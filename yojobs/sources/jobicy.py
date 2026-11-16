"""Jobicy API v2. Terms: credit Jobicy and link to the original job URL."""
from __future__ import annotations

from ..http import get_json
from ..models import Job, parse_iso, strip_html

URL = "https://jobicy.com/api/v2/remote-jobs"


def _salary(j):
    lo, hi = j.get("salaryMin"), j.get("salaryMax")
    if lo and hi:
        return f"{j.get('salaryCurrency', '')} {lo:,}-{hi:,}".strip()
    return ""


def fetch(cfg, since):
    params = {"count": cfg.get("count", 100)}
    if cfg.get("geo"):
        params["geo"] = cfg["geo"]
    data = get_json(URL, params)
    jobs = []
    for j in data.get("jobs", []):
        jobs.append(Job(
            source="jobicy",
            remote=True,  # remote-only board
            title=strip_html(j.get("jobTitle")),
            company=j.get("companyName", ""),
            url=j.get("url", ""),
            location=j.get("jobGeo", ""),
            published=parse_iso(j.get("pubDate")),
            description=strip_html(j.get("jobDescription") or j.get("jobExcerpt")),
            tags=(j.get("jobIndustry") or []) + ([j["jobLevel"]] if j.get("jobLevel") else []),
            salary=_salary(j),
        ))
    return jobs
