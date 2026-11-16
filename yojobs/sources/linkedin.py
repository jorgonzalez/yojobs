"""LinkedIn via jobdrop (public guest job search; no LinkedIn account used).

To keep requests low (LinkedIn blocks aggressive scrapers):
  1. run each configured search WITHOUT descriptions (one request per 25 results)
  2. keep only jobs whose title/location already pass a profile (`_title_ok`)
  3. fetch the description only for those, to check required words (Kubernetes)

config.yaml:
  linkedin:
    enabled: true
    results_per_search: 50
    searches:
      - {term: "DevOps Manager", location: Berlin}               # on-site/hybrid/remote in Berlin
      - {term: "DevOps Manager", location: Germany, remote: true} # remote within Germany
"""
from __future__ import annotations

import logging
import random
import sys
import time
from datetime import datetime, timezone
from types import SimpleNamespace

from ..models import Job, strip_html, to_utc
from ..progress import say
from ..remote import remote_evidence


def _published(value):
    if value is None or value != value:  # None / NaN
        return None
    if isinstance(value, datetime):
        return to_utc(value)
    try:  # datetime.date
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    except AttributeError:
        return None


def _str(value) -> str:
    return "" if value is None or value != value else str(value)


def fetch(cfg, since):
    from jobdrop import scrape_jobs, set_logger_level  # heavy import, only when enabled
    from jobdrop.linkedin import LinkedIn
    from jobdrop.model import DescriptionFormat

    set_logger_level(logging.WARNING)
    hours_old = max(1, int((datetime.now(timezone.utc) - since).total_seconds() // 3600))
    title_ok = cfg.get("_title_ok") or (lambda job: True)

    jobs = {}
    searches = cfg.get("searches") or []
    for i, s in enumerate(searches):
        if i:
            time.sleep(random.uniform(4, 8))
        where = f"{s.get('location') or 'anywhere'}{' (remote)' if s.get('remote') else ''}"
        say(f"    linkedin search {i + 1}/{len(searches)}: \"{s['term']}\" in {where}")
        remote = bool(s.get("remote"))
        df = scrape_jobs(
            site_name="linkedin",
            search_term=s["term"],
            location=s.get("location"),
            is_remote=remote,
            hours_old=hours_old,
            results_wanted=cfg.get("results_per_search", 50),
            linkedin_fetch_description=False,
        )
        for row in df.to_dict("records"):
            url = _str(row.get("job_url"))
            if not url or url in jobs:
                continue
            # For remote jobs LinkedIn's location is where you may live/work from
            # ("Cork, Ireland" = remote within Ireland), so keep it as is.
            loc = _str(row.get("location"))
            jobs[url] = Job(
                source="linkedin",
                # provisional: lets remote-search jobs reach the description step;
                # decided for real once the description is known
                remote=True if remote else None,
                title=_str(row.get("title")),
                company=_str(row.get("company")),
                url=url,
                location=loc,
                published=_published(row.get("date_posted")),
                tags=[t for t in [_str(row.get("job_level")), _str(row.get("job_function"))] if t],
            )
            jobs[url]._li_id = _str(row.get("id")).replace("li-", "")

    # Only fetch descriptions for jobs that already pass title + location rules.
    candidates = [j for j in jobs.values() if title_ok(j)]
    say(f"    linkedin: {len(jobs)} jobs found, {len(candidates)} match title + location; fetching their descriptions")
    if candidates:
        li = LinkedIn()
        li.scraper_input = SimpleNamespace(description_format=DescriptionFormat.MARKDOWN)
        for n, job in enumerate(candidates):
            if n:
                time.sleep(random.uniform(2, 5))
            say(f"    linkedin description {n + 1}/{len(candidates)}: {job.title[:60]}")
            details = li._get_job_details(job._li_id) or {}
            job.description = strip_html(details.get("description") or "")
    # Decide remote for every job from the wording, not LinkedIn's filter.
    for job in jobs.values():
        where = remote_evidence(job.title, job.description)
        job.remote = bool(where)
        if where == "description":
            job.source_notes = ["remote per description, check"]
    if candidates:
        missing = sum(1 for j in candidates if not j.description)
        if missing:
            print(f"[linkedin] {missing}/{len(candidates)} descriptions could not be fetched "
                  f"(possibly rate-limited); those jobs can't pass the Kubernetes check", file=sys.stderr)
    return list(jobs.values())
