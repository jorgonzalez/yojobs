"""Company career pages through the official public job-board APIs of the
applicant-tracking systems most tech companies use:

  greenhouse  https://boards-api.greenhouse.io/v1/boards/<id>/jobs
  lever       https://api.lever.co/v0/postings/<id>?mode=json
  ashby       https://api.ashbyhq.com/posting-api/job-board/<id>

config.yaml:
  companies:
    enabled: true
    boards: ["greenhouse:gitlab", "ashby:n8n", "lever:sysdig"]

Greenhouse lists have no description, so it is fetched only for jobs whose title +
location already match. Lever and Ashby include descriptions and an explicit work
mode (remote / hybrid / on-site), which we use as the remote flag.
"""
from __future__ import annotations

import time

from ..http import get_json
from ..models import Job, from_timestamp, parse_iso, strip_html
from ..progress import say

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


def fetch(cfg, since):
    title_ok = cfg.get("_title_ok") or (lambda job: True)
    boards = cfg.get("boards") or []
    jobs, failed = [], []
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
            else:
                say(f"    companies: unknown system '{ats}' for {board}")
                continue
        except Exception as exc:  # one company's board must not stop the rest
            failed.append(board)
            say(f"    companies: {board} failed: {type(exc).__name__}: {exc}")
            continue
        for job in found:
            job.tags = [f"{ats}:{board}"]
        jobs.extend(found)
        time.sleep(0.3)
    if failed:
        say(f"    companies: {len(failed)} boards failed: {', '.join(failed)}")
    return jobs
