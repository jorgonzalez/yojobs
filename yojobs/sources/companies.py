"""Company career pages through the official public job-board APIs of the
applicant-tracking systems most tech companies use:

  greenhouse  https://boards-api.greenhouse.io/v1/boards/<id>/jobs
  lever       https://api.lever.co/v0/postings/<id>?mode=json
              ("eu:<id>": api.eu.lever.co, for companies on Lever's EU servers, jobs.eu.lever.co/<id>)
  ashby       https://api.ashbyhq.com/posting-api/job-board/<id>
  personio    https://<id>.jobs.personio.de/xml   (many German companies)
  recruitee   https://<id>.recruitee.com/api/offers/
  teamtailor  https://<id>.teamtailor.com/jobs.rss   (or a company's own career domain)
  pinpoint    https://<id>.pinpointhq.com/postings.json   (or a company's own career domain,
              e.g. "pinpoint:careers.admgroup.com"); no posting date, so new jobs are
              told apart by the seen list; the company name comes from the domain
  deel        https://jobs.deel.com/<id>   (Deel's job system: one page with every posting;
              Deel's own page lists jobs without text, so up to 5 fitting job pages are opened)

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

import dataclasses
import json
import random
import re
import time
import xml.etree.ElementTree as ET

from ..enrich import Blocked, fetch_page, next_stream
from ..http import get_bytes, get_json
from ..models import Job, from_timestamp, parse_iso, strip_html
from ..progress import say
from .rss import parse_rfc822

GH_LIST = "https://boards-api.greenhouse.io/v1/boards/{}/jobs"
GH_JOB = "https://boards-api.greenhouse.io/v1/boards/{}/jobs/{}"
LEVER = "https://api.lever.co/v0/postings/{}"
LEVER_EU = "https://api.eu.lever.co/v0/postings/{}"
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
    """board "<id>" (Lever's US servers) or "eu:<id>" (its EU servers)."""
    region, _, board = board.rpartition(":")
    jobs = []
    for j in get_json((LEVER_EU if region.lower() == "eu" else LEVER).format(board), {"mode": "json"}):
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


def _pinpoint_host(board: str) -> str:
    return board if "." in board else f"{board}.pinpointhq.com"


def _pinpoint_company(host: str) -> str:
    labels = host.lower().split(".")
    name = labels[0] if host.endswith(".pinpointhq.com") else (labels[-2] if len(labels) >= 2 else host)
    return name.replace("-", " ").title()


def _pinpoint(board):
    host = _pinpoint_host(board)
    jobs = []
    for j in get_json(f"https://{host}/postings.json").get("data") or []:
        loc = j.get("location") or {}
        place = ", ".join(dict.fromkeys(x for x in (loc.get("city"), loc.get("province"), loc.get("name")) if x))
        mode = j.get("workplace_type") or ""
        jobs.append(Job(
            source="companies",
            title=(j.get("title") or "").strip(),
            company=_pinpoint_company(host),
            url=j.get("url") or "",
            location=place,
            published=None,  # Pinpoint's feed has no posting date
            description=strip_html(" ".join(j.get(k) or "" for k in ("description", "key_responsibilities",
                                                                      "skills_knowledge_expertise"))),
            tags=[t for t in [((j.get("job") or {}).get("department") or {}).get("name")] if t],
            remote=_mode(mode),
            work_mode=j.get("workplace_type_text") or mode,
        ))
    return jobs


DEEL = "https://jobs.deel.com/{}"
DEEL_DETAILS_PER_BOARD = 5     # job pages opened per board and run (Deel's own page has no ad text)
DEEL_PAUSE = (2.0, 4.0)


_ROW = re.compile(rb"([0-9a-f]+):(T([0-9a-f]+),)?")


def _text_rows(stream: str) -> dict:
    """The Next.js stream's text rows, {id: text}. Rows are "<id>:<json>\\n" or
    "<id>:T<hex byte length>,<text>" (no newline after the text, so walk them in order)."""
    data, pos, out = stream.encode(), 0, {}
    while pos < len(data):
        m = _ROW.match(data, pos)
        if not m:  # not a row start: skip to the next line
            nl = data.find(b"\n", pos)
            if nl < 0:
                break
            pos = nl + 1
            continue
        if m.group(2):
            end = m.end() + int(m.group(3), 16)
            out[m.group(1).decode()] = data[m.end():end].decode("utf-8", "replace")
            pos = end
        else:
            nl = data.find(b"\n", m.end())
            if nl < 0:
                break
            pos = nl + 1
    return out


def _deel_text(texts: dict, ref) -> str:
    """A text reference ("$24") -> its text row; plain text stays as it is."""
    if not isinstance(ref, str):
        return ""
    return texts.get(ref[1:], "") if ref.startswith("$") else ref


def _deel_places(job: dict) -> str:
    places = []
    for jl in job.get("jobLocations") or []:
        loc = (jl or {}).get("location") or {}
        country = (loc.get("country") or {}).get("name") or ""
        group = loc.get("locationGroup")
        name = loc.get("name") or (group.get("name") if isinstance(group, dict) else "") or ""
        places.append(name if not country or name == country else f"{name}, {country}" if name else country)
    return "; ".join(dict.fromkeys(p for p in places if p))


def _deel_posting(p: dict, texts: dict, board: str, company: str) -> Job:
    """A posting record of Deel's job system (most companies' list pages, every job page)."""
    job = p.get("job") or {}
    mode = job.get("workArrangementEnum") or ""
    states = [((x or {}).get("currentState") or {}) for x in p.get("jobPostingPublications") or []]
    published = next((s.get("createdAt") for s in states if str(s.get("stateSlug") or "").startswith("published")), None)
    return Job(
        source="companies",
        title=(p.get("title") or "").strip(),
        company=company,
        url=f"{DEEL.format(board)}/job-details/{p.get('id')}/overview",
        location=_deel_places(job),
        published=parse_iso(published or p.get("createdAt")),
        description=strip_html(_deel_text(texts, p.get("richtextDescription"))),
        tags=[d["department"]["name"] for d in job.get("jobDepartments") or []
              if isinstance((d or {}).get("department"), dict) and d["department"].get("name")],
        remote=_mode(mode),
        work_mode=mode.lower().replace("_", "") if mode else "",
    )


def _decode_at(stream: str, key: str):
    """The JSON value right after `key` (e.g. '"jobPostings":'), or None."""
    i = stream.find(key)
    if i < 0:
        return None
    try:
        return json.JSONDecoder().raw_decode(stream, i + len(key))[0]
    except ValueError:
        return None


def _deel_company(html: str, board: str) -> str:
    m = re.search(r'"@type"\s*:\s*"Organization"\s*,\s*"name"\s*:\s*"([^"]+)"', html)
    return m.group(1) if m else board.replace("-", " ").title()


def _deel(board, title_ok=lambda job: False, known=lambda job: False, page=fetch_page):
    """Deel's job system, jobs.deel.com/<org> (its robots.txt allows these pages; /api/ is
    off-limits). Most companies' pages embed every posting with its text, places and work
    mode. Deel's own page is different: a list fed from Ashby (title, countries, date), so
    the job pages of fitting, unknown jobs are opened for the text and the work mode
    (without a title check, e.g. in tests, none are opened)."""
    html = get_bytes(DEEL.format(board)).decode("utf-8", "replace")
    stream = next_stream(html)
    company = _deel_company(html, board)
    postings = _decode_at(stream, '"jobPostings":')
    if isinstance(postings, list):
        texts = _text_rows(stream)
        return [_deel_posting(p, texts, board, company) for p in postings if isinstance(p, dict)]
    i = stream.find('"__component":"product.career-job-listing"')
    listing = _decode_at(stream[i:], '"jobs":') if i >= 0 else None
    if not isinstance(listing, list):
        raise ValueError("no job list found on the page")
    jobs = []
    for item in listing:
        a = (item or {}).get("attributes") or {}
        if a.get("is_listed") is False or not a.get("ashby_id"):
            continue
        jobs.append(Job(
            source="companies",
            title=(a.get("title") or "").strip(),
            company=company,
            url=f"{DEEL.format(board)}/job-details/{a['ashby_id']}/overview",
            location=", ".join(x for x in a.get("all_locations") or [a.get("location_name") or ""] if x),
            published=parse_iso(a.get("ashby_published_date")),
            description=strip_html(a.get("full_job_description") or ""),
            tags=[t for t in [a.get("team_name")] if t],
        ))
    opened = 0
    for job in jobs:
        # the list has countries but no work mode: open the page if the job would fit as remote
        if job.description or opened >= DEEL_DETAILS_PER_BOARD or known(job) \
                or not title_ok(dataclasses.replace(job, remote=True)):
            continue
        time.sleep(random.uniform(*DEEL_PAUSE))
        opened += 1
        try:
            page_stream = next_stream(page(job.url))
        except Blocked as exc:  # 403/429: no more job pages this run
            say(f"    companies: {board} job pages said {exc}; no more this run")
            break
        except Exception:  # one odd page leaves that job as it is
            continue
        p = _decode_at(page_stream, '"jobPosting":')
        if isinstance(p, dict):
            d = _deel_posting(p, _text_rows(page_stream), board, company)
            job.description = d.description
            job.remote, job.work_mode = d.remote, d.work_mode
            job.location = d.location or job.location
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
            elif ats == "pinpoint":
                found = _pinpoint(board)
            elif ats == "deel":
                found = _deel(board, title_ok, cfg.get("_known") or (lambda job: False))
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
