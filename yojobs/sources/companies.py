"""Company career pages through the official public job-board APIs of the
applicant-tracking systems most tech companies use:

  greenhouse  https://boards-api.greenhouse.io/v1/boards/<id>/jobs
  lever       https://api.lever.co/v0/postings/<id>?mode=json
  ashby       https://api.ashbyhq.com/posting-api/job-board/<id>
  personio    https://<id>.jobs.personio.de/xml   (many German companies)
  recruitee   https://<id>.recruitee.com/api/offers/
  teamtailor  https://<id>.teamtailor.com/jobs.rss   (or a company's own career domain)

Not supported: SmartRecruiters (its API's robots.txt only allows LinkedIn's bot)
and Workable (rate-limits even a handful of requests).

config.yaml:
  companies:
    enabled: true
    boards: ["greenhouse:gitlab", "ashby:n8n", "lever:sysdig"]

Greenhouse lists have no description, so it is fetched only for jobs whose title +
location already match. Lever, Ashby, Personio and Recruitee include descriptions;
Lever, Ashby and Recruitee also state the work mode (remote / hybrid / on-site),
which we use as the remote flag. Personio only has the office text
("Berlin / 100% remote möglich"), so remote is decided from that.
"""
from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET

from ..http import get_bytes, get_json
from ..models import Job, from_timestamp, parse_iso, strip_html
from ..progress import say
from .rss import parse_rfc822

GH_LIST = "https://boards-api.greenhouse.io/v1/boards/{}/jobs"
GH_JOB = "https://boards-api.greenhouse.io/v1/boards/{}/jobs/{}"
LEVER = "https://api.lever.co/v0/postings/{}"
ASHBY = "https://api.ashbyhq.com/posting-api/job-board/{}"


def _mode(value):
    v = (value or "").lower().replace("-", "").replace("_", "")
    if v == "remote":
        return True
    if v in ("hybrid", "onsite"):
        return False
    return None  # unspecified: decided from the location text


def _greenhouse(board, title_ok):
    jobs = []
    for j in get_json(GH_LIST.format(board)).get("jobs", []):
        jobs.append(Job(
            source="companies",
            title=j.get("title") or "",
            company=j.get("company_name") or board,
            url=j.get("absolute_url") or "",
            location=(j.get("location") or {}).get("name") or "",
            published=parse_iso(j.get("first_published")) or parse_iso(j.get("updated_at")),
        ))
        jobs[-1]._gh = (board, j.get("id"))
    for job in jobs:
        if title_ok(job):
            time.sleep(0.3)
            detail = get_json(GH_JOB.format(*job._gh))
            job.description = strip_html(strip_html(detail.get("content") or ""))  # content is escaped HTML
    return jobs


