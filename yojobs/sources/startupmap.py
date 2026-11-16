"""StartupMap (startupmap.one): European startup jobs. One public JSON request
returns every listed job (~16k). There are no descriptions, so required words
like Kubernetes can't be checked: matches are marked "not verified"."""
from __future__ import annotations

import re

from ..http import get_json
from ..models import Job, parse_iso

URL = "https://startupmap.one/api/jobs"
_COUNTRY_SUFFIX = re.compile(r"_[a-z]{2}$")


def _company(startup_id: str) -> str:
    return _COUNTRY_SUFFIX.sub("", startup_id or "").replace("_", " ").replace("-", " ").title()


def _remote(j):
    if j.get("is_remote") or j.get("workplace_type") == "remote":
        return True
    if j.get("workplace_type") in ("onsite", "hybrid"):
        return False
    return None


def _location(j) -> str:
    countries = ", ".join(j.get("job_countries") or [j.get("job_country") or ""]).strip(", ")
    city = j.get("location_display") or ""
    parts = []
    if j.get("is_remote") or j.get("workplace_type") == "remote":
        parts.append("Remote")
    if city and city.lower() not in countries.lower():
        parts.append(city)
    if countries:
        parts.append(countries)
    return ", ".join(parts)


def fetch(cfg, since):
    jobs = []
    for j in get_json(URL):
        if j.get("visible") is False or not j.get("apply_url"):
            continue
        jobs.append(Job(
            source="startupmap",
            remote=_remote(j),
            title=j.get("job_title") or "",
            company=_company(j.get("startup_id", "")),
            url=j["apply_url"],
            location=_location(j),
            # when StartupMap added it: many jobs are added with an older posting date
            published=parse_iso(j.get("first_seen_at")) or parse_iso(j.get("posted_at")),
            tags=list(j.get("type") or []),
            salary=str(j.get("salary") or ""),
            has_description=False,
        ))
    return jobs
