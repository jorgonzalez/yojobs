"""Run: python -m yojobs [--email] [--config config.yaml] [--source NAME ...] [--days N] [--all]

Without --email: preview in the terminal (new jobs marked with *), nothing saved.
With --email: email only jobs not reported before, then remember them."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import filter as jobfilter
from . import mailer
from .progress import say
from .sources import SOURCES
from .store import Store

ROOT = Path(__file__).resolve().parent.parent  # repo dir; launchd runs from elsewhere


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


def load_config(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"Config not found: {path}. Copy config.example.yaml to config.yaml first.")
    with path.open() as fh:
        return yaml.load(fh, Loader=_StrictLoader) or {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="yojobs")
    ap.add_argument("--config", default=ROOT / "config.yaml", type=Path)
    ap.add_argument("--email", action="store_true", help="email new jobs and remember them")
    ap.add_argument("--source", action="append", help="only run this source (repeatable)")
    ap.add_argument("--days", type=float, help="override max_age_days")
    ap.add_argument("--all", action="store_true", help="skip keyword filtering (debug)")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    store = Store(ROOT / cfg.get("database", "seen.sqlite"), key_days=cfg.get("dedupe_days", 60))
    if args.days is not None:
        days = args.days
    elif store.is_empty():
        days = cfg.get("first_run_days", 30)
        say(f"First run (no jobs remembered yet): looking back {days:g} days instead of {cfg.get('max_age_days', 3):g}")
    else:
        days = cfg.get("max_age_days", 3)
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
        scfg = dict(scfg, _keywords=sorted(terms),
                    _title_ok=lambda job: any(jobfilter.title_ok(job, p) for p in profiles))
        selected[name] = scfg

    results, stats = [], []
    say(f"Checking {len(selected)} sources for jobs from the last {days:g} days")
    for i, (name, scfg) in enumerate(selected.items(), 1):
        t0 = time.time()
        say(f"[{i}/{len(selected)}] {name}...")
        try:
            jobs = SOURCES[name](scfg, since)
        except Exception as exc:  # one broken portal must not stop the run
            stats.append((name, "ERROR", f"{type(exc).__name__}: {exc}"))
            say(f"[{i}/{len(selected)}] {name}: ERROR {type(exc).__name__}: {exc}")
            continue
        recent = [j for j in jobs if j.published is None or j.published >= since]
        if args.all:
            kept = recent
        else:
            kept = [j for j in recent if any(jobfilter.apply(j, p) for p in profiles)]
        results.extend(kept)
        stats.append((name, "ok", f"{len(jobs)} fetched, {len(recent)} from last {days:g} days, {len(kept)} matched ({time.time() - t0:.1f}s)"))
        say(f"[{i}/{len(selected)}] {name}: {len(kept)} matched ({time.time() - t0:.0f}s)")

    results.sort(key=lambda j: (j.score, j.published or since), reverse=True)

    new = store.filter_new(results)
    say(f"{len(results)} matches, {len(new)} not sent before")
    new_ids = {id(j) for j in new}

    if args.email:
        if new:
            say(f"Sending email with {len(new)} jobs...")
            mailer.send(cfg.get("email") or {}, new, stats)
            store.mark_seen(new)
        print(f"{datetime.now():%Y-%m-%d %H:%M} emailed {len(new)} new of {len(results)} matches")
        for name, status, msg in stats:
            print(f"  {name:15} {status:5} {msg}")
        return 1 if stats and all(s[1] == "ERROR" for s in stats) else 0

    for j in results:
        date = j.published.strftime("%Y-%m-%d") if j.published else "?"
        mark = "*" if id(j) in new_ids else " "
        print(f"{mark}[{j.score}] {j.title} — {j.company}  ({j.source}, {date})")
        loc = j.location if len(j.location) <= 80 else j.location[:77] + "..."
        extras = " | ".join(x for x in [loc, j.salary, ", ".join(j.matched), "; ".join(j.notes).upper()] if x)
        if extras:
            print(f"     {extras}")
        print(f"     {j.url}")

    print(f"\n{len(results)} jobs, last {days:g} days ({len(new)} new, marked *)")
    for name, status, msg in stats:
        print(f"  {name:15} {status:5} {msg}")
    return 1 if stats and all(s[1] == "ERROR" for s in stats) else 0


if __name__ == "__main__":
    sys.exit(main())
