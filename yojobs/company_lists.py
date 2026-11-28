"""Company lists: files of company names, each with what to do with their jobs.

In blocklist.yaml (files are relative to the config folder):

    company_lists:
      - file: company_lists/narnia.txt
        label: Narnian company     # shown next to the job
        action: warn               # warn | block

  warn   the job is emailed as usual, with a "⚠ <label>" note (also on weekly near misses)
  block  like blocked_companies: never emailed, never a near miss, no board suggested

A list file has one company per line; other names for the same company go after "|";
"#" starts a comment; blank lines are ignored:

    Cair Paravel Systems | Cair Paravel     # founded in Narnia, HQ in Archenland
    Lantern Waste Labs

Names are compared like blocked_companies: case, spaces, punctuation and legal suffixes
are ignored ("Lantern Waste Labs GmbH" = "lanternwaste labs"), but only whole names
match, so a short name like "Via" doesn't hit "Viaplay".
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .store import norm_company

ACTIONS = ("warn", "block")


class ListError(ValueError):
    pass


def company_key(name: str) -> str:
    """'GetYourGuide' == 'Get Your Guide GmbH' == 'getyourguide'."""
    return norm_company(name).replace(" ", "")


def read_names(path: Path) -> List[str]:
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0]
        names += [n.strip() for n in line.split("|") if n.strip()]
    return names


def resolve(cfg: dict, base: Path) -> None:
    """Read cfg["company_lists"]: names of `block` lists are added to blocked_companies,
    `warn` lists become cfg["flagged_companies"] = {company key: label}. Raises ListError."""
    entries = cfg.pop("company_lists", None) or []
    if not isinstance(entries, list):
        raise ListError("company_lists: expected a list of {file, label, action}")
    flagged: Dict[str, str] = {}
    blocked = list(cfg.get("blocked_companies") or [])
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("file"):
            raise ListError(f"company_lists: each entry needs a file (got {entry!r})")
        action = str(entry.get("action") or "warn").lower()
        if action not in ACTIONS:
            raise ListError(f"company_lists: {entry['file']}: action must be one of {', '.join(ACTIONS)}")
        path = (base / str(entry["file"])).expanduser()
        if not path.is_file():
            raise ListError(f"company_lists: file not found: {path}")
        names = read_names(path)
        label = str(entry.get("label") or path.stem)
        if action == "block":
            blocked += names
        else:
            for n in names:
                if company_key(n):
                    flagged.setdefault(company_key(n), label)
    cfg["blocked_companies"] = blocked
    cfg["flagged_companies"] = flagged


def flag(cfg: dict, company: str) -> str:
    """The warn-list label for a company, or ""."""
    flagged = cfg.get("flagged_companies") or {}
    return flagged.get(company_key(company), "") if flagged and company else ""
