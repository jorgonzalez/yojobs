"""Progress messages on stderr, so long runs show what is happening (and the
launchd log gets a timeline). Results stay on stdout."""
from __future__ import annotations

import sys
from datetime import datetime


def say(msg: str) -> None:
    print(f"{datetime.now():%H:%M:%S}  {msg}", file=sys.stderr, flush=True)
