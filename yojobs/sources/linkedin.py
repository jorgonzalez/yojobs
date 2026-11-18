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
import time
from datetime import datetime, timezone
from types import SimpleNamespace

from ..models import Job, strip_html, to_utc
from ..progress import is_verbose, note, say
from ..remote import remote_evidence, remote_region


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


class Throttle:
    """Set when LinkedIn answers 429 (too many requests) to any request of this run."""

    def __init__(self):
        self.hit = False
        self.at = ""


def gentle_session_factory(create_session, throttle: Throttle):
    """Wrap jobdrop's create_session: no retries on 429 and no obeying Retry-After
    (jobdrop's default retried 429s 3x with backoff, honouring LinkedIn's Retry-After,
    which stalled single searches for ~15 minutes), short retries for 5xx only, and
    a response hook that records any 429."""
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    def make(*args, **kwargs):
        kwargs["has_retry"] = False
        session = create_session(*args, **kwargs)
        retry = Retry(total=2, connect=2, read=1, status=2, status_forcelist=[500, 502, 503, 504],
                      backoff_factor=2, respect_retry_after_header=False, raise_on_status=False)
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        def record(response, *a, **k):
            if response.status_code == 429:
                throttle.hit = True
        session.hooks["response"].append(record)
        return session
    return make


def parse_job_page(page: str):
    """-> (description, location) from a public LinkedIn job page."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page, "html.parser")
    desc = soup.find("div", class_=lambda x: x and "show-more-less-html__markup" in x)
    loc = soup.find(class_=lambda x: x and "topcard__flavor--bullet" in x)
    return (strip_html(str(desc)) if desc else "", loc.get_text(" ", strip=True) if loc else "")


def job_page(session, job_id: str):
    """Fetch one public job page (the same single request jobdrop makes for the
    description); -> (description, location), ("", "") on any failure."""
    try:
        r = session.get(f"https://www.linkedin.com/jobs/view/{job_id}", timeout=10)
        if r.status_code != 200 or "linkedin.com/signup" in r.url:
            return "", ""
        return parse_job_page(r.text)
    except Exception:
        return "", ""


def rotated(searches: list, now: float = None) -> list:
    """Start at a different search each run (runs are >= 5 h apart), so if LinkedIn
    throttles a run and the rest are skipped, the next run covers them first."""
    if not searches:
        return []
    start = int((now if now is not None else time.time()) // (4 * 3600)) % len(searches)
    return searches[start:] + searches[:start]


def fetch(cfg, since):
    import jobdrop.linkedin as jl
    from jobdrop import scrape_jobs, set_logger_level  # heavy import, only when enabled
    from jobdrop.linkedin import LinkedIn
    from jobdrop.model import DescriptionFormat

    throttle = Throttle()
    original = jl.create_session
    jl.create_session = gentle_session_factory(original, throttle)
    try:
        return _fetch(cfg, since, scrape_jobs, set_logger_level, LinkedIn, DescriptionFormat, throttle)
    finally:
        jl.create_session = original


def _fetch(cfg, since, scrape_jobs, set_logger_level, LinkedIn, DescriptionFormat, throttle):
    problems = cfg.get("_problems")

    # jobdrop warnings would break the one-line status display in quiet mode
    set_logger_level(logging.WARNING if is_verbose() else logging.ERROR)
    hours_old = max(1, int((datetime.now(timezone.utc) - since).total_seconds() // 3600))
    title_ok = cfg.get("_title_ok") or (lambda job: True)

    jobs = {}
    searches = rotated(cfg.get("searches") or [])
    for i, s in enumerate(searches):
        if throttle.hit:
            msg = (f"LinkedIn said 'too many requests' (429) after {i}/{len(searches)} searches; "
                   f"skipped the other {len(searches) - i} this run (the next run starts with them)")
            note(f"linkedin: {msg}")
            if problems is not None:
                problems.append(("throttled", msg))
            break
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
            if throttle.hit:
                note(f"linkedin: 'too many requests' (429); skipped {len(candidates) - n} descriptions this run")
                break
            if n:
                time.sleep(random.uniform(2, 5))
            say(f"    linkedin description {n + 1}/{len(candidates)}: {job.title[:60]}")
            job.description, page_location = job_page(li.session, job._li_id)
            # Search cards sometimes have no location; an empty location would count as
            # "no restriction" for a remote job, so take the job page's location instead.
            if not job.location and page_location:
                job.location = page_location
    # Decide remote for every job from the wording, not LinkedIn's filter.
    for job in jobs.values():
        where = remote_evidence(job.title, job.description)
        job.remote = bool(where)
        if where == "description":
            job.source_notes = ["remote per description, check"]
        # Where the remote role may be done from, if the ad says it ("fully remote and
        # global", "remote within the EU"): checked by remote_regions like a location.
        region = remote_region(job.description) if job.remote else ""
        if region:
            job.location = f"{job.location} (remote: {region})" if job.location else f"Remote: {region}"
            job.source_notes = job.source_notes + [f"remote region from the ad: {region}, check"]
    if candidates:
        missing = sum(1 for j in candidates if not j.description)
        if missing:
            note(f"linkedin: {missing}/{len(candidates)} descriptions could not be fetched "
                 f"(possibly rate-limited); those jobs can't pass the all_of check")
    return list(jobs.values())
