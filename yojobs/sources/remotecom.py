"""Remote.com job board (remote.com/jobs), from its search pages; robots.txt allows them.

For each term of the `only: [remotecom]` searches in searches.yaml (places are ignored:
the board is about remote work), fetch https://remote.com/jobs/all?query=<term> (20
results). Each page embeds its jobs as JSON: title, company, where they hire
(hiringLocation: "global" or a list of regions/countries), work mode, date, salary.

Only jobs that pass the title + place rules get their job page opened (one request
each) for the full ad (its schema.org JobPosting), used for the Kubernetes check and
the CV match. The search is loose (single words match), so the filters do the work.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
from typing import List

from ..http import get_bytes
from ..models import Job, parse_iso, strip_html
from ..progress import say

SEARCH = "https://remote.com/jobs/all?"
JOB = "https://remote.com/jobs/{company}/{slug}"
_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', re.S)
_RECORD = re.compile(r'\{"status":"published","title"')


def _page_data(page: str) -> str:
    """The app's embedded data, unescaped from its JavaScript string chunks."""
    return "".join(_CHUNK.findall(page)).encode().decode("unicode_escape", "ignore")


def records(page: str) -> List[dict]:
    blob, decoder, out = _page_data(page), json.JSONDecoder(), []
    for m in _RECORD.finditer(blob):
        try:
            out.append(decoder.raw_decode(blob, m.start())[0])
        except ValueError:
            continue
    return out


def _where(o: dict) -> str:
    hl = o.get("hiringLocation") or {}
    if hl.get("type") == "global":
        return "Worldwide"
    names = [(l.get("value") or {}).get("name") or "" for l in hl.get("includedLocations") or []]
    return ", ".join(n for n in names if n)


def _salary(o: dict) -> str:
    c = o.get("compensation") or {}
    lo, hi, cur = c.get("minimum"), c.get("maximum"), (c.get("currency") or {}).get("code", "")
    if lo and hi:  # amounts are in cents
        return f"{cur} {lo // 100:,}-{hi // 100:,}".strip()
    return ""


def to_job(o: dict) -> Job:
    company = o.get("companyProfile") or {}
    mode = (o.get("workplaceLocation") or {}).get("type") or ""
    return Job(
        source="remotecom",
        title=strip_html(o.get("title")),
        company=company.get("name") or "",
        url=JOB.format(company=company.get("slug") or "", slug=o.get("slug") or ""),
        location=_where(o),
        published=parse_iso(o.get("publishedAt")),
        tags=[t for t in [o.get("employmentType") or "", *(o.get("seniority") or [])] if t],
        salary=_salary(o),
        remote=True if mode == "remote" else False if mode in ("hybrid", "onsite") else None,
        work_mode=mode,
    )


def ad_text(page: str) -> str:
    """Full ad from a job page's schema.org JobPosting, '' if none."""
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            return strip_html(data.get("description") or "")
    return ""


def fetch(cfg, since):
    title_ok = cfg.get("_title_ok") or (lambda job: True)
    known = cfg.get("_known") or (lambda job: False)
    problems = cfg.get("_problems")
    delay = float(cfg.get("delay_seconds", 4))
    terms = list(dict.fromkeys(s["term"] for s in cfg.get("searches") or []))
    jobs, ok, n = {}, 0, 0
    for term in terms:
        if n:
            time.sleep(delay)
        n += 1
        say(f"    remotecom search {n}/{len(terms)}: \"{term}\"")
        try:
            page = get_bytes(SEARCH + urllib.parse.urlencode({"query": term})).decode("utf-8", "replace")
        except Exception as exc:  # one failed search must not stop the others
            if problems is not None:
                problems.append((term, f"{type(exc).__name__}: {exc}"[:200]))
            continue
        ok += 1
        for o in records(page):
            job = to_job(o)
            job.found_by = f"{term} · remote.com"
            jobs.setdefault(job.url, job)
    if n and not ok:
        raise RuntimeError(f"all {n} remote.com searches failed")
    # full ad only for jobs that can still match and aren't already known
    candidates = [j for j in jobs.values() if title_ok(j) and not known(j)]
    for i, job in enumerate(candidates, 1):
        time.sleep(delay)
        say(f"    remotecom ad {i}/{len(candidates)}: {job.title[:60]}")
        try:
            job.description = ad_text(get_bytes(job.url).decode("utf-8", "replace"))
        except Exception:
            pass  # no text: the job can't pass the required words, and shows as a near miss
    return list(jobs.values())
