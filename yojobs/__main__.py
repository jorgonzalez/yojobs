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

from . import filter as jobfilter
from . import __version__, mailer, matching, weekly, workmode
from .history import History, SourceRun
from . import progress
from .progress import note, say, step
from .schedule import RunLock, State, is_due, trim_log
from .sources import SOURCES
from .config import default_path, load_config
from .models import Job
from .store import Store, norm_company

ROOT = Path(__file__).resolve().parent.parent  # repo dir; launchd runs from elsewhere


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="yojobs")
    ap.add_argument("--version", action="version", version=f"yojobs {__version__}")
    ap.add_argument("--config", type=Path, help="config folder or file (default: config/, else config.yaml)")
    ap.add_argument("--email", action="store_true", help="email new jobs and remember them")
    ap.add_argument("--source", action="append", help="only run this source (repeatable)")
    ap.add_argument("--days", type=float, help="override max_age_days")
    ap.add_argument("--all", action="store_true", help="skip keyword filtering (debug)")
    ap.add_argument("--scheduled", action="store_true", help="launchd mode: --email only when a run is due")
    ap.add_argument("--check-schedule", action="store_true", help="only say whether a scheduled run is due")
    ap.add_argument("--weekly", action="store_true",
                    help="build the weekly summary now (print it; with --email, send it)")
    ap.add_argument("--split-config", action="store_true",
                    help="convert config.yaml into the config/ folder (checks the result is identical)")
    ap.add_argument("--match", metavar="LINK|FILE|-",
                    help="score one job ad against your CV: a link, a .txt/.md/.pdf/.docx/.html file, "
                         "or - for pasted text (e.g. pbpaste | ... --match -)")
    ap.add_argument("--criteria", metavar="A,B,...",
                    help="CV match criteria for this run only, e.g. role,skills,gaps,wishes "
                         "(any of role, skills, seniority, gaps, wishes; overrides config/matching.yaml)")
    ap.add_argument("--cv-check", action="store_true",
                    help="show the CV match setup (CV file, wishes, Ollama) without scoring")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="print every step on its own line (default: one status line)")
    args = ap.parse_args(argv)
    # the launchd log is always verbose
    progress.set_verbose(args.verbose or args.scheduled)

    if args.split_config:
        from .config_split import run as split_run
        return split_run(args.config or ROOT / "config.yaml", ROOT / "config")
    cfg = load_config(args.config or default_path(ROOT))
    store = Store(ROOT / cfg.get("database", "seen.sqlite"), key_days=cfg.get("dedupe_days", 60))
    if args.criteria:  # one-off override of config/matching.yaml
        cfg["matching"] = dict(cfg.get("matching") or {},
                               criteria=[c.strip() for c in args.criteria.split(",") if c.strip()])
    if args.cv_check:
        code = matching.check(cfg, ROOT)
        # on its own it only shows the setup; with run options it shows it, then runs
        wants_run = any([args.email, args.days is not None, args.source, args.all, args.match,
                         args.weekly, args.scheduled, args.verbose])
        if not wants_run:
            return code
        print()
    if args.match:
        return matching.match_one(cfg, ROOT, args.match)
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
        # checks run every 10 minutes: log "not due" at most once an hour
        if args.check_schedule or state.log_once_per_hour(now):
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


def _near_miss_scorer(cfg: dict, store: Store):
    """CV-score the weekly near misses (if matching is on): best first in the email.
    Up to weekly.near_misses_scored (15); cached like the alert emails' scores."""
    def score(near):
        limit = int((cfg.get("weekly") or {}).get("near_misses_scored", 15))
        jobs = [Job(source=n["source"], title=n["title"], company=n["company"], url=n["url"],
                    location=n["location"], description=n.get("description") or "") for n in near]
        mcfg = dict(cfg, matching=dict(cfg.get("matching") or {}, max_jobs_per_run=limit))
        matching.score_jobs(jobs, mcfg, ROOT, store.db)
        for n, j in zip(near, jobs):
            if j.match:
                n["match"] = j.match
    return score


