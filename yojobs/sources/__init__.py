"""Job sources. Each module exposes `fetch(cfg: dict, since: datetime) -> list[Job]`.

To add a portal: create a module here and register it in SOURCES.
"""
from __future__ import annotations

from . import fourdayweek, himalayas, jobicy, landingjobs, remotive, weworkremotely, workingnomads

SOURCES = {
    "remotive": remotive.fetch,
    "himalayas": himalayas.fetch,
    "jobicy": jobicy.fetch,
    "weworkremotely": weworkremotely.fetch,
    "workingnomads": workingnomads.fetch,
    "landingjobs": landingjobs.fetch,
    "4dayweek": fourdayweek.fetch,
}
