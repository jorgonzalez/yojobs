"""StepStone (stepstone.de), from its search result pages.

Uses the terms in config/searches.yaml, in the places that are cities (e.g.
Berlin): one page per term, https://www.stepstone.de/jobs/<term>/in-<city>, which
robots.txt allows (its API, the "home office" section and most URLs with
parameters are disallowed, so there are no remote searches).

Each page embeds its ~25 results as JSON (title, company, location, date, a
~500-character excerpt, skills). Job pages aren't opened: they timed out when
tried, so ad_must_mention is checked on the excerpt and skills only; jobs that
miss it show up in the weekly near misses.

This reads data embedded in StepStone's web page, not a feed, so a redesign can
break it; the health warnings will say so.
"""
from __future__ import annotations

import json
import re
import time
from typing import List

from ..http import get_bytes
from ..models import Job, parse_iso, strip_html
from ..progress import say

SEARCH = "https://www.stepstone.de/jobs/{term}/in-{city}"
_STATE = re.compile(r"window\.__PRELOADED_STATE__\[[^\]]*\]\s*=\s*")


def slug(text: str) -> str:
    """"SRE Team Lead" -> "sre-team-lead", "München" -> "muenchen"."""
    text = text.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def records(page: str) -> List[dict]:
    """Job records from the JSON objects embedded in a search page."""
    decoder, out = json.JSONDecoder(), []
    for m in _STATE.finditer(page):
        try:
            obj, _ = decoder.raw_decode(page, m.end())
        except ValueError:
            continue
        stack = [obj]
        while stack:
            o = stack.pop()
            if isinstance(o, dict):
                if "title" in o and "companyName" in o and "stellenangebote--" in str(o.get("url", "")):
                    out.append(o)
                stack.extend(o.values())
            elif isinstance(o, list):
                stack.extend(o)
    return out


def to_job(o: dict) -> Job:
    skills = [str(s.get("name", s)) if isinstance(s, dict) else str(s) for s in (o.get("skills") or [])]
    excerpt = strip_html(o.get("textSnippet"))
    wfh = str(o.get("workFromHome") or "")
    return Job(
        source="stepstone",
        title=strip_html(o.get("title")),
        company=o.get("companyName") or "",
        url=str(o.get("url") or "").split("?")[0],
        location=o.get("location") or "",
        published=parse_iso(o.get("datePosted")),
        description=" ".join(x for x in [excerpt, "Skills: " + ", ".join(skills) if skills else ""] if x),
        tags=skills,
        remote=False,  # city searches; the "home office" section is off limits
        work_mode="hybrid" if wfh == "2" else "",  # "2" = partly from home; other values unclear
        source_notes=["excerpt only"],
    )


def fetch(cfg, since):
    cities: List[str] = []
    terms: List[str] = []
    for s in cfg.get("searches") or []:
        if s.get("remote"):
            continue  # no remote searches on StepStone
        if s.get("location") and s["location"] not in cities:
            cities.append(s["location"])
        if s["term"] not in terms:
            terms.append(s["term"])
    problems = cfg.get("_problems")
    delay = float(cfg.get("delay_seconds", 4))
    jobs, ok, n = {}, 0, 0
    for city in cities:
        for term in terms:
            if n:
                time.sleep(delay)
            n += 1
            say(f"    stepstone {n}/{len(cities) * len(terms)}: \"{term}\" in {city}")
            url = SEARCH.format(term=slug(term), city=slug(city))
            try:
                page = get_bytes(url).decode("utf-8", "replace")
            except Exception as exc:  # one failed search must not stop the others
                if problems is not None:
                    problems.append((f"{term} in {city}", f"{type(exc).__name__}: {exc}"[:200]))
                say(f"    stepstone: \"{term}\" failed: {type(exc).__name__}: {exc}")
                continue
            ok += 1
            for o in records(page):
                job = to_job(o)
                jobs.setdefault(job.url, job)
    if n and not ok:
        raise RuntimeError(f"all {n} StepStone searches failed")
    return list(jobs.values())
