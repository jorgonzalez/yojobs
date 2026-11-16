"""Landing.jobs public API (European tech jobs, many on-site/hybrid).
The API has no company name field; we derive it from the URL /at/<company>/..."""
from __future__ import annotations

from ..http import get_json
from ..models import Job, parse_iso, strip_html

URL = "https://landing.jobs/api/v1/jobs"


def _company(url):
    parts = url.split("/at/", 1)
    return parts[1].split("/", 1)[0].replace("-", " ").title() if len(parts) == 2 else ""


def _location(j):
    locs = [f"{l.get('city', '')} ({l.get('country_code', '')})" for l in j.get("locations") or []]
    if j.get("remote"):
        locs.insert(0, "Remote")
    return ", ".join(locs)


def fetch(cfg, since):
    jobs, page_size = [], 50
    for page in range(cfg.get("max_pages", 6)):
        batch = get_json(URL, {"limit": page_size, "offset": page * page_size})
        if not batch:
            break
        for j in batch:
            url = j.get("url", "")
            desc = " ".join(strip_html(j.get(k)) for k in ("role_description", "main_requirements", "nice_to_have"))
            lo, hi = j.get("gross_salary_low"), j.get("gross_salary_high")
            jobs.append(Job(
                source="landingjobs",
                title=j.get("title", ""),
                company=_company(url),
                url=url,
                location=_location(j),
                published=parse_iso(j.get("published_at")),
                description=desc.strip(),
                tags=j.get("tags") or [],
                salary=f"{j.get('currency_code', '')} {lo:,}-{hi:,}" if lo and hi else "",
            ))
        if len(batch) < page_size:
            break
    return jobs
