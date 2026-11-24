"""Job details from the ad itself, for sources that only give a title.

Welcome to the Jungle (sitemaps), StartupMap (no descriptions) and 4dayweek (RSS without
location) list jobs without the ad text, so the Kubernetes check can't be made, the CV
match only sees the title, and 4dayweek jobs have no location at all (an empty location
counts as "remote, no restriction", so a London hybrid job got through).

For jobs that already pass the title (and, where known, the place) check, open the ad
once and fill in what's missing:
  - links to Greenhouse, Lever or Ashby ads (StartupMap) -> those systems' public APIs
  - 4dayweek job pages -> the job data embedded in the page (location, work mode, text)
  - any other page (Welcome to the Jungle, company sites) -> its schema.org JobPosting

Only empty fields are filled (a source's location / work mode wins). At most
MAX_PER_RUN ads per run, a pause between pages, and a site answering 403/429 is not
asked again in that run; a failed lookup just leaves the job as it was ("not verified").
"""
from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .http import TIMEOUT, USER_AGENT, get_json
from .models import Job, strip_html
from .progress import note, say

MAX_PER_RUN = 10
PAUSE = (2.0, 4.0)        # seconds between ads
MAX_BYTES = 3_000_000


@dataclass
class Details:
    description: str = ""
    location: str = ""
    remote: Optional[bool] = None
    work_mode: str = ""


class Blocked(Exception):
    """The site said 403/429: don't ask it again this run."""


def needs(job: Job) -> bool:
    return not job.has_description


def _mode(value: str) -> Optional[bool]:
    v = (value or "").lower().replace("-", "").replace("_", "")
    if v in ("remote", "telecommute", "fullyremote"):
        return True
    if v in ("hybrid", "onsite", "office", "inoffice"):
        return False
    return None


def fetch_page(url: str) -> str:
    """One attempt, no retries: a 403/429 stops lookups at that site for this run."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read(MAX_BYTES).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise Blocked(f"HTTP {exc.code}") from exc
        raise


# --- applicant tracking systems (public APIs) ----------------------------------

def _greenhouse(board: str, job_id: str) -> Details:
    d = get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}")
    return Details(description=strip_html(strip_html(d.get("content") or "")),   # escaped HTML
                   location=(d.get("location") or {}).get("name") or "")


def _lever(host: str, board: str, job_id: str) -> Details:
    api = "api.eu.lever.co" if host.startswith("jobs.eu.") else "api.lever.co"
    d = get_json(f"https://{api}/v0/postings/{board}/{job_id}")
    cats = d.get("categories") or {}
    lists = " ".join(f"{x.get('text', '')}: {strip_html(x.get('content') or '')}" for x in d.get("lists") or [])
    return Details(description=" ".join(x for x in (d.get("descriptionPlain"), lists, d.get("additionalPlain")) if x),
                   location=", ".join(cats.get("allLocations") or [cats.get("location") or ""]),
                   remote=_mode(d.get("workplaceType")), work_mode=d.get("workplaceType") or "")


def _ashby(board: str, job_id: str) -> Optional[Details]:
    d = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}")
    j = next((j for j in d.get("jobs") or [] if job_id in (j.get("id"), (j.get("jobUrl") or "").rstrip("/").rsplit("/", 1)[-1])), None)
    if j is None:
        return None
    locs = [j.get("location") or ""] + [s.get("location") or "" for s in j.get("secondaryLocations") or []]
    return Details(description=j.get("descriptionPlain") or "", location=", ".join(dict.fromkeys(l for l in locs if l)),
                   remote=_mode(j.get("workplaceType")), work_mode=j.get("workplaceType") or "")


_ATS = [
    (re.compile(r"^https?://(?:job-)?boards(?:\.eu)?\.greenhouse\.io/([^/?#]+)/jobs/(\d+)"),
     lambda m: _greenhouse(m.group(1), m.group(2))),
    (re.compile(r"^https?://(jobs(?:\.eu)?\.lever\.co)/([^/?#]+)/([0-9a-f-]{36})"),
     lambda m: _lever(m.group(1), m.group(2), m.group(3))),
    (re.compile(r"^https?://jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-f-]{36})"),
     lambda m: _ashby(urllib.parse.unquote(m.group(1)), m.group(2))),
]


# --- pages -----------------------------------------------------------------------

def _places(value) -> List[str]:
    out = []
    for place in value if isinstance(value, list) else [value] if value else []:
        addr = (place or {}).get("address") or {} if isinstance(place, dict) else {}
        if isinstance(addr, str):
            out.append(addr.strip())
            continue
        parts = [str(addr.get(k) or "").strip() for k in ("addressLocality", "addressRegion", "addressCountry")]
        text = ", ".join(p for p in parts if p)
        if text:
            out.append(text)
    return out


def job_posting(html: str) -> Optional[Details]:
    """Details from the page's schema.org JobPosting (JSON-LD), or None."""
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            data = json.loads(m.group(1).strip())
        except ValueError:
            continue
        items = data if isinstance(data, list) else data.get("@graph") or [data] if isinstance(data, dict) else []
        for d in items:
            if not isinstance(d, dict) or d.get("@type") != "JobPosting":
                continue
            remote = True if str(d.get("jobLocationType") or "").upper() == "TELECOMMUTE" else None
            where = _places(d.get("jobLocation"))
            regions = [((r or {}).get("name") or "") for r in (d.get("applicantLocationRequirements") or [])
                       if isinstance(r, dict)] if isinstance(d.get("applicantLocationRequirements"), list) else []
            if remote and regions:
                where = [f"Remote: {', '.join(r for r in regions if r)}"] + where
            return Details(description=strip_html(strip_html(d.get("description") or "")),
                           location="; ".join(dict.fromkeys(where)), remote=remote,
                           work_mode="remote" if remote else "")
    return None


