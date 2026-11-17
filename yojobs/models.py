from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class Job:
    """Common shape every source maps its jobs into."""

    source: str
    title: str
    company: str
    url: str
    location: str = ""
    published: Optional[datetime] = None  # always timezone-aware (UTC)
    description: str = ""  # plain text
    tags: List[str] = field(default_factory=list)
    salary: str = ""
    has_description: bool = True  # False for sources that never provide one
    remote: Optional[bool] = None  # True remote, False on-site/hybrid, None unknown
    source_notes: List[str] = field(default_factory=list)  # e.g. "remote per description"
    work_mode: str = ""  # as stated by the source: "remote", "hybrid", "onsite" (or "")
    work_hint: str = ""  # shown next to the location, e.g. "hybrid · 2 office days/week"


    # Filled in by the filter step
    score: int = 0
    matched: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)  # e.g. "Kubernetes not verified"


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(text: Optional[str]) -> str:
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", html.unescape(text)).strip()


def to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO-8601 strings like 2026-11-14T20:33:53, ...Z, ...+00:00, ...-05:00."""
    if not value:
        return None
    v = value.strip().replace("Z", "+00:00")
    try:
        return to_utc(datetime.fromisoformat(v))
    except ValueError:
        # fromisoformat on 3.9 dislikes some fractional-second lengths
        try:
            return to_utc(datetime.fromisoformat(re.sub(r"\.\d+", "", v)))
        except ValueError:
            return None


def from_timestamp(value) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
