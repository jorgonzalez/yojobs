"""Welcome to the Jungle, from its public sitemaps only.

robots.txt disallows its search and any URL with "?", and its job pages have bot
protection (opening ~60 in a row got us HTTP 202 challenges, then 403). So we only
read the job-listing sitemaps it publishes for crawlers (~9 gzip files per run).
Each URL looks like /<lang>/companies/<company>/jobs/<title-slug>_<city>_<id>,
with a lastmod date. That gives title, company, city and date, but no description
and no remote field: matches are marked "Kubernetes not verified", and since the
work mode is unknown, only jobs whose city is in `onsite_cities` (Berlin) pass.
"""
from __future__ import annotations

import gzip
import re
import time

from ..http import get_bytes
from ..models import Job, parse_iso
from ..progress import say

INDEX = "https://www.welcometothejungle.com/sitemaps/index.xml.gz"
_LOC = re.compile(r"<loc>([^<]+)</loc>(?:<lastmod>([^<]+)</lastmod>)?")
_URL = re.compile(r"/companies/([^/]+)/jobs/([^/?#]+)$")


def _sitemap_urls(url):
    raw = get_bytes(url)
    try:
        raw = gzip.decompress(raw)
    except OSError:
        pass  # already plain XML
    return _LOC.findall(raw.decode("utf-8", "replace"))


def _words(slug: str) -> str:
    return " ".join(w.capitalize() if w.islower() else w for w in slug.split("-") if w)


def _job(loc: str, lastmod: str):
    m = _URL.search(loc)
    if not m:
        return None
    company_slug, slug = m.groups()
    parts = slug.split("_")
    title_slug = parts[0]
    city_slug = parts[1] if len(parts) >= 3 else ""  # <title>_<city>_<id>; some have no city
    return Job(
        source="welcometothejungle",
        title=_words(title_slug),
        company=_words(re.sub(r"-\d+$", "", company_slug)),
        url=loc,
        location=_words(city_slug),
        published=parse_iso(lastmod),  # last update of the listing, not first posting
        has_description=False,
        remote=None,  # unknown without opening the (bot-protected) job page
    )


def fetch(cfg, since):
    since_s = since.strftime("%Y-%m-%d")
    say("    welcometothejungle: reading sitemaps")
    sitemaps = [u for u, _ in _sitemap_urls(INDEX) if "job-listings" in u]
    jobs, seen_ids = [], set()
    for n, sm in enumerate(sitemaps):
        if n:
            time.sleep(1)
        for loc, lastmod in _sitemap_urls(sm):
            if lastmod and lastmod[:10] < since_s:
                continue
            job = _job(loc, lastmod)
            if not job:
                continue
            job_id = loc.rsplit("_", 1)[-1]
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)
            jobs.append(job)
    return jobs
