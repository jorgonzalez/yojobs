"""Arbeitnow public job board API (https://www.arbeitnow.com/api/job-board-api):
jobs in Germany, many in Berlin, mostly tech. 300 jobs per page, newest first
(about 3 days per page); we read pages until the jobs are older than the window.

API terms: free public API, please don't abuse it, link back to the site; the
email links every job to its arbeitnow.com page. robots.txt allows access.

Remote: Arbeitnow's own flag, or clear wording in the title/description
("100% remote", "fully remote"...; see remote.py) when the flag is off.
"""
from __future__ import annotations

import time

from ..http import get_json
from ..models import Job, from_timestamp, strip_html
from ..progress import say
from ..remote import remote_evidence

URL = "https://www.arbeitnow.com/api/job-board-api"


def to_job(j: dict) -> Job:
    title, description = j.get("title") or "", strip_html(j.get("description"))
    if j.get("remote"):
        remote, notes = True, []
    else:
        where = remote_evidence(title, description)
        remote = True if where else False
        notes = ["remote per description, check"] if where == "description" else []
    return Job(
        source="arbeitnow",
        title=title,
        company=j.get("company_name") or "",
        url=j.get("url") or "",
        location=j.get("location") or "",
        published=from_timestamp(j.get("created_at")),
        description=description,
        tags=list(j.get("tags") or []) + list(j.get("job_types") or []),
        remote=remote,
        source_notes=notes,
    )


def fetch(cfg, since):
    jobs = []
    for page in range(1, int(cfg.get("max_pages", 10)) + 1):
        say(f"    arbeitnow page {page}")
        data = get_json(URL, {"page": page})
        batch = [to_job(j) for j in data.get("data") or []]
        jobs += batch
        oldest = min((j.published for j in batch if j.published), default=None)
        if not batch or not (data.get("links") or {}).get("next") or (since and oldest and oldest < since):
            break
        time.sleep(float(cfg.get("delay_seconds", 1.5)))
    return jobs
