"""The weekly summary email: is yojobs alive, how is each source doing, and the
near misses of the week (jobs that failed only the required words, e.g. a
platform leadership job whose ad never mentions Kubernetes).

config.yaml:
  weekly:
    enabled: true
    day: monday          # sent with the first scheduled run on/after this day
    near_misses: true

Send it now with:  python -m yojobs --weekly          (print only)
                   python -m yojobs --weekly --email  (send)
"""
from __future__ import annotations

import html
from datetime import datetime
from typing import List, Tuple

from .history import History


def _when(iso: str) -> str:
    if not iso:
        return "never"
    return datetime.fromisoformat(iso).astimezone().strftime("%a %d %b %H:%M")


def build(history: History, cfg: dict) -> Tuple[str, str, str, List[str]]:
    """-> (subject, text, html, near-miss urls listed)"""
    st = history.week_stats()
    near = history.pending_near_misses() if cfg.get("near_misses", True) else []
    alerted = set(st["alerted"])
    broken = [s for s in st["sources"] if s["source"] in alerted]
    parts = st["parts"]

    subject = (f"yojobs weekly: {st['runs']} runs, {st['emailed']} jobs emailed"
               + (f", {len(near)} near misses" if near else "")
               + (f", {len(broken)} source problem{'s' if len(broken) != 1 else ''}" if broken else "")
               + (f", {len(parts)} failing board{'s' if len(parts) != 1 else ''}" if parts else ""))

    # --- plain text ---
    t = [f"Last 7 days: {st['runs']} runs, ~{st['jobs_per_run']:,} jobs checked per run, "
         f"{st['emailed']} jobs emailed.", ""]
    if broken:
        t += ["Sources with problems: " + ", ".join(s["source"] for s in broken), ""]
    if near:
        t += [f"Near misses ({len(near)}): passed every rule except the required words. Worth a look:", ""]
        for n in near:
            date = n["published"][:10] if n["published"] else "?"
            t += [f"- {n['title']} — {n['company']}", f"    {n['location'][:80]} · {n['source']} {date} · {n['reason']}",
                  f"    {n['url']}"]
        t.append("")
    if parts:
        t += [f"Company boards that failed this week ({len(parts)}): check the jobs page, update or remove the entry:"]
        t += [f"  {p['part']:32} failed {p['failed']} of {p['runs']} runs  ({p['last_error'][:70]})" for p in parts]
        t.append("")
    t += ["Sources:", f"  {'source':20} {'runs':>4} {'errors':>6} {'jobs/run':>8} {'matched':>7}  last good run"]
    for s in st["sources"]:
        flag = " !" if s["source"] in alerted else ""
        t.append(f"  {s['source']:20} {s['runs']:>4} {s['errors']:>6} {s['avg_fetched']:>8} {s['matched']:>7}  "
                 f"{_when(s['last_ok'])}{flag}")

    # --- html ---
    e = html.escape
    cell = 'style="padding:3px 8px;border-bottom:1px solid #eee;font-size:12px"'
    rows = "".join(
        f'<tr style="{"background:#fff7ed;color:#9a3412" if s["source"] in alerted else ""}">'
        f'<td {cell}>{e(s["source"])}</td><td {cell} align="right">{s["runs"]}</td>'
        f'<td {cell} align="right">{s["errors"]}</td><td {cell} align="right">{s["avg_fetched"]:,}</td>'
        f'<td {cell} align="right">{s["matched"]}</td><td {cell}>{e(_when(s["last_ok"]))}</td></tr>'
        for s in st["sources"])
    near_html = "".join(
        f'<li style="margin-bottom:8px"><a href="{e(n["url"])}" style="font-weight:600;color:#1a1a1a">{e(n["title"])}</a>'
        f' — {e(n["company"])}<br><span style="font-size:12px;color:#666">{e(n["location"][:80])} · '
        f'{e(n["source"])} {e((n["published"] or "")[:10])} · <span style="color:#b45309">{e(n["reason"])}</span>'
        f'</span></li>' for n in near)
    body = (
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:680px">'
        f'<p style="font-size:14px">Last 7 days: <b>{st["runs"]}</b> runs, ~<b>{st["jobs_per_run"]:,}</b> jobs checked '
        f'per run, <b>{st["emailed"]}</b> jobs emailed.</p>'
        + (f'<p style="font-size:13px;color:#9a3412">Sources with problems: '
           f'{e(", ".join(s["source"] for s in broken))}</p>' if broken else "")
        + (f'<h3 style="font-size:15px;margin:18px 0 4px">Near misses ({len(near)})</h3>'
           f'<p style="font-size:12px;color:#666;margin:0 0 8px">Passed every rule except the required words. '
           f'Worth a look: recruiters often leave them out.</p><ul style="padding-left:18px">{near_html}</ul>'
           if near else "")
        + (f'<h3 style="font-size:15px;margin:18px 0 4px">Company boards that failed this week ({len(parts)})</h3>'
           f'<p style="font-size:12px;color:#666;margin:0 0 6px">Check the jobs page, then update or remove the '
           f'entry in config.yaml.</p><ul style="font-size:12px;padding-left:18px">'
           + "".join(f'<li><b>{e(p["part"])}</b>: failed {p["failed"]} of {p["runs"]} runs '
                     f'<span style="color:#888">({e(p["last_error"][:90])})</span></li>' for p in parts)
           + "</ul>" if parts else "")
        + '<h3 style="font-size:15px;margin:18px 0 4px">Sources</h3>'
        f'<table style="border-collapse:collapse"><tr><th {cell} align="left">source</th><th {cell}>runs</th>'
        f'<th {cell}>errors</th><th {cell}>jobs/run</th><th {cell}>matched</th><th {cell} align="left">last good run</th>'
        f'</tr>{rows}</table></div>')
    return subject, "\n".join(t), body, [n["url"] for n in near]
