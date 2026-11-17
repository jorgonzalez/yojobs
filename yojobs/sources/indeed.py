"""Indeed (Germany) via jobdrop. Fast, and descriptions are included.

Indeed returns 0 results when its time filter is combined with a location, so we
search without it and drop old jobs ourselves. Indeed's own remote flag also covers
"mobiles Arbeiten" jobs, so a job outside Berlin only counts as remote if its
location says Home Office/Remote or its title/description clearly says remote.

config.yaml:
  indeed:
    enabled: true
    country: Germany
    results_per_search: 50
    searches:
      - {term: "DevOps Manager", location: Berlin}
      - {term: "DevOps Manager", location: Germany, remote: true}
"""
from __future__ import annotations

import logging
import random
import re
import time
from datetime import datetime, timezone

from ..models import Job, strip_html, to_utc
from ..progress import is_verbose, note, say
from ..remote import remote_evidence

_HOME_OFFICE_LOC = re.compile(r"\b(home\s?office|remote)\b", re.I)


def _str(value) -> str:
    return "" if value is None or value != value else str(value)


def _published(value):
    if value is None or value != value:
        return None
    if isinstance(value, datetime):
        return to_utc(value)
    try:
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    except AttributeError:
        return None


def _location(raw: str) -> str:
    # "Berlin, BE, DE" -> "Berlin, BE, Germany" so region rules recognise it
    return re.sub(r"\bDE$", "Germany", raw.strip())


def fetch(cfg, since):
    from jobdrop import scrape_jobs, set_logger_level  # heavy import, only when enabled

    # jobdrop warnings would break the one-line status display in quiet mode
    set_logger_level(logging.WARNING if is_verbose() else logging.ERROR)
    country = cfg.get("country", "Germany")
    searches = cfg.get("searches") or []
    jobs = {}
    for i, s in enumerate(searches):
        if i:
            time.sleep(random.uniform(1.5, 3))
        where = f"{s.get('location') or country}{' (remote)' if s.get('remote') else ''}"
        say(f"    indeed search {i + 1}/{len(searches)}: \"{s['term']}\" in {where}")
        df = scrape_jobs(
            site_name="indeed",
            search_term=s["term"],
            location=s.get("location"),
            is_remote=bool(s.get("remote")),
            country_indeed=country,
            results_wanted=cfg.get("results_per_search", 50),
            description_format="markdown",
        )
        for row in df.to_dict("records"):
            url = _str(row.get("job_url"))
            if not url or url in jobs:
                continue
            title = _str(row.get("title"))
            loc = _location(_str(row.get("location")))
            desc = strip_html(_str(row.get("description")))
            where_remote = "location" if _HOME_OFFICE_LOC.search(loc) else remote_evidence(title, desc)
            jobs[url] = Job(
                source="indeed",
                title=title,
                company=_str(row.get("company")),
                url=url,
                location=loc,
                published=_published(row.get("date_posted")),
                description=desc,
                remote=bool(where_remote),
                source_notes=["remote per description, check"] if where_remote == "description" else [],
            )
    return list(jobs.values())
