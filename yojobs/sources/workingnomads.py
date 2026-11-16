"""Working Nomads exposed jobs feed (small, latest jobs only)."""
from __future__ import annotations

from ..http import get_json
from ..models import Job, parse_iso, strip_html

URL = "https://www.workingnomads.com/api/exposed_jobs/"


def fetch(cfg, since):
    jobs = []
    for j in get_json(URL):
        jobs.append(Job(
            source="workingnomads",
            title=j.get("title", ""),
            company=j.get("company_name", ""),
            url=j.get("url", ""),
            location=j.get("location", ""),
            published=parse_iso(j.get("pub_date")),
            description=strip_html(j.get("description")),
            tags=[t for t in (j.get("tags") or "").split(",") if t],
        ))
    return jobs
