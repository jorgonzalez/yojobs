"""Decide whether a scheduled run is due, and keep runs from overlapping.

launchd starts `yojobs --scheduled` every 10 minutes (and at login). Timers don't fire
while the Mac sleeps, so checking often means a due run starts soon after it wakes;
this module decides if that tick should actually run:

  * not before `earliest` or after `latest` (local time)
  * at most `max_runs_per_day`, at least `min_gap_hours` apart
  * a new day starts fresh: missed runs from earlier days are not caught up
  * a run only counts if it worked (some source answered and the email, if any,
    was sent); otherwise the next tick tries again

State lives in a small JSON file next to the database (git-ignored).
"""
from __future__ import annotations

import fcntl
import json
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


def trim_log(path: Path, max_bytes: int = 2_000_000, keep_bytes: int = 1_000_000) -> None:
    """Keep the launchd log from growing forever: when it passes max_bytes,
    keep only the last keep_bytes."""
    try:
        if path.stat().st_size <= max_bytes:
            return
        with open(path, "rb") as fh:
            fh.seek(-keep_bytes, 2)
            tail = fh.read()
        with open(path, "wb") as fh:
            fh.write(b"[... older log lines trimmed ...]\n" + tail[tail.find(b"\n") + 1:])
    except OSError:
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
