"""Remote OK public API (https://remoteok.com/api): the latest ~100 remote jobs.

API terms: mention Remote OK as the source and link to the job on remoteok.com;
the email does both (source name + job URL). robots.txt allows general access.

Every job is remote; `location` is where the company hires (e.g. "Germany",
"EMEA", "Remote - US"), which the remote_regions rule checks.
Some text arrives double-encoded (UTF-8 read as Latin-1: "MÃ¼nchen"); fixed here.
"""
from __future__ import annotations

from ..http import get_json
from ..models import Job, from_timestamp, parse_iso, strip_html

URL = "https://remoteok.com/api"


def fix_mojibake(text: str) -> str:
    """'MÃ¼nchen' -> 'München'; text that is already fine is returned unchanged."""
    if not text or not any(c in text for c in "ÃÂâ"):
        return text or ""
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def _salary(j):
    lo, hi = int(j.get("salary_min") or 0), int(j.get("salary_max") or 0)
    if lo and hi:
        return f"USD {lo:,}-{hi:,}"
    return ""


def fetch(cfg, since):
    jobs = []
    for j in get_json(URL):
        if not isinstance(j, dict) or "position" not in j:
            continue  # the first element is the API's legal notice
        text = lambda key: fix_mojibake(str(j.get(key) or ""))
        jobs.append(Job(
            source="remoteok",
            remote=True,  # remote-only board
            title=strip_html(text("position")),
            company=text("company"),
            url=j.get("url") or "",
            location=text("location"),
            published=parse_iso(j.get("date")) or from_timestamp(int(j.get("epoch") or 0)),
            description=strip_html(text("description")),
            tags=[fix_mojibake(t) for t in j.get("tags") or []],
            salary=_salary(j),
        ))
    return jobs
