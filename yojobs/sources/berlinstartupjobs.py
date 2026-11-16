"""Berlin Startup Jobs RSS. Titles look like "Job title // Company"; the feed only
has a short teaser, so the full job page is fetched for jobs whose title and
location already match (usually 0-2 per run), to check required words."""
from __future__ import annotations

import time

from ..http import get_bytes
from ..models import Job, strip_html
from .rss import items, parse_rfc822

FEEDS = [
    "https://berlinstartupjobs.com/engineering/feed/",
    "https://berlinstartupjobs.com/feed/",
]


def fetch(cfg, since):
    jobs = {}
    for feed in cfg.get("feeds") or FEEDS:
        for it in items(feed):
            url = it.get("link") or it.get("guid", "")
            if not url or url in jobs:
                continue
            title, _, company = it.get("title", "").rpartition(" // ")
            if not title:
                title, company = it.get("title", ""), ""
            jobs[url] = Job(
                source="berlinstartupjobs",
                title=title.strip(),
                company=company.strip(),
                url=url,
                location="Berlin, Germany",
                published=parse_rfc822(it.get("pubDate")),
                description=strip_html(it.get("description")),
                tags=[it.get("category", "")] if it.get("category") else [],
            )

    title_ok = cfg.get("_title_ok") or (lambda job: True)
    for job in jobs.values():
        if job.published and job.published < since:
            continue
        if title_ok(job):
            time.sleep(1)
            try:
                job.description = strip_html(get_bytes(job.url).decode("utf-8", "replace"))
            except Exception:
                pass  # keep the teaser; Kubernetes check will likely fail
    return list(jobs.values())