def _lever(board):
    jobs = []
    for j in get_json(LEVER.format(board), {"mode": "json"}):
        cats = j.get("categories") or {}
        locs = cats.get("allLocations") or [cats.get("location") or ""]
        jobs.append(Job(
            source="companies",
            title=j.get("text") or "",
            company=board.replace("-", " ").title(),
            url=j.get("hostedUrl") or "",
            location=", ".join(l for l in locs if l),
            published=from_timestamp((j.get("createdAt") or 0) // 1000),
            description=" ".join(x for x in [j.get("descriptionPlain"), j.get("additionalPlain"),
                                             " ".join(strip_html(l.get("content")) for l in j.get("lists") or [])] if x),
            remote=_mode(j.get("workplaceType")),
            work_mode=j.get("workplaceType") or "",
        ))
    return jobs


def _ashby(board):
    jobs = []
    for j in get_json(ASHBY.format(board)).get("jobs", []):
        if j.get("isListed") is False:
            continue
        locs = [j.get("location") or ""] + [s.get("location") or "" for s in j.get("secondaryLocations") or []]
        country = (((j.get("address") or {}).get("postalAddress") or {}).get("addressCountry")) or ""
        location = ", ".join(dict.fromkeys(l for l in locs + [country] if l))
        jobs.append(Job(
            source="companies",
            title=j.get("title") or "",
            company=board.replace("-", " ").title(),
            url=j.get("jobUrl") or "",
            location=location,
            published=parse_iso(j.get("publishedAt")),
            description=j.get("descriptionPlain") or "",
            remote=_mode(j.get("workplaceType")),
            work_mode=j.get("workplaceType") or "",
        ))
    return jobs


def _personio(board):
    """Personio XML feed. A board may be "name" (jobs.personio.de) or "name.com"."""
    name, _, tld = board.partition(".")
    host = f"https://{name}.jobs.personio.{tld or 'de'}"
    # English where the ad has an English version; otherwise the ad's own language
    # (asking for English returns no text for German-only ads)
    def descriptions(params):
        root = ET.fromstring(get_bytes(f"{host}/xml", params))
        return root, {(pos.findtext("id") or "").strip(): " ".join(
            f"{(d.findtext('name') or '').strip()}: {strip_html(d.findtext('value') or '')}"
            for d in pos.iter("jobDescription") if (d.findtext("value") or "").strip())
            for pos in root.iter("position")}
    root, english = descriptions({"language": "en"})
    original = None
    jobs = []
    for pos in root.iter("position"):
        text = lambda tag: (pos.findtext(tag) or "").strip()
        offices = [text("office")] + [(o.text or "").strip() for o in pos.iter("additionalOffice")]
        description = english.get(text("id"), "")
        if not description:
            if original is None:
                time.sleep(0.3)
                original = descriptions({})[1]
            description = original.get(text("id"), "")
        jobs.append(Job(
            source="companies",
            title=text("name"),
            company=text("subcompany") or name.replace("-", " ").title(),
            url=f"{host}/job/{text('id')}?language=en",
            location=", ".join(dict.fromkeys(o for o in offices if o)),
            published=parse_iso(text("createdAt")),
            description=description,
            tags=[t for t in (text("department"), text("seniority"), text("keywords")) if t],
        ))
    return jobs


_TT = "{https://teamtailor.com/locations}"
_TT_MODES = {"fully": (True, "remote"), "remote": (True, "remote"), "hybrid": (False, "hybrid"),
             "none": (False, "onsite"), "onsite": (False, "onsite")}


def _teamtailor(board):
    """Teamtailor career site feed. A board is "acme" (acme.teamtailor.com) or a
    company's own career domain ("careers.acme.com"), which serves the same feed."""
    host = board if "." in board else f"{board}.teamtailor.com"
    root = ET.fromstring(get_bytes(f"https://{host}/jobs.rss"))
    channel = root.find("channel")
    company = (channel.findtext("title") if channel is not None else "") or board
    company = re.sub(r"(?i)\s*[-–|]?\s*(career|careers|jobs|karriere)\b.*$", "", company).strip() or board
    jobs = []
    for item in root.iter("item"):
        places = []
        for loc in item.iter(_TT + "location"):
            places += [loc.findtext(_TT + "city") or loc.findtext(_TT + "name") or "", loc.findtext(_TT + "country") or ""]
        remote, mode = _TT_MODES.get((item.findtext("remoteStatus") or "").strip().lower(), (None, ""))
        jobs.append(Job(
            source="companies",
            title=(item.findtext("title") or "").strip(),
            company=company,
            url=(item.findtext("link") or "").strip(),
            location=", ".join(dict.fromkeys(p for p in places if p)) or ("Remote" if remote else ""),
            published=parse_rfc822(item.findtext("pubDate")),
            description=strip_html(item.findtext("description") or ""),
            tags=[t for t in (item.findtext(_TT + "department"), item.findtext(_TT + "role")) if t],
            remote=remote,
            work_mode=mode,
        ))
    return jobs


def _recruitee(board):
    jobs = []
    for o in get_json(f"https://{board}.recruitee.com/api/offers/").get("offers", []):
        if o.get("remote") and not (o.get("hybrid") or o.get("on_site")):
            remote, mode = True, "remote"
        elif o.get("hybrid"):
            remote, mode = False, "hybrid"
        elif o.get("on_site"):
            remote, mode = False, "onsite"
        else:
            remote, mode = None, ""
        places = [o.get("location") or ""] + [l.get("name") or "" for l in o.get("locations") or []] \
            + [o.get("city") or "", o.get("country") or ""]
        jobs.append(Job(
            source="companies",
            title=o.get("title") or "",
            company=o.get("company_name") or board.title(),
            url=o.get("careers_url") or "",
            location=", ".join(dict.fromkeys(p for p in places if p)),
            published=parse_iso((o.get("published_at") or o.get("created_at") or "").replace(" UTC", "+00:00")),
            description=strip_html(" ".join(x for x in (o.get("description"), o.get("requirements")) if x)),
            tags=[t for t in (o.get("department"), o.get("category_code")) if t],
            remote=remote,
            work_mode=mode,
        ))
    return jobs


def fetch(cfg, since):
    title_ok = cfg.get("_title_ok") or (lambda job: True)
    boards = cfg.get("boards") or []
    jobs, failed = [], []
    problems = cfg.get("_problems")  # list provided by the runner: (board, error) per failed board
    for n, entry in enumerate(boards, 1):
        ats, _, board = str(entry).partition(":")
        say(f"    companies {n}/{len(boards)}: {board} ({ats})")
        try:
            if ats == "greenhouse":
                found = _greenhouse(board, title_ok)
            elif ats == "lever":
                found = _lever(board)
            elif ats == "ashby":
                found = _ashby(board)
            elif ats == "personio":
                found = _personio(board)
            elif ats == "recruitee":
                found = _recruitee(board)
            elif ats == "teamtailor":
                found = _teamtailor(board)
            else:
                say(f"    companies: unknown system '{ats}' for {board}")
                continue
        except Exception as exc:  # one company's board must not stop the rest
            failed.append(board)
            if problems is not None:
                problems.append((f"{ats}:{board}", f"{type(exc).__name__}: {exc}"[:200]))
            say(f"    companies: {board} failed: {type(exc).__name__}: {exc}")
            continue
        for job in found:
            job.tags = [f"{ats}:{board}"]
        jobs.extend(found)
        time.sleep(0.3)
    if failed:
        say(f"    companies: {len(failed)} boards failed: {', '.join(failed)}")
    return jobs
