"""SQLite memory of jobs already reported, so each job is emailed only once.

A job counts as seen if its URL was seen, or if a job with the same normalized
company + title was seen (catches the same job reposted on another portal)."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from .models import Job

_NOISE = re.compile(r"\((?:m|f|w|d|x|h)(?:/(?:m|f|w|d|x|h))+\)|\b(remote|fully remote|100% remote)\b", re.I)
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def job_key(job: Job) -> str:
    def norm(s: str) -> str:
        return _NON_ALNUM.sub(" ", _NOISE.sub(" ", s.lower())).strip()
    return f"{norm(job.company)}|{norm(job.title)}"


class Store:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(str(path))
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS seen (
                   url TEXT PRIMARY KEY,
                   key TEXT NOT NULL,
                   title TEXT, company TEXT, source TEXT,
                   first_seen TEXT NOT NULL)"""
        )
        self.db.execute("CREATE INDEX IF NOT EXISTS seen_key ON seen(key)")

    def is_seen(self, job: Job) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM seen WHERE url = ? OR key = ? LIMIT 1", (job.url, job_key(job))
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
        self.db.executemany(
            "INSERT OR IGNORE INTO seen (url, key, title, company, source, first_seen) VALUES (?,?,?,?,?,?)",
            [(j.url, job_key(j), j.title, j.company, j.source, now) for j in jobs],
        )
        self.db.commit()
