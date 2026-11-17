"""Run history in the same SQLite file as the seen-jobs memory, for:

  * source health: a source that errors or returns 0 jobs for `failed_runs`
    runs in a row triggers one warning email (and another when it recovers is
    not sent; recovery is listed in the weekly summary)
  * the weekly summary email: runs, jobs checked, jobs emailed, per-source status
  * near misses: jobs that passed every rule except the required words (all_of),
    collected during runs and listed once in the weekly email

Only real runs (--email / scheduled) are recorded; previews leave no trace.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from .models import Job
from .store import job_key

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class SourceRun:
    source: str
    status: str            # "ok" or "ERROR"
    fetched: int = 0
    recent: int = 0
    matched: int = 0
    seconds: float = 0.0
    error: str = ""


class History:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        db.executescript(
            """CREATE TABLE IF NOT EXISTS source_runs (
                   run_at TEXT NOT NULL, source TEXT NOT NULL, status TEXT NOT NULL,
                   fetched INTEGER, recent INTEGER, matched INTEGER, seconds REAL, error TEXT);
               CREATE INDEX IF NOT EXISTS source_runs_src ON source_runs(source, run_at);
               CREATE TABLE IF NOT EXISTS near_misses (
                   url TEXT PRIMARY KEY, key TEXT, title TEXT, company TEXT, location TEXT,
                   source TEXT, published TEXT, reason TEXT, found_at TEXT NOT NULL, digested_at TEXT);
               CREATE TABLE IF NOT EXISTS meta (name TEXT PRIMARY KEY, value TEXT);""")
        db.commit()

    # --- meta ----------------------------------------------------------------

    def get(self, name: str, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE name = ?", (name,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, name: str, value) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta (name, value) VALUES (?, ?)", (name, json.dumps(value)))
        self.db.commit()

    # --- runs & health -------------------------------------------------------

    def record(self, runs: List[SourceRun], when: Optional[str] = None) -> None:
        when = when or _now()
        self.db.executemany(
            "INSERT INTO source_runs VALUES (?,?,?,?,?,?,?,?)",
            [(when, r.source, r.status, r.fetched, r.recent, r.matched, r.seconds, r.error) for r in runs])
        self.db.execute("DELETE FROM source_runs WHERE run_at < ?",
                        ((datetime.now(timezone.utc) - timedelta(days=90)).isoformat(),))
        self.db.commit()

    def failing(self, source: str, failed_runs: int) -> Optional[str]:
        """Why the source looks broken (its last `failed_runs` runs all errored or
        returned nothing), or None if it is fine."""
        rows = self.db.execute(
            "SELECT status, fetched, error FROM source_runs WHERE source = ? ORDER BY run_at DESC LIMIT ?",
            (source, failed_runs)).fetchall()
        if len(rows) < failed_runs:
            return None
        if all(s == "ERROR" for s, _, _ in rows):
            return f"failed the last {failed_runs} runs ({rows[0][2]})"
        if all(s == "ERROR" or not f for s, f, _ in rows):
            return f"returned no jobs in the last {failed_runs} runs (the site may have changed)"
        return None

    def health_changes(self, sources: List[str], failed_runs: int) -> Tuple[Dict[str, str], List[str]]:
        """-> (newly broken {source: reason}, recovered [source]). 'Newly' = not
        warned about yet; call mark_alerted() once the warning email went out."""
        alerted = set(self.get("alerted_sources", []))
        broken, recovered = {}, []
        for s in sources:
            why = self.failing(s, failed_runs)
            if why and s not in alerted:
                broken[s] = why
            elif not why and s in alerted:
                recovered.append(s)
        return broken, recovered

    def mark_alerted(self, broken: List[str], recovered: List[str]) -> None:
        alerted = (set(self.get("alerted_sources", [])) | set(broken)) - set(recovered)
        self.set("alerted_sources", sorted(alerted))

    # --- near misses ---------------------------------------------------------

    def add_near_misses(self, items: List[Tuple[Job, str]]) -> None:
        self.db.executemany(
            "INSERT OR IGNORE INTO near_misses (url, key, title, company, location, source, published, reason, found_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            [(j.url, job_key(j), j.title, j.company, j.location, j.source,
              j.published.isoformat() if j.published else None, reason, _now()) for j, reason in items])
        self.db.commit()

    def pending_near_misses(self, limit: int = 60) -> List[dict]:
        """Near misses not listed in a weekly email yet, and never emailed as a match;
        one per company + title (the same job from several portals)."""
        rows = self.db.execute(
            """SELECT url, key, title, company, location, source, published, reason FROM near_misses
               WHERE digested_at IS NULL AND key NOT IN (SELECT key FROM seen) AND url NOT IN (SELECT url FROM seen)
               ORDER BY published DESC""").fetchall()
        out, keys = [], set()
        for url, key, title, company, location, source, published, reason in rows:
            if key in keys:
                continue
            keys.add(key)
            out.append(dict(url=url, title=title, company=company, location=location or "", source=source,
                            published=published, reason=reason))
        return out[:limit]

    def mark_digested(self, urls: List[str]) -> None:
        now = _now()
        self.db.executemany("UPDATE near_misses SET digested_at = ? WHERE url = ?", [(now, u) for u in urls])
        # forget near misses after 60 days
        self.db.execute("DELETE FROM near_misses WHERE found_at < ?",
                        ((datetime.now(timezone.utc) - timedelta(days=60)).isoformat(),))
        self.db.commit()

    # --- weekly summary ------------------------------------------------------

    def weekly_due(self, cfg: dict, today: date) -> bool:
        """Due on the configured weekday, or the first run after it (laptop off
        on Monday -> sent on Tuesday), once per week."""
        if not cfg.get("enabled", True):
            return False
        target = WEEKDAYS.index(str(cfg.get("day", "monday")).lower())
        last_target = today - timedelta(days=(today.weekday() - target) % 7)
        last_sent = self.get("weekly_sent_on")
        return last_sent is None or date.fromisoformat(last_sent) < last_target

    def mark_weekly_sent(self, today: date) -> None:
        self.set("weekly_sent_on", today.isoformat())

    def week_stats(self, days: int = 7) -> dict:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        runs = self.db.execute("SELECT COUNT(DISTINCT run_at) FROM source_runs WHERE run_at >= ?", (since,)).fetchone()[0]
        emailed = self.db.execute("SELECT COUNT(*) FROM seen WHERE first_seen >= ?", (since,)).fetchone()[0]
        per_run = self.db.execute(
            "SELECT AVG(total) FROM (SELECT SUM(fetched) total FROM source_runs WHERE run_at >= ? GROUP BY run_at)",
            (since,)).fetchone()[0]
        sources = []
        for source, n, errors, avg_fetched, matched, last_ok in self.db.execute(
                """SELECT source, COUNT(*), SUM(status = 'ERROR'), AVG(CASE WHEN status = 'ok' THEN fetched END),
                          SUM(matched), MAX(CASE WHEN status = 'ok' AND fetched > 0 THEN run_at END)
                   FROM source_runs WHERE run_at >= ? GROUP BY source ORDER BY source""", (since,)):
            sources.append(dict(source=source, runs=n, errors=errors or 0, avg_fetched=round(avg_fetched or 0),
                                matched=matched or 0, last_ok=last_ok))
        return dict(runs=runs, emailed=emailed, jobs_per_run=round(per_run or 0), sources=sources,
                    alerted=self.get("alerted_sources", []))
