"""Remote Rocketship (remoterocketship.com), from its job sitemaps; robots.txt allows them
(it disallows /api and personal pages).

Its English job-opening sitemaps (worldwide + "rest of world", ~50,000 URLs) give, per job,
the company, a title slug ending in the place it's open to ("…-germany-remote",
"…-europe-remote", "…-worldwide-remote") and when it was last updated. Only jobs updated
within the window and open to one of `places` are kept; titles are filtered before
anything else is fetched. Job pages (schema.org JobPosting: full ad, the exact countries
allowed, date, company name) are opened only for new candidates.

The site's German section translates titles and pages into German, which the title and
language rules would misread, so only the English sitemaps are used.
"""
from __future__ import annotations

import json
import re
import time
from typing import Dict, List

from ..http import get_bytes
from ..models import Job, parse_iso, strip_html
from ..progress import say

BASE = "https://www.remoterocketship.com/"
SITEMAPS = ["sitemap_job_openings_worldwide.xml", "sitemap_job_openings_rest_of_world.xml",
            "sitemap_job_openings_rest_of_world_2.xml"]
# slug tail -> location for the remote_regions rule
PLACES = {"worldwide": "Worldwide", "germany": "Germany", "berlin": "Berlin", "europe": "Europe",
          "emea": "EMEA", "european-union": "European Union"}
_ENTRY = re.compile(r"<loc>([^<]+)</loc>\s*(?:<lastmod>([^<]+)</lastmod>)?")
_URL = re.compile(r"/company/([^/]+)/jobs/([^/]+)/?$")


def _tail(places: Dict[str, str]):
    return re.compile(r"-(" + "|".join(re.escape(p) for p in sorted(places, key=len, reverse=True))
                      + r")-remote(?:-\d+)?$")


def _words(slug: str) -> str:
    return " ".join(w.capitalize() if w.islower() else w for w in slug.split("-") if w)


def entries(sitemap: str, since, places: Dict[str, str]) -> List[Job]:
    tail, out = _tail(places), []
    since_s = since.isoformat() if since else ""
    for url, lastmod in _ENTRY.findall(sitemap):
        if since_s and lastmod and lastmod < since_s[:len(lastmod)]:
            continue
        m = _URL.search(url)
        if not m:
            continue
        t = tail.search(m.group(2))
        if not t:
            continue  # open to somewhere else (a single country, the US...)
        out.append(Job(source="remoterocketship", title=_words(m.group(2)[:t.start()]),
                       company=_words(m.group(1)), url=url, location=places[t.group(1)],
                       published=parse_iso(lastmod) if lastmod else None, remote=True))
    return out


def job_posting(page: str) -> dict:
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            return data
    return {}


def enrich(job: Job, posting: dict) -> None:
    """Real title, company, full ad, date and the countries allowed, from the job page."""
    if not posting:
        return
    job.title = strip_html(posting.get("title")) or job.title
    org = posting.get("hiringOrganization") or {}
    job.company = (org.get("name") if isinstance(org, dict) else "") or job.company
    job.description = strip_html(posting.get("description") or "")
    job.published = parse_iso(posting.get("datePosted")) or job.published
    reqs = posting.get("applicantLocationRequirements") or []
    names = [r.get("name") for r in (reqs if isinstance(reqs, list) else [reqs]) if isinstance(r, dict) and r.get("name")]
    if names:
        job.location = ", ".join(dict.fromkeys(names))


def fetch(cfg, since):
    title_ok = cfg.get("_title_ok") or (lambda job: True)
    known = cfg.get("_known") or (lambda job: False)
    problems = cfg.get("_problems")
    places = cfg.get("places") or PLACES
    delay = float(cfg.get("delay_seconds", 4))
    jobs: Dict[str, Job] = {}
    ok = 0
    for n, name in enumerate(cfg.get("sitemaps") or SITEMAPS, 1):
        if n > 1:
            time.sleep(delay)
        say(f"    remoterocketship sitemap {n}: {name}")
        try:
            body = get_bytes(BASE + name).decode("utf-8", "replace")
        except Exception as exc:
            if problems is not None:
                problems.append((name, f"{type(exc).__name__}: {exc}"[:200]))
            continue
        ok += 1
        for job in entries(body, since, places):
            jobs.setdefault(job.url, job)
    if not ok:
        raise RuntimeError("no Remote Rocketship sitemap could be read")
    candidates = [j for j in jobs.values() if title_ok(j) and not known(j)]
    say(f"    remoterocketship: {len(jobs)} jobs open to {', '.join(dict.fromkeys(places.values()))}; "
        f"{len(candidates)} new candidates")
    for i, job in enumerate(candidates, 1):
        time.sleep(delay)
        say(f"    remoterocketship job {i}/{len(candidates)}: {job.title[:60]}")
        try:
            enrich(job, job_posting(get_bytes(job.url).decode("utf-8", "replace")))
        except Exception:
            pass  # no ad text: can't pass the required words; shows as a near miss
    return list(jobs.values())
