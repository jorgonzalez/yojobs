"""Progress messages on stderr (results stay on stdout).

Three kinds of message:
  step(msg)  the portal being checked now, e.g. "[3/15] himalayas"
  say(msg)   detail: every search, page, board... (what a source is doing)
  note(msg)  always shown: errors, summary, email sent, lock, schedule decisions

Verbose (-v, and always for scheduled runs / the launchd log): every message is
its own timestamped line.

Quiet (default): in a terminal, a single status line is redrawn in place
("[3/15] himalayas · page 2...") without new lines; when the run ends it is
cleared. Only note() messages get lines of their own. When stderr is not a
terminal (piped, redirected), the status line is not drawn at all.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime

_verbose = False
_status = ""     # current step text (quiet mode)
_drawn = False   # is a status line currently on screen?


def set_verbose(value: bool) -> None:
    global _verbose
    _verbose = bool(value)


def is_verbose() -> bool:
    return _verbose


def _tty() -> bool:
    try:
        return sys.stderr.isatty()
    except (AttributeError, ValueError):
        return False


def _line(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S}  {msg}", file=sys.stderr, flush=True)


def _clear() -> None:
    global _drawn
    if _drawn:
        sys.stderr.write("\r\033[K")
        sys.stderr.flush()
        _drawn = False


def _draw(text: str) -> None:
    global _drawn
    if not _tty():
        return
    width = max(20, shutil.get_terminal_size((100, 20)).columns - 1)
    text = " ".join(text.split())  # one line, no leading indentation
    if len(text) > width:
        text = text[: width - 1] + "…"
    sys.stderr.write("\r\033[K" + text)
    sys.stderr.flush()
    _drawn = True


def step(msg: str) -> None:
    """The portal being checked now."""
    global _status
    if _verbose:
        _line(msg)
        return
    _status = msg
    _draw(msg)


def say(msg: str) -> None:
    """Detail: a line in verbose mode, otherwise appended to the status line."""
    if _verbose:
        _line(msg)
    elif _status:
        detail = msg.strip()
        name = _status.split("] ", 1)[-1]  # "[3/15] himalayas" -> "himalayas"
        for prefix in (_status, name):     # avoid "companies · companies 4/66"
            if detail.startswith(prefix):
                detail = detail[len(prefix):].lstrip(" :")
                break
        _draw(f"{_status} · {detail}" if detail else _status)


def note(msg: str) -> None:
    """Always shown on a line of its own."""
    if not _verbose:
        _clear()
    _line(msg)


def end() -> None:
    """The portal loop is over: remove the status line."""
    global _status
    _status = ""
    _clear()
