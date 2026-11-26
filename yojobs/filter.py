"""Keyword filtering and scoring.

A profile in config.yaml supports:
  any_of:   OR keywords. Each distinct match adds +1 to the job's score.
  groups:   named keyword lists, e.g. {role: [...], area: [...]}. The job must
            match at least one word from EVERY group (in match_in). Group
            matches also add to the score.
  all_of:   AND keywords. Every one must appear, otherwise the job is dropped.
  all_of_in: where all_of is searched (default: title, description, tags).
            Jobs from sources without descriptions skip all_of and get a
            "<words> not verified" note instead.
  none_of:  exclusion keywords. Any match drops the job.
  match_in: where any_of/all_of are searched: title, description, tags, company.
  exclude_in: where none_of is searched (default: same as match_in).
  min_score: minimum number of distinct any_of matches (default 1).
  onsite_cities: on-site/hybrid jobs are only kept in these places (e.g. Berlin).
  remote_regions: remote jobs are kept if their location (where you may live)
             mentions one of these, or is empty / plain "Remote". "USA Only",
             "Remote - UK" or "Cork, Ireland" are dropped.

Matching is case-insensitive on whole words; a space in a keyword also matches
a hyphen, so "team lead" matches "Team-Lead". "Kubernetes|K8s" matches either.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Pattern

from . import language, workmode
from .models import Job

_cache: Dict[str, Pattern] = {}


def _pattern(keyword: str) -> Pattern:
    """Whole-word, case-insensitive; spaces also match hyphens; "a|b" means a or b."""
    if keyword not in _cache:
        alts = []
        for alt in keyword.split("|"):
            parts = [re.escape(p) for p in alt.strip().split()]
            alts.append(r"[\s\-]+".join(parts))
        _cache[keyword] = re.compile(r"(?<!\w)(?:" + "|".join(alts) + r")(?!\w)", re.IGNORECASE)
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
    """Region check for REMOTE jobs: keep if the location mentions an allowed region
    (e.g. Germany, Europe, Worldwide), or is empty / just "Remote" (no restriction).
    Anything else (e.g. "USA Only", "Remote - UK", "Cork, Ireland") is dropped.
    An empty allowed list disables the check."""
    if not allowed:
        return True
    if _hits(allowed, location):
        return True
    return _GENERIC_LOC.sub("", location or "") == ""


_REMOTE_WORDS = re.compile(r"\b(remote|anywhere|worldwide|work from home|wfh|distributed)\b", re.IGNORECASE)


_REMOTE_PLACE = re.compile(r"\bremote\b", re.IGNORECASE)
_OFFICE_PLACE = re.compile(r"\b(hybrid|on[\s-]?site|in[\s-]office)\b", re.IGNORECASE)


def is_remote(job: Job) -> bool:
    if job.remote is False and job.work_mode.lower().replace("-", "") == "hybrid" \
            and _REMOTE_PLACE.search(job.location) and not _OFFICE_PLACE.search(job.location):
        # a "hybrid" tag on a job whose location says "Remote Germany" (vivenu on Lever):
        # the location is the more specific of the two. An ad that asks for office days
        # is still caught by place_ok's office_required check.
        return True
    if job.remote is not None:
        return job.remote
    return not job.location or bool(_REMOTE_WORDS.search(job.location))


def place_ok(job: Job, profile: dict) -> bool:
    """On-site/hybrid jobs: only in `onsite_cities` (e.g. Berlin).
    Remote jobs: the location (= where you may live) must be an allowed region."""
    cities = profile.get("onsite_cities") or []
    regions = profile.get("remote_regions") or profile.get("location_any") or []
    if cities and _hits(cities, job.location):
        return True  # any work mode is fine in your city
    if is_remote(job):
        if workmode.office_required(job.description):
            # labelled remote, but the ad asks for office days: hybrid, so the office must be
            # in one of your cities ("2 office days a month in our Paris office" -> no)
            return bool(cities) and bool(_hits(cities, job.description))
        return location_ok(job.location, regions)
    return not cities and location_ok(job.location, regions)


def title_ok(job: Job, profile: dict) -> bool:
    """Everything except the required (all_of) words: lets sources skip fetching
    descriptions for jobs that can never match."""
    return apply(job, profile, check_all_of=False)


def apply(job: Job, profile: dict, check_all_of: bool = True, check_place: bool = True) -> bool:
    """Return True if the job passes the profile; sets job.score / job.matched."""
    match_in = profile.get("match_in") or ["title"]
    exclude_in = profile.get("exclude_in") or match_in
    text = _text(job, match_in)

    if _hits(profile.get("none_of") or [], _text(job, exclude_in)):
        return False

    # language: ads written in a skipped language, or requiring fluency in one
    # (needs the ad text: jobs without a description are kept)
    if job.description and profile.get("skip_ad_languages"):
        if language.ad_language(job.description) in profile["skip_ad_languages"]:
            return False
    for lang in profile.get("skip_if_requires") or []:
        if language.requires(job.description, lang):
            return False

    all_of = profile.get("all_of") or []
    all_text = _text(job, profile.get("all_of_in") or ["title", "description", "tags"])
    notes = list(job.source_notes)
    if check_all_of and len(_hits(all_of, all_text)) != len(all_of):
        if job.has_description:
            return False
        # source has no descriptions: can't check, so keep it but say so
        notes.append(f"{', '.join(a.split('|')[0] for a in all_of)} not verified")

    if check_place and not place_ok(job, profile):
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
    job.notes = notes
    return True


def still_near_miss(job: Job, profile: dict) -> bool:
    """For a stored near miss: do today's title rules (exclusions, title words, language)
    still let it through? The place was checked when it was found (its remote flag isn't
    stored), and the required words are what it misses anyway."""
    return apply(job, profile, check_all_of=False, check_place=False)


def near_miss(job: Job, profile: dict) -> str:
    """For a job the profile rejected: if it fails ONLY the required words
    (all_of), say which ones are missing; otherwise "". Used for the weekly
    "near misses" list (e.g. a leadership platform job whose ad never says Kubernetes)."""
    all_of = profile.get("all_of") or []
    if not all_of or not apply(job, profile, check_all_of=False):
        return ""
    if not job.description:
        return "ad text not available"
    text = _text(job, profile.get("all_of_in") or ["title", "description", "tags"])
    missing = [a.split("|")[0] for a in all_of if not _hits([a], text)]
    return f"no {', '.join(missing)} in the ad" if missing else ""