def next_stream(html: str) -> str:
    """The Next.js data stream: the strings passed to self.__next_f.push([1, "..."])."""
    out = []
    for s in re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html):
        try:
            out.append(json.loads(s))
        except ValueError:
            pass
    return "".join(out)


def fourdayweek(html: str, url: str) -> Optional[Details]:
    """4dayweek job page: the job object embedded in the page (work_arrangement, locations,
    description = a reference to a text chunk "<id>:T<hex length>,<text>")."""
    stream = next_stream(html)
    slug = urllib.parse.urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    i = stream.find(f'"slug":"{slug}"')
    start = stream.rfind('{"id"', 0, i) if i >= 0 else -1
    if start < 0:
        return None
    try:
        job, _ = json.JSONDecoder().raw_decode(stream, start)
    except ValueError:
        return None
    if not isinstance(job, dict):
        return None
    places = []
    for loc in job.get("locations") or []:
        text = ", ".join(x for x in (loc.get("city"), loc.get("state"), loc.get("country")) if x) or loc.get("continent") or ""
        if text:
            places.append(text)
    desc = job.get("description") or ""
    if isinstance(desc, str) and desc.startswith("$"):
        m = re.search(rf"(?:^|\n){re.escape(desc[1:])}:T([0-9a-f]+),", stream)
        desc = ""
        if m:
            desc = stream[m.end():].encode()[:int(m.group(1), 16)].decode("utf-8", "replace")
    mode = job.get("work_arrangement") or ""
    return Details(description=strip_html(desc), location="; ".join(dict.fromkeys(places)) or job.get("location_raw") or "",
                   remote=_mode(mode), work_mode=mode)


_PAGES: List = [
    (re.compile(r"^https?://(?:www\.)?4dayweek\.io/job/"), fourdayweek),
]


# --- per run -----------------------------------------------------------------------

class Enricher:
    """Fills in jobs for one run: limit, pauses, and sites that said 403/429 are skipped."""

    def __init__(self, limit: int = MAX_PER_RUN, pause=PAUSE, page: Callable[[str], str] = fetch_page):
        self.limit, self.pause, self.page = limit, pause, page
        self.done = 0
        self.blocked: Dict[str, str] = {}

    def details(self, url: str) -> Optional[Details]:
        for pattern, reader in _ATS:
            m = pattern.match(url)
            if m:
                return reader(m)
        html = self.page(url)
        for pattern, reader in _PAGES:
            if pattern.match(url):
                return reader(html, url)
        return job_posting(html)

    def enrich(self, job: Job) -> str:
        """Fill in the job's missing details; -> what happened (for the log)."""
        host = urllib.parse.urlparse(job.url).netloc.lower()
        if not host:
            return ""
        if host in self.blocked:
            return f"skipped ({host} said {self.blocked[host]} earlier this run)"
        if self.done >= self.limit:
            return f"skipped (limit of {self.limit} ads per run)"
        if self.done:
            time.sleep(random.uniform(*self.pause))
        self.done += 1
        try:
            d = self.details(job.url)
        except Blocked as exc:
            self.blocked[host] = str(exc)
            note(f"details: {host} said {exc}; no more lookups there this run")
            return f"failed ({exc})"
        except Exception as exc:  # one odd page must never stop the run
            return f"failed ({type(exc).__name__}: {str(exc)[:80]})"
        if d is None or not (d.description or d.location or d.remote is not None):
            return "nothing found"
        filled = []
        if d.description:
            job.description, job.has_description = d.description, True
            filled.append("description")
        if d.location and not job.location:
            job.location = d.location
            filled.append(f"location {d.location[:60]}")
        if d.remote is not None and job.remote is None:
            job.remote = d.remote
            if d.work_mode and not job.work_mode:
                job.work_mode = d.work_mode
            filled.append(f"work mode {d.work_mode or ('remote' if d.remote else 'not remote')}")
        return ", ".join(filled) or "nothing new"


def enrich_jobs(jobs: List[Job], wanted: Callable[[Job], bool], enricher: Enricher) -> int:
    """Fill in `jobs` that need details and pass `wanted` (title/place, not already known);
    -> how many were looked up."""
    n = 0
    for job in jobs:
        if needs(job) and wanted(job):
            n += 1
            say(f"    details {n}: {job.title[:50]} ({urllib.parse.urlparse(job.url).netloc}): {enricher.enrich(job)}")
    return n
