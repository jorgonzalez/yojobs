"""Job boards built on WordPress + WP Job Manager, via their job RSS feed.

Each item has title, link, date, the full ad (content:encoded) and job fields
(job_listing:company / location / job_type / salary).

  euroremotejobs  https://euroremotejobs.com/?feed=job_feed&posts_per_page=100
                  robots.txt allows query URLs: the newest 100 jobs (~2 days)
  jobspresso      https://jobspresso.co/feed/job_feed/
                  robots.txt disallows every URL with "?", so only the plain feed
                  address is used, which returns just the newest 10 jobs

Both are remote-only boards; the location is where the job may be done from
(e.g. "Europe", "UK"), which the remote_regions rule checks.
"""
from __future__ import annotations

from urllib.parse import urlencode

from ..models import Job, strip_html
from .rss import items, parse_rfc822

SITES = {
    "euroremotejobs": ("https://euroremotejobs.com/", {"feed": "job_feed", "posts_per_page": 100}),
    "jobspresso": ("https://jobspresso.co/feed/job_feed/", {}),
}


def clean_location(location: str) -> str:
    """euroremotejobs adds "Europe" to every country ("United Kingdom, Europe"),
    which would make a UK-only job pass a remote_regions rule that allows Europe.
    When specific places are listed, drop the generic region."""
    parts = [p.strip() for p in (location or "").split(",") if p.strip()]
    specific = [p for p in parts if p.lower() not in ("europe", "eu", "emea")]
    return ", ".join(specific if specific else parts)


def to_job(source: str, it: dict) -> Job:
    return Job(
        source=source,
        title=strip_html(it.get("title")),
        company=strip_html(it.get("company")),
        url=it.get("link") or it.get("guid") or "",
        location=clean_location(strip_html(it.get("location"))),
        published=parse_rfc822(it.get("pubDate")),
        description=strip_html(it.get("encoded") or it.get("description")),
        tags=[t for t in (strip_html(it.get("job_type")), strip_html(it.get("job_category"))) if t],
        salary=strip_html(it.get("salary")),
        remote=True,  # remote-only boards
    )


def _fetcher(source: str):
    base, params = SITES[source]

    def fetch(cfg, since):
        url = base + ("?" + urlencode(params) if params else "")
        return [to_job(source, it) for it in items(url)]

    fetch.__doc__ = f"{source}: WP Job Manager feed ({base})"
    return fetch


fetch_euroremotejobs = _fetcher("euroremotejobs")
fetch_jobspresso = _fetcher("jobspresso")
