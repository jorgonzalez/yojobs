"""Keyword filtering and scoring.

A profile in config.yaml supports:
  any_of:   OR keywords. Each distinct match adds +1 to the job's score.
  all_of:   AND keywords. Every one must appear, otherwise the job is dropped.
  all_of_in: where all_of is searched (default: title, description, tags).
  none_of:  exclusion keywords. Any match drops the job.
  match_in: where any_of/all_of are searched: title, description, tags, company.
  exclude_in: where none_of is searched (default: same as match_in).
  min_score: minimum number of distinct any_of matches (default 1).
  location_any / location_none: keywords checked against the job's location
             (jobs with an empty location pass location_any).

Matching is case-insensitive on whole words; a space in a keyword also matches
a hyphen, so "team lead" matches "Team-Lead".
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Pattern

from .models import Job

_cache: Dict[str, Pattern] = {}


def _pattern(keyword: str) -> Pattern:
    if keyword not in _cache:
        parts = [re.escape(p) for p in keyword.strip().split()]
        _cache[keyword] = re.compile(r"(?<!\w)" + r"[\s\-]+".join(parts) + r"(?!\w)", re.IGNORECASE)
    return _cache[keyword]


def _text(job: Job, fields: Iterable[str]) -> str:
    chunks = []
    for f in fields:
        v = getattr(job, f, "")
        chunks.append(" ".join(v) if isinstance(v, list) else (v or ""))
    return "\n".join(chunks)


def _hits(keywords: List[str], text: str) -> List[str]:
    return [k for k in keywords if _pattern(k).search(text)]


def apply(job: Job, profile: dict) -> bool:
    """Return True if the job passes the profile; sets job.score / job.matched."""
    match_in = profile.get("match_in") or ["title"]
    exclude_in = profile.get("exclude_in") or match_in
    text = _text(job, match_in)

    if _hits(profile.get("none_of") or [], _text(job, exclude_in)):
        return False

    all_of = profile.get("all_of") or []
    all_text = _text(job, profile.get("all_of_in") or ["title", "description", "tags"])
    if len(_hits(all_of, all_text)) != len(all_of):
        return False

    loc_any = profile.get("location_any") or []
    if loc_any and job.location and not _hits(loc_any, job.location):
        return False
    if job.location and _hits(profile.get("location_none") or [], job.location):
        return False

    matched = _hits(profile.get("any_of") or [], text)
    if profile.get("any_of") and len(matched) < profile.get("min_score", 1):
        return False

    job.matched = matched
    job.score = len(matched)
    return True
