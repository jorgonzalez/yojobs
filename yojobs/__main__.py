"""Run: python -m yojobs [--email | --scheduled | --check-schedule] [--config config.yaml]
                       [--source NAME ...] [--days N] [--all]

Without --email: preview in the terminal (new jobs marked with *), nothing saved.
With --email: email only jobs not reported before, then remember them.
With --scheduled (used by launchd every 30 min): run with --email only if a run is
due per the `schedule` config; never two at once; looks back to the last run."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import filter as jobfilter
from . import mailer, weekly, workmode
from .history import History, SourceRun
from . import progress
from .progress import note, say, step
from .schedule import RunLock, State, is_due, trim_log
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
    ap.add_argument("--scheduled", action="store_true", help="launchd mode: --email only when a run is due")
    ap.add_argument("--check-schedule", action="store_true", help="only say whether a scheduled run is due")
    ap.add_argument("--weekly", action="store_true",
                    help="build the weekly summary now (print it; with --email, send it)")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="print every step on its own line (default: one status line)")
    args = ap.parse_args(argv)
    # the launchd log is always verbose
    progress.set_verbose(args.verbose or args.scheduled)

    cfg = load_config(args.config)
    store = Store(ROOT / cfg.get("database", "seen.sqlite"), key_days=cfg.get("dedupe_days", 60))
    if args.scheduled or args.check_schedule:
        return scheduled(args, cfg, store)

    # Manual runs take the same lock as scheduled ones, so they never overlap
    # (two runs at once could email the same jobs twice).
    lock = RunLock(ROOT / "yojobs.lock")
    if not lock.acquire():
        note("Another yojobs run is in progress (manual or scheduled); try again when it has finished")
        return 1
    try:
        if args.weekly:
            return send_weekly(args, cfg, store)
        if args.days is not None:
            days = args.days
        elif store.is_empty():
            days = cfg.get("first_run_days", 30)
            note(f"First run (no jobs remembered yet): looking back {days:g} days instead of {cfg.get('max_age_days', 3):g}")
        else:
            days = cfg.get("max_age_days", 3)
        code, _ok = run(args, cfg, store, days)
        return code
    finally:
        lock.release()


def scheduled(args, cfg: dict, store: Store) -> int:
    trim_log(Path.home() / "Library" / "Logs" / "yojobs.log")
    state = State(ROOT / cfg.get("schedule_state", "schedule_state.json"))
    now = datetime.now()
    due, reason = is_due(cfg.get("schedule") or {}, state, now)
    if args.check_schedule or not due:
        note(f"Scheduled run {'due' if due else 'not due'}: {reason}")
        return 0

    lock = RunLock(ROOT / "yojobs.lock")
    if not lock.acquire():
        note("Another yojobs run is still in progress; skipping this one")
        return 0
    try:
        note(f"Scheduled run starting ({reason})")
        max_age = cfg.get("max_age_days", 3)
        if store.is_empty():
            days = cfg.get("first_run_days", 30)
        elif state.last_run:
            # cover everything since the previous run (+1h margin), at least max_age_days
            gap_days = (now - state.last_run).total_seconds() / 86400 + 1 / 24
            days = min(max(max_age, gap_days), cfg.get("first_run_days", 30))
        else:
            days = max_age
        args.email = True
        code, ok = run(args, cfg, store, days)
        if ok:
            state.record_run(now)
            note("Scheduled run finished and recorded")
            weekly_cfg = cfg.get("weekly") or {}
            if History(store.db).weekly_due(weekly_cfg, now.date()):
                args.email = True
                send_weekly(args, cfg, store)  # a failure here is retried on the next run
        else:
            note("Scheduled run failed (no source answered or email not sent); will retry next tick")
        return code
    finally:
        lock.release()


def send_weekly(args, cfg: dict, store: Store) -> int:
    history = History(store.db)
    weekly_cfg = cfg.get("weekly") or {}
    subject, text, html_body, urls = weekly.build(history, weekly_cfg)
    if not args.email:
        print(subject + "\n\n" + text)
        return 0
    note(f"Sending the weekly summary ({len(urls)} near misses)...")
    try:
        mailer.deliver(cfg.get("email") or {}, subject, text, html_body)
    except Exception as exc:
        note(f"Weekly email failed: {type(exc).__name__}: {exc}")
        return 1
    history.mark_digested(urls)
    history.mark_weekly_sent(datetime.now().date())
    return 0


def run(args, cfg: dict, store: Store, days: float):
    """One full pass. Returns (exit code, ok) where ok means the run did its job."""
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
            note(f"Unknown source in config: {name}")
            continue
        # sources with server-side search (e.g. himalayas) get search terms: a profile's
        # all_of words if it has any (every match must contain them), else its any_of words
        terms = {alt.strip() for p in profiles for k in (p.get("all_of") or p.get("any_of") or [])
                 for alt in k.split("|")}
        scfg = dict(scfg, _keywords=sorted(terms),
                    _title_ok=lambda job: any(jobfilter.title_ok(job, p) for p in profiles))
        selected[name] = scfg

    results, stats, source_runs, near = [], [], [], []
    say(f"Checking {len(selected)} sources for jobs from the last {days:.3g} days")
    for i, (name, scfg) in enumerate(selected.items(), 1):
        t0 = time.time()
        step(f"[{i}/{len(selected)}] {name}")
        try:
            jobs = SOURCES[name](scfg, since)
        except Exception as exc:  # one broken portal must not stop the run
            stats.append((name, "ERROR", f"{type(exc).__name__}: {exc}"))
            source_runs.append(SourceRun(name, "ERROR", seconds=time.time() - t0, error=f"{type(exc).__name__}: {exc}"[:300]))
            note(f"[{i}/{len(selected)}] {name}: ERROR {type(exc).__name__}: {exc}")
            continue
        recent = [j for j in jobs if j.published is None or j.published >= since]
        if args.all:
            kept = recent
        else:
            kept = [j for j in recent if any(jobfilter.apply(j, p) for p in profiles)]
            if args.email:  # jobs that failed only the required words, for the weekly email
                kept_ids = {id(j) for j in kept}
                for j in recent:
                    if id(j) not in kept_ids:
                        reason = next((r for r in (jobfilter.near_miss(j, p) for p in profiles) if r), "")
                        if reason:
                            near.append((j, reason))
        for j in kept:
            if not jobfilter.is_remote(j):  # on-site / hybrid (e.g. Berlin): say how much office
                j.work_hint = workmode.describe(j)
        results.extend(kept)
        source_runs.append(SourceRun(name, "ok", len(jobs), len(recent), len(kept), time.time() - t0))
        stats.append((name, "ok", f"{len(jobs)} fetched, {len(recent)} from last {days:g} days, {len(kept)} matched ({time.time() - t0:.1f}s)"))
        say(f"[{i}/{len(selected)}] {name}: {len(kept)} matched ({time.time() - t0:.0f}s)")

    progress.end()
    results.sort(key=lambda j: (j.score, j.published or since), reverse=True)

    new = store.filter_new(results)
    note(f"{len(results)} matches, {len(new)} not sent before")
    new_ids = {id(j) for j in new}

    all_failed = bool(stats) and all(s[1] == "ERROR" for s in stats)
    if args.email:
        if all_failed:
            # most likely no internet: not recorded, so it doesn't count against the sources
            note("Every source failed (no internet?); nothing emailed")
            return 1, False
        history = History(store.db)
        history.record(source_runs)
        history.add_near_misses(near)
        failed_runs = int((cfg.get("health") or {}).get("failed_runs", 3))
        broken, recovered = history.health_changes([r.source for r in source_runs], failed_runs)
        warnings = [f"{s} {why}" for s, why in broken.items()]
        for w in warnings:
            note(f"Source warning: {w}")
        if new or warnings:
            note(f"Sending email with {len(new)} jobs" + (f" and {len(warnings)} source warnings" if warnings else "") + "...")
            try:
                mailer.send(cfg.get("email") or {}, new, stats, warnings)
            except Exception as exc:
                note(f"Email failed: {type(exc).__name__}: {exc}")
                return 1, False  # jobs not marked as seen: they go out next time
            store.mark_seen(new)
        history.mark_alerted(list(broken), recovered)
        print(f"{datetime.now():%Y-%m-%d %H:%M} emailed {len(new)} new of {len(results)} matches")
        for name, status, msg in stats:
            print(f"  {name:15} {status:5} {msg}")
        return 0, True

    for j in results:
        date = j.published.strftime("%Y-%m-%d") if j.published else "?"
        mark = "*" if id(j) in new_ids else " "
        print(f"{mark}[{j.score}] {j.title} — {j.company}  ({j.source}, {date})")
        loc = j.location if len(j.location) <= 80 else j.location[:77] + "..."
        loc += f" ({j.work_hint})" if j.work_hint else ""
        extras = " | ".join(x for x in [loc, j.salary, ", ".join(j.matched), "; ".join(j.notes).upper()] if x)
        if extras:
            print(f"     {extras}")
        print(f"     {j.url}")

    print(f"\n{len(results)} jobs, last {days:g} days ({len(new)} new, marked *)")
    for name, status, msg in stats:
        print(f"  {name:15} {status:5} {msg}")
    return (1, False) if all_failed else (0, True)


if __name__ == "__main__":
    sys.exit(main())
