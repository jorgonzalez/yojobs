"""Keep the log files from growing forever (settings.yaml `logs:`).

  logs:
    keep_days: 90     # delete lines older than this (off when missing)
    max_mb: 50        # and never let a file grow past this (default 2): keep the newest half
    files: [~/Library/Logs/yojobs.log, ~/Library/Logs/ollama.log]   # the default

Lines are dated by their own timestamp: yojobs' "2026-11-19 07:07:18 ..." (scheduled runs),
Python logging's "2026-11-19 07:07:17,987 - ...", Ollama's "time=2026-11-19T..." and
"[GIN] 2026/11/19 - ...". Lines without a date (tracebacks, tables) belong to the dated line
before them. Files are rewritten in place, so a program appending to them (launchd's output,
`ollama serve`) keeps writing to the same file.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Optional

DEFAULT_FILES = ["~/Library/Logs/yojobs.log", "~/Library/Logs/ollama.log"]
DEFAULT_MAX_MB = 2.0
_DATE = re.compile(rb"^(?:time=)?(\d{4})-(\d{2})-(\d{2})[ T]|^\[GIN\] (\d{4})/(\d{2})/(\d{2}) ")


def line_date(line: bytes) -> Optional[date]:
    m = _DATE.match(line)
    if not m:
        return None
    y, mo, d = (int(x) for x in (m.group(1, 2, 3) if m.group(1) else m.group(4, 5, 6)))
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def cut_before(lines: list, cutoff: date) -> int:
    """Index of the first line to keep: the first dated line on/after `cutoff`. When every dated
    line is older, everything goes (len(lines)); when nothing is dated, nothing goes (0)."""
    dated = False
    for i, line in enumerate(lines):
        d = line_date(line)
        if d is None:
            continue
        dated = True
        if d >= cutoff:
            return i
    return len(lines) if dated else 0


def _rewrite(path: Path, data: bytes) -> None:
    with open(path, "r+b") as fh:  # same file (inode): appending writers keep working
        fh.write(data)
        fh.truncate()


def trim(path: Path, keep_days: Optional[float], max_mb: float, today: Optional[date] = None) -> str:
    """Trim one file; -> what was done ("" if nothing)."""
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    data = None
    done = []
    if keep_days:
        cutoff = (today or date.today()) - timedelta(days=float(keep_days))
        with open(path, "rb") as fh:
            head = fh.read(65536).splitlines()
        first = next((d for d in map(line_date, head) if d), None)
        if first is not None and first < cutoff:  # only read the whole file when there's something to cut
            with open(path, "rb") as fh:
                lines = fh.read().splitlines(keepends=True)
            i = cut_before(lines, cutoff)
            if i:
                data = b"".join(lines[i:])
                done.append(f"{i} lines older than {cutoff}")
    limit = int(max_mb * 1_000_000)
    current = len(data) if data is not None else size
    if limit > 0 and current > limit:
        if data is None:
            with open(path, "rb") as fh:
                fh.seek(-(limit // 2), 2)
                data = fh.read()
        else:
            data = data[-(limit // 2):]
        data = b"[... older log lines trimmed ...]\n" + data[data.find(b"\n") + 1:]
        done.append(f"over {max_mb:g} MB")
    if data is None:
        return ""
    try:
        _rewrite(path, data)
    except OSError:
        return ""
    return f"{path.name}: removed " + " and ".join(done)


def trim_all(cfg: Optional[dict], today: Optional[date] = None) -> list:
    cfg = cfg or {}
    keep_days = cfg.get("keep_days")
    max_mb = float(cfg.get("max_mb", DEFAULT_MAX_MB))
    files: Iterable[str] = cfg.get("files") or DEFAULT_FILES
    return [r for r in (trim(Path(f).expanduser(), keep_days, max_mb, today) for f in files) if r]
