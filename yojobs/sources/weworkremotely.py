"""We Work Remotely RSS. Titles look like "Company: Job title"."""
from __future__ import annotations

from ..models import Job, strip_html
from .rss import items, parse_rfc822

URL = "https://weworkremotely.com/remote-jobs.rss"


def fetch(cfg, since):
    jobs = []
    for it in items(cfg.get("url", URL)):
        raw = it.get("title", "")
        company, _, title = raw.partition(": ")
        if not title:
            company, title = "", raw
        jobs.append(Job(
            source="weworkremotely",
            remote=True,  # remote-only board
            title=title.strip(),
            company=company.strip(),
            url=it.get("link") or it.get("guid", ""),
            location=it.get("region", ""),
            published=parse_rfc822(it.get("pubDate")),
            description=strip_html(it.get("description")),
            tags=[t for t in [it.get("category", "")] if t],
        ))
    return jobs
