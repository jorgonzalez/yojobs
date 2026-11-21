"""Stapply's open job dataset (https://storage.stapply.ai/jobs/v1/manifest.json; MIT;
collected from ~90 hiring systems and job boards, refreshed once a day).

Off by default, and optional: it needs DuckDB (`.venv/bin/pip install duckdb`), which reads
only the needed columns of each slice's Parquet file over HTTP (a few MB, seconds per slice).
DuckDB's HTTP extension is kept in `.duckdb/` inside the project (git-ignored), not ~/.duckdb.

Each run:
  1. reads the manifest; a slice whose file hasn't changed since we last read it is skipped
     (so each daily snapshot is read once, however many runs a day)
  2. per slice, light columns of the jobs posted since that slice was last read (minus a
     2-day margin, at most 7 days), in Germany or remote, not marked stale
  3. the ad text only for jobs whose title and place already fit and that aren't known yet

`slices` picks the hiring systems; the default leaves out the ones yojobs already reads
directly (Greenhouse, Lever, Ashby, Personio, Recruitee, Teamtailor, Pinpoint, WTTJ...).
Every job records its slice as found_by, so the weekly email's Searches table shows what
each slice brought (matches emailed / near misses; 0/0 = nothing, a candidate to drop).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from ..http import get_json
from ..models import Job, parse_iso
from ..progress import note, say

MANIFEST = "https://storage.stapply.ai/jobs/v1/manifest.json"
DEFAULT_SLICES = ["bamboohr", "smartrecruiters", "workable", "workday", "join_com", "eures"]
DONE_KEY = "stapply_done"           # meta: {slice: {"sha": parquet sha256, "at": when read}}
MARGIN = timedelta(days=2)          # a job can reach the dataset a day after it was posted
MAX_LOOKBACK = timedelta(days=7)
MAX_ADS_PER_SLICE = 40              # ad texts fetched per slice and run
EXT_DIR = Path(__file__).resolve().parents[2] / ".duckdb"

LIGHT = ["url", "title", "company", "location", "locations", "country_iso", "is_remote", "workplace_type",
         "posted_at"]


class DuckDB:
    """Parquet over HTTP; the extension lives in the project, never in ~/.duckdb."""

    def __init__(self, ext_dir: Path = EXT_DIR):
        try:
            import duckdb
        except ImportError as exc:
            raise RuntimeError("the stapply source needs DuckDB: .venv/bin/pip install duckdb") from exc
        ext_dir.mkdir(exist_ok=True)
        self.con = duckdb.connect()
        self.con.execute(f"SET home_directory = '{ext_dir}'")
        self.con.execute(f"SET extension_directory = '{ext_dir}'")

    def columns(self, url: str) -> set:
        return {r[0] for r in self.con.execute(f"DESCRIBE SELECT * FROM read_parquet('{url}')").fetchall()}

    def rows(self, sql: str, params: list) -> List[dict]:
        cur = self.con.execute(sql, params)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]


def _places(row: dict) -> str:
    """The location plus any further offices from `locations` (multi-city ads list them there)."""
    places = [row.get("location") or ""]
    try:
        places += [(p or {}).get("label") or "" for p in json.loads(row.get("locations") or "[]")]
    except (ValueError, TypeError, AttributeError):
        pass
    return "; ".join(dict.fromkeys(p.strip() for p in places if p and p.strip()))


def to_job(row: dict, slice_name: str) -> Job:
    mode = (row.get("workplace_type") or "").lower()
    remote = True if row.get("is_remote") or mode == "remote" else False if mode in ("onsite", "hybrid") else None
    return Job(source="stapply", title=row.get("title") or "", company=row.get("company") or "",
               url=row.get("url") or "", location=_places(row), published=parse_iso(row.get("posted_at")),
               remote=remote, work_mode=mode if mode in ("remote", "hybrid", "onsite") else "",
               has_description=False, found_by=slice_name)


def _select(cols: set, names: List[str]) -> str:
    return ", ".join(n if n in cols else f"NULL AS {n}" for n in names)


def _where(cols: set) -> str:
    place = ["country_iso = 'DE'" if "country_iso" in cols else None,
             "coalesce(is_remote, false)" if "is_remote" in cols else None,
             "lower(workplace_type) = 'remote'" if "workplace_type" in cols else None,
             """locations LIKE '%"country_iso":"DE"%'""" if "locations" in cols else None]
    where = ["posted_at >= ?", "(" + " OR ".join(p for p in place if p) + ")"]
    if "is_stale" in cols:
        where.append("NOT coalesce(is_stale, false)")
    return " AND ".join(where)


def read_slice(db, url: str, slice_name: str, start: datetime, wanted, known) -> List[Job]:
    cols = db.columns(url)
    if not {"url", "title", "posted_at"} <= cols:
        raise ValueError(f"unexpected columns in {slice_name}")
    rows = db.rows(f"SELECT {_select(cols, LIGHT)} FROM read_parquet('{url}') WHERE {_where(cols)}",
                   [start.strftime("%Y-%m-%d")])
    jobs = [to_job(r, slice_name) for r in rows if r.get("url") and r.get("title")]
    todo = [j for j in jobs if wanted(j) and not known(j)][:MAX_ADS_PER_SLICE]
    if todo and "description" in cols:
        ads = {r["url"]: r["description"] or "" for r in db.rows(
            f"SELECT url, description FROM read_parquet('{url}') WHERE url IN (SELECT unnest(?))",
            [[j.url for j in todo]])}
        for j in todo:
            if ads.get(j.url):
                j.description, j.has_description = ads[j.url], True
    say(f"    stapply {slice_name}: {len(jobs)} jobs in Germany/remote, {len(todo)} fit the title")
    return jobs


def fetch(cfg, since):
    state = cfg.get("_state")          # History (meta table)
    now = datetime.now(timezone.utc)
    manifest = get_json(MANIFEST)
    by_ats = manifest.get("by_ats") or {}
    done: Dict[str, dict] = dict(state.get(DONE_KEY, {}) if state is not None else {})
    db = cfg.get("_db")                # tests pass a fake
    wanted = cfg.get("_title_ok") or (lambda j: True)
    known = cfg.get("_known") or (lambda j: False)
    jobs: List[Job] = []
    window: Optional[datetime] = None
    for name in cfg.get("slices") or DEFAULT_SLICES:
        entry = by_ats.get(name) or {}
        url, sha = entry.get("parquet"), entry.get("parquet_sha256") or manifest.get("generated_at")
        if not url:
            note(f"    stapply: no slice '{name}' in the manifest")
            continue
        last = done.get(name) or {}
        if last.get("sha") == sha:
            say(f"    stapply {name}: snapshot already read")
            continue
        read_at = parse_iso(last.get("at"))
        start = max(read_at - MARGIN, now - MAX_LOOKBACK) if read_at else since
        if db is None:
            db = DuckDB()
        try:
            jobs += read_slice(db, url, name, start, wanted, known)
        except Exception as exc:  # one slice must not stop the others
            if cfg.get("_problems") is not None:
                cfg["_problems"].append((f"stapply:{name}", f"{type(exc).__name__}: {exc}"[:200]))
            note(f"    stapply {name}: {type(exc).__name__}: {exc}")
            continue
        window = min(window or start, start)
        done[name] = {"sha": sha, "at": now.isoformat()}
        if state is not None:
            state.set(DONE_KEY, done)
    if window:
        cfg["_window_start"] = window
    return jobs
