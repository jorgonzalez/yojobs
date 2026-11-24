"""We Work Remotely RSS. Titles look like "Company: Job title".

The feed's region is often "Anywhere in the World" for jobs that are remote in one
country only. Each ad starts with "Headquarters: ...": for jobs imported from company
job boards that line is the ad's own location ("Remote - United States", "San Francisco,
CA, US; Remote, CA, US"); for the board's own posts it is the company's head office
("San Francisco, CA"), which says nothing about where you may work. So the line is used
as the location only when it mentions remote work and names a place.
"""
from __future__ import annotations

import re

from ..models import Job, strip_html
from .rss import items, parse_rfc822

URL = "https://weworkremotely.com/remote-jobs.rss"

_HQ = re.compile(r"Headquarters:\s*(?:</strong>)?\s*([^<\n]+)", re.I)


def remote_location(description: str) -> str:
    """The ad's "Headquarters:" line when it reads as a remote job's location, else ""."""
    m = _HQ.search((description or "")[:500])
    if not m:
        return ""
    hq = strip_html(m.group(1))
    if not re.search(r"(?i)\bremote\b", hq):
        return ""                                       # a head office, not the job's place
    if not re.sub(r"(?i)\bremote\b|[\W_]", "", hq):
        return ""                                       # just "Remote": names no place
    return hq


def fetch(cfg, since):
    jobs = []
    for it in items(cfg.get("url", URL)):
        raw = it.get("title", "")
        company, _, title = raw.partition(": ")
        if not title:
            company, title = "", raw
        description = it.get("description") or ""
        jobs.append(Job(
            source="weworkremotely",
            remote=True,  # remote-only board
            title=title.strip(),
            company=company.strip(),
            url=it.get("link") or it.get("guid", ""),
            location=remote_location(description) or it.get("region", ""),
            published=parse_rfc822(it.get("pubDate")),
            description=strip_html(description),
            tags=[t for t in [it.get("category", "")] if t],
        ))
    return jobs
