"""Work-mode hint for on-site / hybrid jobs, shown next to the location in the
email, e.g. "Berlin (hybrid · 2-3 office days/week)".

The mode comes from the source when it states it (Greenhouse/Lever/Ashby
workplaceType, StartupMap workplace_type), otherwise from the job text, in
English and German. Office days are taken from phrases like "3 days a week in
the office", "in our Berlin office twice a week" or "2 Tage pro Woche im Büro".
"""
from __future__ import annotations

import re

from .models import Job

_NUM = r"(\d|one|two|three|four|five|ein|eine|einem|zwei|drei|vier|fünf)"
_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
          "ein": "1", "eine": "1", "einem": "1", "zwei": "2", "drei": "3", "vier": "4", "fünf": "5"}

# "2-3 days a week", "3 office days per week", "2x per week", "2 Tage pro Woche", "an 3 Tagen (pro Woche)"
_DAYS = re.compile(
    rf"\b(?:an\s+)?{_NUM}(?:\s*(?:-|–|to|or|bis|oder)\s*{_NUM})?\s*"
    r"(?:x|times|office\s+days?|days?|tage?n?|bürotage?n?)\b"
    r"(?:\s*(?:a|per|each|every|pro|die|in\s+der|/)\s*(?:week|woche))?",
    re.IGNORECASE)
_TWICE = re.compile(r"\b(once|twice)\s+(?:a|per)\s+week\b", re.IGNORECASE)
_OFFICE = re.compile(r"\b(office|in[- ]person|on[- ]?site|onsite|büro|vor\s+ort|präsenz)", re.IGNORECASE)
_HOME = re.compile(r"\b(remote|home|from\s+home|homeoffice|home[- ]office|mobil)", re.IGNORECASE)

_HYBRID = re.compile(r"\b(hybrid|hybride[nrs]?|hybrides?\s+arbeiten)\b", re.IGNORECASE)
_ONSITE = re.compile(r"\b(on[- ]?site|in[- ]office|office[- ]based|fully\s+in\s+the\s+office|"
                     r"vor\s+ort|präsenz)\b", re.IGNORECASE)

_SOURCE_MODES = {"hybrid": "hybrid", "onsite": "on-site", "on-site": "on-site", "on_site": "on-site",
                 "remote": "remote"}


def _n(token: str) -> str:
    return _WORDS.get((token or "").lower(), token or "")


def office_days(text: str) -> str:
    """'2', '2-3' or '' from phrases like '2-3 days a week in the office'."""
    for m in _TWICE.finditer(text or ""):
        near = text[max(0, m.start() - 60): m.end() + 60]
        if _OFFICE.search(near):
            return "1" if m.group(1).lower() == "once" else "2"
    for m in _DAYS.finditer(text or ""):
        if not re.search(r"week|woche|tag", m.group(0), re.IGNORECASE) and \
                not re.search(r"week|woche", text[m.end(): m.end() + 25], re.IGNORECASE):
            continue  # "5 days of onboarding": not a weekly rhythm
        before, after = text[max(0, m.start() - 60): m.start()], text[m.end(): m.end() + 60]
        if not _OFFICE.search(m.group(0)):  # "3 office days", "Bürotage": office is in the phrase
            if not _OFFICE.search(before + " " + after):
                continue
            # "2 days from home, rest in the office": the office word must be the closest one
            home_after, office_after = _HOME.search(after), _OFFICE.search(after)
            if home_after and (not office_after or home_after.start() < office_after.start()):
                continue
        lo, hi = _n(m.group(1)), _n(m.group(2))
        if not lo.isdigit() or int(lo) > 5 or (hi and (not hi.isdigit() or int(hi) > 5)):
            continue
        return f"{lo}-{hi}" if hi and hi != lo else lo
    return ""


def detect_mode(job: Job) -> str:
    explicit = _SOURCE_MODES.get((job.work_mode or "").lower().replace(" ", ""))
    if explicit:
        return explicit
    text = " ".join([job.title, job.location, job.description])
    if _HYBRID.search(text):
        return "hybrid"
    if job.remote is True:
        return "remote"
    if _ONSITE.search(text):
        return "on-site"
    return ""


def describe(job: Job) -> str:
    """Short hint like 'hybrid · 2 office days/week', 'on-site', or ''."""
    mode = detect_mode(job)
    days = office_days(job.description) if mode != "remote" else ""
    if days:
        # the ad's own numbers win over a generic label: "on-site" with 3 office
        # days a week is hybrid; 5 days is on-site
        mode = "on-site" if days.split("-")[-1] == "5" else "hybrid"
    if not mode:
        return ""
    if days:
        unit = "office day" if days == "1" else "office days"
        return f"{mode} · {days} {unit}/week"
    return mode
