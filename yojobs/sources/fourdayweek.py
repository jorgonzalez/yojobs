"""4dayweek.io RSS feed. Titles look like "Job title at Company"; no description."""
from __future__ import annotations

from ..models import Job, strip_html
from .rss import items, parse_rfc822

URL = "https://4dayweek.io/feed"


def fetch(cfg, since):
    jobs = []
    for it in items(URL):
        raw = it.get("title", "")
        company = it.get("author", "")
        title = raw[: -len(f" at {company}")] if company and raw.endswith(f" at {company}") else raw
        jobs.append(Job(
            source="4dayweek",
            title=title,
            company=company,
            url=it.get("link") or it.get("guid", ""),
            published=parse_rfc822(it.get("pubDate")),
            description=strip_html(it.get("description")),
        ))
    return jobs
