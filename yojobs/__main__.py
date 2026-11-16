"""Run: python -m yojobs [--config config.yaml] [--source NAME ...] [--days N] [--all]"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import filter as jobfilter
from .sources import SOURCES


def load_config(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"Config not found: {path}. Copy config.example.yaml to config.yaml first.")
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="yojobs")
    ap.add_argument("--config", default="config.yaml", type=Path)
    ap.add_argument("--source", action="append", help="only run this source (repeatable)")
    ap.add_argument("--days", type=float, help="override max_age_days")
    ap.add_argument("--all", action="store_true", help="skip keyword filtering (debug)")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    days = args.days if args.days is not None else cfg.get("max_age_days", 3)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    profiles = cfg.get("profiles") or []

    selected = {}
    for name, scfg in (cfg.get("sources") or {}).items():
        scfg = scfg or {}
        if args.source and name not in args.source:
            continue
        if not args.source and not scfg.get("enabled", True):
            continue
        if name not in SOURCES:
            print(f"[!] unknown source in config: {name}", file=sys.stderr)
            continue
        # sources with server-side search (e.g. himalayas) get search terms: a profile's
        # all_of words if it has any (every match must contain them), else its any_of words
        terms = {k for p in profiles for k in (p.get("all_of") or p.get("any_of") or [])}
        scfg = dict(scfg, _keywords=sorted(terms))
        selected[name] = scfg

    results, stats = [], []
    for name, scfg in selected.items():
        t0 = time.time()
        try:
            jobs = SOURCES[name](scfg, since)
        except Exception as exc:  # one broken portal must not stop the run
            stats.append((name, "ERROR", f"{type(exc).__name__}: {exc}"))
            continue
        recent = [j for j in jobs if j.published is None or j.published >= since]
        if args.all:
            kept = recent
        else:
            kept = [j for j in recent if any(jobfilter.apply(j, p) for p in profiles)]
        results.extend(kept)
        stats.append((name, "ok", f"{len(jobs)} fetched, {len(recent)} recent, {len(kept)} matched ({time.time() - t0:.1f}s)"))

    results.sort(key=lambda j: (j.score, j.published or since), reverse=True)

    for j in results:
        date = j.published.strftime("%Y-%m-%d") if j.published else "?"
        print(f"[{j.score}] {j.title} — {j.company}  ({j.source}, {date})")
        loc = j.location if len(j.location) <= 80 else j.location[:77] + "..."
        extras = " | ".join(x for x in [loc, j.salary, ", ".join(j.matched)] if x)
        if extras:
            print(f"     {extras}")
        print(f"     {j.url}")

    print(f"\n{len(results)} jobs, last {days:g} days")
    for name, status, msg in stats:
        print(f"  {name:15} {status:5} {msg}")
    return 1 if stats and all(s[1] == "ERROR" for s in stats) else 0


if __name__ == "__main__":
    sys.exit(main())
