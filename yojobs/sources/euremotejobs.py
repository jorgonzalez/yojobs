"""EU Remote Jobs (euremotejobs.com). Every job there is remote.

The owner disabled the job RSS feed and REST API, so we read the homepage (latest
~60 jobs; robots.txt allows it, only search-filter URLs are disallowed). Each card
gives title, company, allowed region and date. Only cards whose title + region
already match are opened (usually 0-3 per run, with pauses) to read the full
description from the page's JobPosting data, for the Kubernetes check.
"""
from __future__ import annotations

import html
import json
import re
import time

from ..http import get_bytes
from ..models import Job, parse_iso, strip_html
from ..progress import say

HOME = "https://euremotejobs.com/"
_CARD = re.compile(r'<a href="(https://euremotejobs\.com/job/[^"]+)" class="job-card-link">(.*?)</a>', re.S)
_LDJSON = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S)


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def _first(pattern: str, block: str) -> str:
    m = re.search(pattern, block, re.S)
    return _text(m.group(1)) if m else ""


def parse_cards(page: str):
    jobs = []
    for url, block in _CARD.findall(page):
        location = _first(r'class="meta-item meta-location">(.*?)</div>', block)
        if location.lower() == "location not specified":
            location = ""
        jobs.append(Job(
            source="euremotejobs",
            title=_first(r'class="job-title">(.*?)</h2>', block),
            company=_first(r'class="company-name">(.*?)</div>', block),
            url=url,
            location=location,
            published=parse_iso(_first(r'<time datetime="([^"]+)"', block) or None),
            tags=[t for t in [_first(r'class="meta-item meta-category">(.*?)</div>', block)] if t],
            remote=True,  # remote-only board
        ))
    return jobs


def _description(page: str) -> str:
    for block in _LDJSON.findall(page):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data])
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "JobPosting":
                return strip_html(item.get("description") or "")
    return ""


def fetch(cfg, since):
    title_ok = cfg.get("_title_ok") or (lambda job: True)
    jobs = list({j.url: j for j in parse_cards(get_bytes(HOME).decode("utf-8", "replace"))}.values())
    matches = [j for j in jobs if (j.published is None or j.published >= since) and title_ok(j)]
    say(f"    euremotejobs: {len(jobs)} jobs on the homepage, {len(matches)} match title + region")
    for n, job in enumerate(matches[: cfg.get("max_pages", 10)]):
        time.sleep(cfg.get("delay_seconds", 3))
        try:
            job.description = _description(get_bytes(job.url).decode("utf-8", "replace"))
        except Exception as exc:
            say(f"    euremotejobs: could not read {job.url}: {exc}")
    return jobs