def send_weekly(args, cfg: dict, store: Store) -> int:
    history = History(store.db)
    weekly_cfg = cfg.get("weekly") or {}
    found = []
    limit = int(weekly_cfg.get("discover_boards", 15))
    if limit > 0:  # job boards of companies from recent matches / near misses
        from . import discovery
        found = discovery.run(store.db, cfg, limit=limit)
    subject, text, html_body, urls = weekly.build(history, weekly_cfg, score=_near_miss_scorer(cfg, store),
                                                  searches=weekly.search_labels(cfg.get("sources") or {}),
                                                  discoveries=found)
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


def _company_key(name: str) -> str:
    """'GetYourGuide' == 'Get Your Guide GmbH' == 'getyourguide'."""
    return norm_company(name).replace(" ", "")


def run(args, cfg: dict, store: Store, days: float):
    """One full pass. Returns (exit code, ok) where ok means the run did its job."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    profiles = cfg.get("profiles") or []

    selected = {}
    history_now = History(store.db)
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
                    _title_ok=lambda job: any(jobfilter.title_ok(job, p) for p in profiles),
                    # already emailed or already a near miss: sources can skip extra requests for it
                    _known=lambda job: store.is_seen(job) or history_now.known_near_miss(job.url),
                    # when this source last ran fully: sources with their own lookback can start there
                    _last_full_run=history_now.last_full_run(name))
        selected[name] = scfg

    results, stats, source_runs, near = [], [], [], []
    # companies you never want to hear from (applied already, not interested...)
    blocked = {_company_key(c) for c in cfg.get("blocked_companies") or [] if str(c).strip()}
    say(f"Checking {len(selected)} sources for jobs from the last {days:.3g} days")
    for i, (name, scfg) in enumerate(selected.items(), 1):
        t0 = time.time()
        scfg["_problems"] = []  # parts of a source that failed (e.g. one company board)
        step(f"[{i}/{len(selected)}] {name}")
        # runs_per_day (e.g. LinkedIn once a day): skip the source after its daily runs,
        # unless asked for explicitly with --source
        limit = scfg.get("runs_per_day")
        if limit and not args.source and history_now.full_runs_today(name) >= int(limit):
            stats.append((name, "skip", f"already ran {limit}x today (runs_per_day)"))
            say(f"[{i}/{len(selected)}] {name}: skipped, already ran {limit}x today (runs_per_day: {limit})")
            continue
        try:
            jobs = SOURCES[name](scfg, since)
        except Exception as exc:  # one broken portal must not stop the run
            stats.append((name, "ERROR", f"{type(exc).__name__}: {exc}"))
            source_runs.append(SourceRun(name, "ERROR", seconds=time.time() - t0, error=f"{type(exc).__name__}: {exc}"[:300]))
            note(f"[{i}/{len(selected)}] {name}: ERROR {type(exc).__name__}: {exc}")
            continue
        recent = [j for j in jobs if j.published is None or j.published >= since]
        if blocked:
            recent = [j for j in recent if _company_key(j.company) not in blocked]
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
        source_runs.append(SourceRun(name, "ok", len(jobs), len(recent), len(kept), time.time() - t0,
                                     parts_failed=list(scfg["_problems"])))
        stats.append((name, "ok", f"{len(jobs)} fetched, {len(recent)} from last {days:g} days, {len(kept)} matched ({time.time() - t0:.1f}s)"))
        say(f"[{i}/{len(selected)}] {name}: {len(kept)} matched ({time.time() - t0:.0f}s)")

    progress.end()
    results.sort(key=lambda j: (j.score, j.published or since), reverse=True)

    new = store.filter_new(results)
    # optional CV match (config/matching.yaml): score the new jobs, best first; never hides any
    matching.score_jobs(new, cfg, ROOT, store.db)
    new = matching.by_score(new)
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
        if j.match:
            print(f"     {mailer.match_line(j.match)}")
        print(f"     {j.url}")

    print(f"\n{len(results)} jobs, last {days:g} days ({len(new)} new, marked *)")
    for name, status, msg in stats:
        print(f"  {name:15} {status:5} {msg}")
    return (1, False) if all_failed else (0, True)


if __name__ == "__main__":
    sys.exit(main())
