"""Board discovery: find the public job boards of companies that already sent you
matches or near misses, and suggest them for config/companies.yaml.

There is no list of all companies on Greenhouse, Lever, Ashby, Personio, Recruitee or
Teamtailor, but every match/near miss names a company that hires for your profile.
For each such company not yet in companies.yaml (checked once, remembered), try a few
spellings of its name on each system's public API. A board only counts if it is
clearly that company's: its name must match where the system reports one; where it
doesn't (Lever, Ashby), the id must be the company's full name.

Shown in the weekly email; you decide what to add. Off with weekly.discover_boards: 0.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

from .http import USER_AGENT
from .progress import say
from .store import norm_company

TIMEOUT = 10


def _get(url: str) -> Optional[bytes]:
    """Body on HTTP 200, else None (404 = no such board; errors = unknown, also None)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                return None
            return resp.read(3_000_000)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def company_key(name: str) -> str:
    return norm_company(name).replace(" ", "")


_NOISE = {"jobs", "job", "careers", "career", "karriere", "at", "bei", "remote", "the"}


def same_company(a: str, b: str) -> bool:
    """Whole words, same first word: "tado" = "tado GmbH", "Distribusion" = "Distribusion
    Technologies", "Get Your Guide" = "GetYourGuide"; but "Remote" != "General Assembly
    Remote Jobs" (a board that once looked like Remote.com's)."""
    if company_key(a) and company_key(a) == company_key(b):
        return True
    wa = [w for w in norm_company(a).split() if w not in _NOISE]
    wb = [w for w in norm_company(b).split() if w not in _NOISE]
    if not wa or not wb or wa[0] != wb[0]:
        return False
    short, long_ = sorted((set(wa), set(wb)), key=len)
    return short <= long_


def variants(company: str) -> List[Tuple[str, bool]]:
    """Board ids to try -> [(id, is_full_name)], e.g. "Distribusion Technologies" ->
    distribusiontechnologies, distribusion-technologies, distribusion (first word)."""
    words = norm_company(company).split()
    if not words:
        return []
    out = [("".join(words), True)]
    if len(words) > 1:
        out.append(("-".join(words), True))
        if len(words[0]) >= 4:
            out.append((words[0], False))
    return list(dict.fromkeys(out))


# system -> probe(id) -> board name reported by the system, "" if it has none, or None if no board
def _greenhouse(bid):
    body = _get(f"https://boards-api.greenhouse.io/v1/boards/{bid}")
    return (json.loads(body).get("name") or "") if body else None


def _json(body: bytes, starts: bytes):
    """Parsed JSON, or True when the body was cut off at the size limit but clearly starts
    with a non-empty job list (a big board), or None."""
    try:
        return json.loads(body)
    except ValueError:
        return True if starts in body[:300].replace(b" ", b"") else None


def _lever(bid, host="api.lever.co"):
    body = _get(f"https://{host}/v0/postings/{bid}?mode=json&limit=1")
    return "" if body and _json(body, b"[{") else None


def _lever_eu(bid):
    return _lever(bid, "api.eu.lever.co")


def _ashby(bid):
    body = _get(f"https://api.ashbyhq.com/posting-api/job-board/{bid}")
    data = _json(body, b'"jobs":[{') if body else None
    return "" if data is True or (isinstance(data, dict) and data.get("jobs")) else None


def _personio(bid):
    body = _get(f"https://{bid}.jobs.personio.de/xml")
    if not body or not body.lstrip().startswith(b"<?xml") or b"<position>" not in body:
        return None
    page = _get(f"https://{bid}.jobs.personio.de/") or b""
    m = re.search(rb"<title>(.*?)</title>", page, re.S)
    return re.sub(r"^\s*(jobs\s+(at|bei)\s+)", "", m.group(1).decode("utf-8", "replace"), flags=re.I).strip() if m else ""


def _recruitee(bid):
    body = _get(f"https://{bid}.recruitee.com/api/offers/")
    if not body:
        return None
    data = _json(body, b'"offers":[{')
    if data is True:  # cut off: take the name from the first offer
        m = re.search(rb'"company_name"\s*:\s*"([^"]*)"', body)
        return m.group(1).decode("utf-8", "replace") if m else ""
    offers = (data.get("offers") or []) if isinstance(data, dict) else []
    return (offers[0].get("company_name") or "") if offers else None


def _teamtailor(bid):
    body = _get(f"https://{bid}.teamtailor.com/jobs.rss")
    if not body or b"<rss" not in body[:500]:
        return None
    try:
        channel = ET.fromstring(body).find("channel")
    except ET.ParseError:
        return None
    return (channel.findtext("title") or "") if channel is not None and channel.find("item") is not None else None


PROBES: Dict[str, Callable[[str], Optional[str]]] = {
    "greenhouse": _greenhouse, "ashby": _ashby, "lever": _lever, "lever:eu": _lever_eu,
    "personio": _personio, "recruitee": _recruitee, "teamtailor": _teamtailor,
}


def find_board(company: str, delay: float = 0.3) -> str:
    """'system:id' of the company's board, or ''."""
    for bid, full in variants(company):
        for system, probe in PROBES.items():
            try:
                name = probe(bid)
            except Exception:  # an odd answer from one system must not stop the others
                name = None
            time.sleep(delay)
            if name is None:
                continue
            if name and same_company(name, company):
                return f"{system}:{bid}"
            if not name and full:            # system reports no name: only trust the full name
                return f"{system}:{bid}"
    return ""


def covered(company: str, boards: List[str]) -> bool:
    """Is the company already in companies.yaml (any system, any spelling we'd try)?"""
    ids = {b.rsplit(":", 1)[1].split(".")[0].replace("-", "") for b in boards if ":" in b}
    return any(v.replace("-", "") in ids for v, _ in variants(company))


def run(db, cfg: dict, limit: int = 15, delay: float = 0.3) -> List[dict]:
    """Check up to `limit` new companies from the last 30 days' matches and near misses;
    -> suggestions not yet in companies.yaml: [{board, company, example}]."""
    db.execute("""CREATE TABLE IF NOT EXISTS board_checks (
                      company_key TEXT PRIMARY KEY, company TEXT, board TEXT, example TEXT, checked_at TEXT)""")
    boards = ((cfg.get("sources") or {}).get("companies") or {}).get("boards") or []
    blocked = {company_key(c) for c in cfg.get("blocked_companies") or []}
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    rows = db.execute("SELECT company, title FROM seen WHERE first_seen >= ? AND source != 'companies' "
                      "UNION ALL SELECT company, title FROM near_misses WHERE found_at >= ? AND source != 'companies'",
                      (since, since)).fetchall()
    checked = {k for (k,) in db.execute("SELECT company_key FROM board_checks")}
    todo: Dict[str, Tuple[str, str]] = {}
    for company, title in rows:
        key = company_key(company or "")
        if not key or key in checked or key in blocked or key in todo or covered(company, boards):
            continue
        todo[key] = (company, title)
    for n, (key, (company, title)) in enumerate(list(todo.items())[:limit], 1):
        say(f"    board discovery {n}/{min(limit, len(todo))}: {company}")
        board = find_board(company, delay)
        db.execute("INSERT OR REPLACE INTO board_checks VALUES (?, ?, ?, ?, ?)",
                   (key, company, board, title, datetime.now(timezone.utc).isoformat(timespec="seconds")))
        db.commit()
    configured = {b.lower() for b in boards}
    return [dict(board=b, company=c, example=e) for c, b, e in db.execute(
        "SELECT company, board, example FROM board_checks WHERE board != '' ORDER BY checked_at DESC")
        if b.lower() not in configured][:10]
