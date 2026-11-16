"""Keyword filtering and scoring.

A profile in config.yaml supports:
  any_of:   OR keywords. Each distinct match adds +1 to the job's score.
  groups:   named keyword lists, e.g. {role: [...], area: [...]}. The job must
            match at least one word from EVERY group (in match_in). Group
            matches also add to the score.
  all_of:   AND keywords. Every one must appear, otherwise the job is dropped.
  all_of_in: where all_of is searched (default: title, description, tags).
  none_of:  exclusion keywords. Any match drops the job.
  match_in: where any_of/all_of are searched: title, description, tags, company.
  exclude_in: where none_of is searched (default: same as match_in).
  min_score: minimum number of distinct any_of matches (default 1).
  location_any: allowed places. A job passes if its location mentions one of them,
             or if its location is empty / plain "Remote" (no restriction).
             Jobs restricted elsewhere (e.g. "USA Only", "UK") are dropped.

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


_GENERIC_LOC = re.compile(r"\b(fully|100%|remote|work from home|wfh|only|job|position)\b|[^\w]", re.IGNORECASE)


def location_ok(location: str, allowed: List[str]) -> bool:
    """Keep the job if its location mentions an allowed place (e.g. Germany, Europe,
    Worldwide), or if it is empty / just "Remote" with no country restriction.
    Anything else (e.g. "USA Only", "Remote - UK", "Brazil") is dropped.
    An empty allowed list disables the location filter."""
    if not allowed:
        return True
    if _hits(allowed, location):
        return True
    return _GENERIC_LOC.sub("", location or "") == ""


def title_ok(job: Job, profile: dict) -> bool:
    """Everything except the required (all_of) words: lets sources skip fetching
    descriptions for jobs that can never match."""
    return apply(job, profile, check_all_of=False)


def apply(job: Job, profile: dict, check_all_of: bool = True) -> bool:
    """Return True if the job passes the profile; sets job.score / job.matched."""
    match_in = profile.get("match_in") or ["title"]
    exclude_in = profile.get("exclude_in") or match_in
    text = _text(job, match_in)

    if _hits(profile.get("none_of") or [], _text(job, exclude_in)):
        return False

    all_of = profile.get("all_of") or []
    all_text = _text(job, profile.get("all_of_in") or ["title", "description", "tags"])
    if check_all_of and len(_hits(all_of, all_text)) != len(all_of):
        return False

    if not location_ok(job.location, profile.get("location_any") or []):
        return False

    # groups: every group needs at least one match (AND between groups, OR inside)
    groups = profile.get("groups") or {}
    group_hits = []
    for words in groups.values():
        hits = _hits(words or [], text)
        if not hits:
            return False
        group_hits += [h for h in hits if h not in group_hits]

    matched = _hits(profile.get("any_of") or [], text)
    matched += [h for h in group_hits if h not in matched]
    if profile.get("any_of") and len(matched) < profile.get("min_score", 1):
        return False

    job.matched = matched
    job.score = len(matched)
    return True
