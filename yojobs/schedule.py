"""Decide whether a scheduled run is due, and keep runs from overlapping.

launchd starts `yojobs --scheduled` every 10 minutes (and at login). Timers don't fire
while the Mac sleeps, so checking often means a due run starts soon after it wakes;
this module decides if that tick should actually run:

  * not before `earliest` or after `latest` (local time)
  * at most `max_runs_per_day`, at least `min_gap_hours` apart
  * a new day starts fresh: missed runs from earlier days are not caught up
  * a run only counts if it worked (some source answered and the email, if any,
    was sent); otherwise the next tick tries again
  * no run starts in a Power Nap wake: macOS wakes a sleeping Mac for a few seconds
    now and then (and launchd fires then), so a run would crawl along in those slices
    all night and its downloads time out; the next real wake starts it instead
  * while a run is going the Mac doesn't idle-sleep (`caffeinate -i`), so a run started
    just before you walk away still finishes; closing the lid on battery still sleeps

State lives in a small JSON file next to the database (git-ignored).
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Optional, Tuple

DEFAULTS = {"earliest": "07:00", "latest": "22:00", "min_gap_hours": 5, "max_runs_per_day": 3}


def _hhmm(value: str) -> time:
    h, m = str(value).split(":")
    return time(int(h), int(m))


class State:
    def __init__(self, path: Path):
        self.path = path
        try:
            self.data = json.loads(path.read_text())
        except (OSError, ValueError):
            self.data = {}

    @property
    def runs(self):
        """Successful run times (local, naive), most recent last."""
        return [datetime.fromisoformat(t) for t in self.data.get("runs", [])]

    @property
    def last_run(self) -> Optional[datetime]:
        runs = self.runs
        return runs[-1] if runs else None

    def log_once_per_hour(self, now: datetime) -> bool:
        """True the first time it's asked in each clock hour (for "not due" log lines)."""
        hour = now.strftime("%Y-%m-%dT%H")
        if self.data.get("not_due_logged") == hour:
            return False
        self.data["not_due_logged"] = hour
        self.path.write_text(json.dumps(self.data, indent=2))
        return True

    def record_run(self, when: datetime) -> None:
        runs = [r for r in self.runs if r > when - timedelta(days=7)] + [when]  # keep a week
        self.data["runs"] = [r.isoformat(timespec="seconds") for r in runs]
        self.path.write_text(json.dumps(self.data, indent=2))


def is_due(cfg: dict, state: State, now: datetime) -> Tuple[bool, str]:
    c = {**DEFAULTS, **(cfg or {})}
    earliest, latest = _hhmm(c["earliest"]), _hhmm(c["latest"])
    if now.time() < earliest:
        return False, f"too early (runs start at {c['earliest']})"
    if now.time() > latest:
        return False, f"too late (no runs after {c['latest']})"
    today = [r for r in state.runs if r.date() == now.date()]
    if len(today) >= int(c["max_runs_per_day"]):
        return False, f"already {len(today)} runs today (max {c['max_runs_per_day']})"
    if today:
        next_at = today[-1] + timedelta(hours=float(c["min_gap_hours"]))
        if now < next_at:
            return False, f"last run at {today[-1]:%H:%M}; next one from {next_at:%H:%M}"
        return True, f"{float(c['min_gap_hours']):g}h since the last run at {today[-1]:%H:%M}"
    return True, "first run today"


def dark_wake(run=subprocess.run) -> bool:
    """True in a macOS Power Nap / maintenance wake ("DarkWake"): the system runs but
    without graphics, as `pmset -g systemstate` shows ("Current System Capabilities are:
    CPU Network Disk" vs "CPU Graphics Audio Network"). Unknown -> False (don't block runs)."""
    try:
        out = run(["pmset", "-g", "systemstate"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    m = re.search(r"Current System Capabilities are:(.*)", out or "")
    return bool(m) and "Graphics" not in m.group(1)


def keep_awake(popen=subprocess.Popen):
    """Start `caffeinate -i -w <this process>`: no idle sleep until this process ends
    (caffeinate then exits by itself). -> the process to stop, or None if unavailable."""
    try:
        return popen(["caffeinate", "-i", "-w", str(os.getpid())],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return None


def stop_awake(proc) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:  # it ends with this process anyway
        pass


class RunLock:
    """Non-blocking exclusive lock: a second run while one is going just exits."""

    def __init__(self, path: Path):
        self.path = path
        self.fh = None

    def acquire(self) -> bool:
        self.fh = open(self.path, "w")
        try:
            fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.fh.close()
            self.fh = None
            return False
        return True

    def release(self) -> None:
        if self.fh:
            fcntl.flock(self.fh, fcntl.LOCK_UN)
            self.fh.close()
            self.fh = None
