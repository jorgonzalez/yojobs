"""Configuration: a config/ folder of small YAML files (or the older single config.yaml).

config/
  settings.yaml   how yojobs runs: look-back, schedule, email, database, weekly, health
  profile.yaml    what you're looking for (title words, required/excluded words, places)
  blocklist.yaml  companies you never want to see
  sources.yaml    which portals are on/off, plus their options
  searches.yaml   LinkedIn/Indeed search terms x places
  companies.yaml  company career pages, grouped by hiring system

Every *.yaml file in the folder is read; their top-level keys are merged, and the
same key in two files is an error (as is a duplicate key inside one file).

The new, friendlier format is converted into the internal structure the rest of
yojobs uses (`profiles`, `sources.<name>.searches`, `sources.companies.boards`...),
so old single-file configs keep working unchanged. Renamed profile keys:
  title_must_have -> groups       ad_must_mention -> all_of
  exclude_titles  -> none_of      where: {onsite_cities, remote_regions}
(the old names are still accepted).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List

import yaml

SYSTEMS = ("greenhouse", "lever", "ashby", "personio", "recruitee")
SEARCH_SOURCES = ("linkedin", "indeed", "stepstone")


class ConfigError(Exception):
    pass


class _StrictLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate keys (plain YAML silently keeps the last)."""


def _no_duplicates(loader, node, deep=False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate key {key!r} in config", key_node.start_mark)
        seen.add(key)
    return loader.construct_mapping(node, deep)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates)


def _read_yaml(path: Path) -> dict:
    with path.open() as fh:
        data = yaml.load(fh, Loader=_StrictLoader) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected 'key: value' settings at the top level")
    return data


def read_raw(path: Path) -> dict:
    """Merge every *.yaml in a folder (or read one file), without normalizing."""
    if path.is_dir():
        merged, origin = {}, {}
        for f in sorted(path.glob("*.yaml")):
            for key, value in _read_yaml(f).items():
                if key in merged:
                    raise ConfigError(f"'{key}' is set in both {origin[key]} and {f.name}; keep only one")
                merged[key], origin[key] = value, f.name
        return merged
    return _read_yaml(path)


# --- normalization: friendly format -> internal structure --------------------

def _flatten(value) -> List[str]:
    """exclude_titles may be a list, or named groups of lists."""
    if isinstance(value, dict):
        return [w for words in value.values() for w in (words or [])]
    return list(value or [])


def _profile(p: dict) -> dict:
    p = dict(p)
    renames = {"title_must_have": "groups", "ad_must_mention": "all_of", "ad_must_mention_in": "all_of_in",
               "exclude_titles": "none_of", "exclude_in": "exclude_in", "title_any": "any_of"}
    for new, old in renames.items():
        if new in p:
            p[old] = p.pop(new)
    p["none_of"] = _flatten(p.get("none_of"))
    where = p.pop("where", None) or {}
    for key in ("onsite_cities", "remote_regions"):
        if key in where:
            p[key] = where[key]
    p.setdefault("name", "profile")
    return p


def _source_entry(value) -> dict:
    """`remotive: on` / `off` / `{enabled: true, max_pages: 20}`."""
    if isinstance(value, bool):
        return {"enabled": value}
    if value is None:
        return {"enabled": True}
    if isinstance(value, dict):
        return dict(value)
    raise ConfigError(f"source settings must be on, off or a mapping, not {value!r}")


def _expand_searches(groups) -> Dict[str, List[dict]]:
    """searches: [{terms: [...], places: [...], only: [linkedin]}] -> per-source lists,
    places outer, terms inner (Berlin x every term, then Germany x every term...)."""
    out: Dict[str, List[dict]] = {s: [] for s in SEARCH_SOURCES}
    if isinstance(groups, dict):
        groups = [groups]
    for g in groups or []:
        only = g.get("only") or list(SEARCH_SOURCES)
        only = [only] if isinstance(only, str) else only
        for place in g.get("places") or [{}]:
            for term in g.get("terms") or []:
                search = {"term": term, **{k: v for k, v in place.items() if k != "only"}}
                for s in (place.get("only") and [place["only"]]) or only:
                    out[s].append(search)
    return out


def normalize(raw: dict) -> dict:
    cfg = dict(raw)
    sources = {name: _source_entry(v) for name, v in (cfg.get("sources") or {}).items()}

    if "searches" in cfg:  # searches.yaml -> sources.linkedin/indeed.searches
        expanded = _expand_searches(cfg.pop("searches"))
        for s in SEARCH_SOURCES:
            if expanded[s] and s in sources:
                sources[s].setdefault("searches", expanded[s])

    if "companies" in cfg:  # companies.yaml -> sources.companies.boards
        boards = [f"{system}:{board}" for system, ids in (cfg.pop("companies") or {}).items()
                  for board in (ids or [])]
        unknown = {b.split(":")[0] for b in boards} - set(SYSTEMS)
        if unknown:
            raise ConfigError(f"companies: unknown hiring system(s) {sorted(unknown)}; use {', '.join(SYSTEMS)}")
        sources.setdefault("companies", {"enabled": True}).setdefault("boards", boards)
    cfg["sources"] = sources

    profiles = cfg.pop("profiles", None) or []
    if "profile" in cfg:
        profiles = [cfg.pop("profile")] + list(profiles)
    cfg["profiles"] = [_profile(p) for p in profiles]
    return cfg


def default_path(root: Path) -> Path:
    """config/ if it exists, else the older single config.yaml."""
    folder = root / "config"
    return folder if folder.is_dir() else root / "config.yaml"


def load_config(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"Config not found: {path}. Copy config.example/ to config/ first "
                 f"(cp -R config.example config).")
    try:
        return normalize(read_raw(path))
    except (ConfigError, yaml.YAMLError) as exc:
        sys.exit(f"Config problem: {exc}")
