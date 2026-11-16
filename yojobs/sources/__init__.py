"""Job sources. Each module exposes `fetch(cfg: dict, since: datetime) -> list[Job]`.

To add a portal: create a module here and register it in SOURCES.
"""
from __future__ import annotations

from . import berlinstartupjobs, fourdayweek, himalayas, indeed, jobicy, landingjobs, linkedin, remotive, startupmap, weworkremotely, workingnomads

SOURCES = {
    "remotive": remotive.fetch,
    "himalayas": himalayas.fetch,
    "jobicy": jobicy.fetch,
    "weworkremotely": weworkremotely.fetch,
    "workingnomads": workingnomads.fetch,
    "landingjobs": landingjobs.fetch,
    "4dayweek": fourdayweek.fetch,
    "linkedin": linkedin.fetch,
    "indeed": indeed.fetch,
    "startupmap": startupmap.fetch,
    "berlinstartupjobs": berlinstartupjobs.fetch,
}
