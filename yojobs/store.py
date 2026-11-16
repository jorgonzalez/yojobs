"""SQLite memory of jobs already reported, so each job is emailed only once.

A job counts as already seen if:
  * its URL was emailed before (forever), or
  * a job with the same normalized company + title was emailed within the last
    `key_days` days (catches reposts and the same job on another portal, while
    letting a genuinely reopened position through after a while).

Normalization (see job_key):
  company: lowercase, punctuation removed, trailing legal suffixes dropped
           ("Acme GmbH" == "ACME" == "Acme, Inc.")
  title:   lowercase, gender tags "(m/w/d)" dropped, location tails dropped
           ("DevOps Engineer - Remote, Germany"), Sr/Jr/Mgr... expanded.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

from .models import Job

# --- company -----------------------------------------------------------------

_LEGAL = {
    "gmbh", "ag", "se", "kg", "ug", "kgaa", "ohg", "mbh", "co", "inc", "incorporated", "ltd", "limited",
    "llc", "llp", "plc", "corp", "corporation", "company", "bv", "nv", "sa", "sas", "sarl", "srl", "spa",
    "and", "sl", "slu", "oy", "oyj", "ab", "as", "asa", "aps", "sp", "zoo", "pty", "group", "holding", "holdings",
}

# --- title -------------------------------------------------------------------

_GENDER = re.compile(r"\(\s*[mfwdxh](\s*[/|,]\s*[mfwdxh*]+)+\s*\)|\b[mfwdxh]/[mfwdxh](/[mfwdxh])?\b", re.I)

# Words that mark a title segment as "just a location / work-mode" tail.
_PLACE_WORDS = (
    "remote|hybrid|onsite|on-site|office|wfh|worldwide|anywhere|global|international|"
    "europe|european|eu|emea|cet|dach|germany|deutschland|berlin|munich|münchen|hamburg|frankfurt|cologne|köln|"
    "stuttgart|dusseldorf|düsseldorf|leipzig|uk|united kingdom|london|us|usa|united states|americas|latam|apac|"
    "spain|madrid|barcelona|portugal|lisbon|porto|netherlands|amsterdam|france|paris|poland|warsaw|"
    "austria|vienna|switzerland|zurich|ireland|dublin|belgium|brussels|italy|sweden|denmark|norway|finland|"
    "canada|india|brazil|mexico|timezone|timezones|time zone|only|based|full-time|full time|part-time"
)
_PLACE_RE = re.compile(rf"\b({_PLACE_WORDS})\b", re.I)

_ABBREV = {
    "sr": "senior", "snr": "senior", "jr": "junior", "jnr": "junior", "mgr": "manager", "mngr": "manager",
    "eng": "engineer", "engr": "engineer", "sw": "software", "infra": "infrastructure", "k8s": "kubernetes",
}

_NON_ALNUM = re.compile(r"[^a-z0-9äöüß]+")


def norm_company(company: str) -> str:
    words = _NON_ALNUM.sub(" ", (company or "").lower().replace(".", "").replace("&", " and ")).split()
    while len(words) > 1 and words[-1] in _LEGAL:
        words.pop()
    return " ".join(words)


def _is_place(segment: str) -> bool:
    """True if a title segment is only location / work-mode words."""
    leftover = _PLACE_RE.sub(" ", segment.lower())
    leftover = re.sub(r"\b(in|or|and|from|within|with|to|the|of|for|fully|\d+)\b|[^\w]", " ", leftover)
    return bool(_PLACE_RE.search(segment)) and not leftover.strip()


def norm_title(title: str) -> str:
    t = _GENDER.sub(" ", title or "")
    # drop parenthesised location bits: "DevOps Engineer (Remote, EU)"
    t = re.sub(r"\(([^)]*)\)", lambda m: " " if _is_place(m.group(1)) else f" {m.group(1)} ", t)
    # drop trailing location segments: "DevOps Engineer - Remote - Germany"
    parts = re.split(r"\s+[-–—|@]\s+|,\s+|:\s+", t)
    while len(parts) > 1 and _is_place(parts[-1]):
        parts.pop()
    t = " ".join(parts).lower().replace("&", " and ")
    words = [_ABBREV.get(w, w) for w in _NON_ALNUM.sub(" ", t).split()]
    words = [w for w in words if w not in ("remote",)]
    return " ".join(words)


def job_key(job: Job) -> str:
    return f"{norm_company(job.company)}|{norm_title(job.title)}"


# --- store -------------------------------------------------------------------


class Store:
    def __init__(self, path: Path, key_days: int = 60):
        self.key_days = key_days
        self.db = sqlite3.connect(str(path))
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS seen (
                   url TEXT PRIMARY KEY,
                   key TEXT NOT NULL,
                   title TEXT, company TEXT, source TEXT,
                   first_seen TEXT NOT NULL)"""
        )
        self.db.execute("CREATE INDEX IF NOT EXISTS seen_key ON seen(key)")
        self._rekey()

    def _rekey(self) -> None:
        """Recompute keys from stored title/company, so normalization changes
        apply to jobs remembered by older versions."""
        rows = self.db.execute("SELECT url, title, company, key FROM seen").fetchall()
        updates = []
        for url, title, company, key in rows:
            new = f"{norm_company(company or '')}|{norm_title(title or '')}"
            if new != key:
                updates.append((new, url))
        if updates:
            self.db.executemany("UPDATE seen SET key = ? WHERE url = ?", updates)
            self.db.commit()

    def is_empty(self) -> bool:
        return self.db.execute("SELECT 1 FROM seen LIMIT 1").fetchone() is None

    def _cutoff(self) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=self.key_days)).isoformat(timespec="seconds")

    def is_seen(self, job: Job) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM seen WHERE url = ? OR (key = ? AND first_seen >= ?) LIMIT 1",
            (job.url, job_key(job), self._cutoff()),
        ).fetchone()
        return row is not None

    def filter_new(self, jobs: List[Job]) -> List[Job]:
        new, keys = [], set()
        for j in jobs:
            k = job_key(j)
            if k in keys or self.is_seen(j):
                continue  # also dedupes within this run
            keys.add(k)
            new.append(j)
        return new

    def mark_seen(self, jobs: List[Job]) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        # REPLACE refreshes first_seen when a reopened job (same URL is rare) is sent again
        self.db.executemany(
            "INSERT OR REPLACE INTO seen (url, key, title, company, source, first_seen) VALUES (?,?,?,?,?,?)",
            [(j.url, job_key(j), j.title, j.company, j.source, now) for j in jobs],
        )
        self.db.commit()
