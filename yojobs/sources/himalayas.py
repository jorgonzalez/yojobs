"""Himalayas. The browse feed gets ~20 new jobs/hour, too many to page through,
so by default we use the search endpoint: one query per profile keyword,
sorted newest first, paging until results are older than `since`.
Set `mode: browse` in config to page the raw feed instead (capped by max_pages)."""
from __future__ import annotations

import time

from ..http import get_json
from ..models import Job, from_timestamp, strip_html

BROWSE_URL = "https://himalayas.app/jobs/api"
SEARCH_URL = "https://himalayas.app/jobs/api/search"


def _salary(j):
    lo, hi, cur = j.get("minSalary"), j.get("maxSalary"), j.get("currency") or ""
    if lo and hi:
        return f"{cur} {lo:,}-{hi:,}".strip()
    return ""


def _job(j):
    return Job(
        source="himalayas",
        title=j.get("title", ""),
        company=j.get("companyName", ""),
        url=j.get("applicationLink") or j.get("guid", ""),
        location=", ".join(j.get("locationRestrictions") or []) or "Worldwide",
        published=from_timestamp(j.get("pubDate")),
        description=strip_html(j.get("description") or j.get("excerpt")),
        tags=j.get("categories") or [],
        salary=_salary(j),
    )


def _search(cfg, since):
    found = {}
    for kw in cfg.get("_keywords", []):
        for page in range(1, cfg.get("max_pages", 5) + 1):
            time.sleep(cfg.get("delay_seconds", 1.5))  # be polite; they rate-limit
            data = get_json(SEARCH_URL, {"q": kw, "sort": "recent", "page": page})
            batch = [_job(j) for j in data.get("jobs", [])]
            for job in batch:
                if job.published and job.published >= since:
                    found.setdefault(job.url, job)
            # stop once a whole page is older than the window (first item can be out of order)
            if len(batch) < 20 or all(j.published and j.published < since for j in batch[1:]):
                break
    return list(found.values())


def _browse(cfg, since):
    jobs, cursor = [], None
    for _ in range(cfg.get("max_pages", 15)):
        params = {"limit": 20}
        if cursor:
            params["cursor"] = cursor
        data = get_json(BROWSE_URL, params)
        batch = [_job(j) for j in data.get("jobs", [])]
        jobs.extend(j for j in batch if not j.published or j.published >= since)
        cursor = data.get("nextCursor")
        if not batch or not cursor or any(j.published and j.published < since for j in batch):
            break
    return jobs


def fetch(cfg, since):
    if cfg.get("mode", "search") == "search" and cfg.get("_keywords"):
        return _search(cfg, since)
    return _browse(cfg, since)
