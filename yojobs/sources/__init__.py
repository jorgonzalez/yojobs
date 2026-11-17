"""Job sources. Each module exposes `fetch(cfg: dict, since: datetime) -> list[Job]`.

To add a portal: create a module here and register it in SOURCES.
"""
from __future__ import annotations

from . import arbeitnow, berlinstartupjobs, companies, euremotejobs, fourdayweek, hackernews, himalayas, indeed, jobicy, landingjobs, linkedin, remoteok, remotive, startupmap, stepstone, welcometothejungle, weworkremotely, workingnomads, wpjobmanager

SOURCES = {
    "remotive": remotive.fetch,
    "remoteok": remoteok.fetch,
    "himalayas": himalayas.fetch,
    "jobicy": jobicy.fetch,
    "weworkremotely": weworkremotely.fetch,
    "workingnomads": workingnomads.fetch,
    "landingjobs": landingjobs.fetch,
    "4dayweek": fourdayweek.fetch,
    "linkedin": linkedin.fetch,
    "indeed": indeed.fetch,
    "stepstone": stepstone.fetch,
    "welcometothejungle": welcometothejungle.fetch,
    "euremotejobs": euremotejobs.fetch,
    "euroremotejobs": wpjobmanager.fetch_euroremotejobs,
    "jobspresso": wpjobmanager.fetch_jobspresso,
    "hackernews": hackernews.fetch,
    "companies": companies.fetch,
    "startupmap": startupmap.fetch,
    "berlinstartupjobs": berlinstartupjobs.fetch,
    "arbeitnow": arbeitnow.fetch,
}
