"""Remotive public API. Their terms: max ~4 requests/day, link back to Remotive.
Jobs are delayed 24h in the public feed."""
from __future__ import annotations

from ..http import get_json
from ..models import Job, parse_iso, strip_html

URL = "https://remotive.com/api/remote-jobs"


def fetch(cfg, since):
    data = get_json(URL, {"limit": cfg.get("limit", 500)})
    jobs = []
    for j in data.get("jobs", []):
        jobs.append(Job(
            source="remotive",
            title=j.get("title", ""),
            company=j.get("company_name", ""),
            url=j.get("url", ""),
            location=j.get("candidate_required_location", ""),
            published=parse_iso(j.get("publication_date")),
            description=strip_html(j.get("description")),
            tags=j.get("tags") or [],
            salary=j.get("salary") or "",
        ))
    return jobs
