"""Turn a single config.yaml into the config/ folder:  python -m yojobs --split-config

Reads the old file, writes settings/profile/blocklist/sources/searches/companies.yaml
in the friendly format, then checks that the new folder loads to exactly the same
configuration (same sources, searches, boards, profiles, settings) before keeping it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import yaml

from .config import SEARCH_SOURCES, SYSTEMS, normalize, read_raw

SETTINGS_KEYS = ["max_age_days", "first_run_days", "schedule", "email", "database", "dedupe_days",
                 "weekly", "health"]
_PROFILE_ORDER = [("groups", "title_must_have"), ("any_of", "title_any"), ("all_of", "ad_must_mention"),
                  ("all_of_in", "ad_must_mention_in"), ("none_of", "exclude_titles"), ("exclude_in", "exclude_in"),
                  ("match_in", "match_in"), ("min_score", "min_score"), ("skip_ad_languages", "skip_ad_languages"),
                  ("skip_if_requires", "skip_if_requires")]


def _scalar(x) -> str:
    return yaml.safe_dump(x, default_flow_style=True, width=10_000).strip().removesuffix("...").strip()


def _flow(items, indent: int, width: int = 100) -> str:
    """[a, b, c] wrapped at `width`, continuation lines aligned after the '['."""
    parts = [_scalar(i) for i in items]
    lines, line = [], "["
    for n, p in enumerate(parts):
        piece = p + (", " if n < len(parts) - 1 else "")
        if len(line) + len(piece) + indent > width and line.strip("["):
            lines.append(line.rstrip())
            line = ""
        line += piece
    lines.append(line + "]")
    return ("\n" + " " * indent).join(lines)


def _mapping_flow(d: dict) -> str:
    return "{" + ", ".join(f"{k}: {_scalar(v)}" for k, v in d.items()) + "}"


def _block(key: str, value, indent: int = 0) -> str:
    pad = " " * indent
    if isinstance(value, dict):
        inner = "".join(_block(k, v, indent + 2) for k, v in value.items())
        return f"{pad}{key}:\n{inner}"
    if isinstance(value, list) and all(not isinstance(v, (dict, list)) for v in value):
        return f"{pad}{key}: {_flow(value, indent + len(key) + 3)}\n"  # items start after "key: ["
    if isinstance(value, list):
        return f"{pad}{key}:\n" + "".join(f"{pad}  - {_mapping_flow(v) if isinstance(v, dict) else _scalar(v)}\n"
                                         for v in value)
    return f"{pad}{key}: {_scalar(value)}\n"


# --- per file -----------------------------------------------------------------

def _settings(raw: dict) -> str:
    out = ["# How yojobs runs. See config.example/settings.yaml for every option.\n"]
    for key in SETTINGS_KEYS + [k for k in raw if k not in SETTINGS_KEYS + ["sources", "profiles", "blocked_companies"]]:
        if key in raw:
            out.append(_block(key, raw[key]))
    return "\n".join(out)


def _blocklist(raw: dict) -> str:
    names = raw.get("blocked_companies") or []
    body = "".join(f"  - {_scalar(n)}\n" for n in names) if names else ""
    return ("# Companies whose jobs are never emailed (or listed as near misses).\n"
            "# Case, spaces and legal suffixes are ignored: \"GetYourGuide\" also blocks \"Get Your Guide GmbH\".\n"
            + ("blocked_companies:\n" + body if names else "blocked_companies: []\n"))


def _profile_block(p: dict, indent: int) -> str:
    pad = " " * indent
    out = [f"{pad}name: {_scalar(p.get('name', 'profile'))}\n"]
    for old, new in _PROFILE_ORDER:
        if p.get(old) not in (None, [], {}):
            out.append(_block(new, p[old], indent))
    where = {k: p[k] for k in ("onsite_cities", "remote_regions") if k in p}
    if where:
        out.append(_block("where", where, indent))
    known = {o for o, _ in _PROFILE_ORDER} | {"name", "onsite_cities", "remote_regions"}
    for k, v in p.items():
        if k not in known:
            out.append(_block(k, v, indent))
    return "".join(out)


def _profiles(raw: dict) -> str:
    profiles = raw.get("profiles") or []
    head = "# What you're looking for. See config.example/profile.yaml for what each rule does.\n"
    if len(profiles) == 1:
        return head + "profile:\n" + _profile_block(profiles[0], 2)
    return head + "profiles:\n" + "".join("  -\n" + _profile_block(p, 4) for p in profiles)


def _sources(raw: dict) -> str:
    out = ["# Which portals to check. on / off, or {enabled: ..., option: ...}.\n",
           "# LinkedIn/Indeed searches are in searches.yaml, company boards in companies.yaml.\n", "sources:\n"]
    for name, s in (raw.get("sources") or {}).items():
        s = dict(s or {})
        s.pop("searches", None)
        s.pop("boards", None)
        enabled = s.pop("enabled", True)
        out.append(f"  {name}: {'on' if enabled else 'off'}\n" if not s
                   else f"  {name}: {_mapping_flow({'enabled': enabled, **s})}\n")
    return "".join(out)


def _searches(raw: dict) -> str:
    """Rebuild terms x places groups from the per-source search lists."""
    per_place: Dict[tuple, Dict[str, List[str]]] = {}
    for src in SEARCH_SOURCES:
        for s in ((raw.get("sources") or {}).get(src) or {}).get("searches") or []:
            place = tuple((k, v) for k, v in s.items() if k != "term")
            per_place.setdefault(place, {}).setdefault(src, []).append(s["term"])
    groups: Dict[tuple, List[dict]] = {}
    for place, by_src in per_place.items():
        for src, terms in by_src.items():
            others = [o for o in by_src if o != src and by_src[o] == terms]
            srcs = tuple(sorted([src] + others))
            key = (tuple(terms), srcs)
            if dict(place) not in groups.setdefault(key, []):
                groups[key].append(dict(place))
    out = ["# LinkedIn / Indeed searches: every term is searched in every place.\n", "searches:\n"]
    for (terms, srcs), places in groups.items():
        out.append(f"  - terms: {_flow(list(terms), 12)}\n")
        out.append("    places:\n" + "".join(f"      - {_mapping_flow(p)}\n" for p in places))
        if list(srcs) != sorted(SEARCH_SOURCES):
            out.append(f"    only: {_flow(list(srcs), 11)}\n")
    return "".join(out)


def _companies(raw: dict) -> str:
    boards = ((raw.get("sources") or {}).get("companies") or {}).get("boards") or []
    by_system: Dict[str, List[str]] = {}
    for b in boards:
        system, _, board = str(b).partition(":")
        by_system.setdefault(system, []).append(board)
    out = ["# Company career pages, by hiring system. The id is in the jobs page address:\n",
           "#   job-boards.greenhouse.io/<id>, jobs.lever.co/<id>, jobs.ashbyhq.com/<id>,\n",
           "#   <id>.jobs.personio.de (.com: <id>.com), <id>.recruitee.com\n", "companies:\n"]
    for system in SYSTEMS:
        if by_system.get(system):
            out.append(f"  {system}:{' ' * (11 - len(system))}{_flow(by_system[system], 15)}\n")
    return "".join(out)


def split(raw: dict) -> Dict[str, str]:
    return {"settings.yaml": _settings(raw), "profile.yaml": _profiles(raw), "blocklist.yaml": _blocklist(raw),
            "sources.yaml": _sources(raw), "searches.yaml": _searches(raw), "companies.yaml": _companies(raw)}


def same_config(old: dict, new: dict) -> List[str]:
    """Differences that matter (board order is irrelevant)."""
    def canon(c):
        c = normalize(dict(c))
        # an empty list and "not set" behave the same
        c["profiles"] = [{k: v for k, v in pr.items() if v not in (None, [], {})} for pr in c["profiles"]]
        comp = c["sources"].get("companies")
        if comp and "boards" in comp:
            comp["boards"] = sorted(comp["boards"])
        return c
    a, b = canon(old), canon(new)
    return [k for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)]


def run(src: Path, dest: Path) -> int:
    if dest.exists():
        print(f"{dest} already exists; move it away first.")
        return 1
    raw = read_raw(src)
    files = split(raw)
    dest.mkdir()
    for name, text in files.items():
        (dest / name).write_text(text)
    diff = same_config(raw, read_raw(dest))
    if diff:
        for f in files:
            (dest / f).unlink()
        dest.rmdir()
        print(f"Conversion would change: {', '.join(diff)}. Nothing written.")
        return 1
    print(f"Wrote {dest}/ ({', '.join(files)}); it loads to the same configuration as {src.name}.")
    print(f"yojobs now uses {dest}/. Keep {src.name} as a backup or delete it.")
    return 0
