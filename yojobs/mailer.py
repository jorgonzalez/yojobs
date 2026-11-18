"""Email the new jobs via SMTP (Gmail by default).

The SMTP password is read from the macOS Keychain, never from config:
  security add-generic-password -s yojobs-smtp -a you@gmail.com -w
(For Gmail use an App Password: https://myaccount.google.com/apppasswords)"""
from __future__ import annotations

import html
import smtplib
import ssl
import subprocess
from email.message import EmailMessage
from typing import List, Sequence, Tuple

from .models import Job

KEYCHAIN_SERVICE = "yojobs-smtp"


def keychain_password(account: str) -> str:
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", account, "-w"],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError:
        raise RuntimeError(
            f"No SMTP password in Keychain for {account}. Add it with:\n"
            f"  security add-generic-password -s {KEYCHAIN_SERVICE} -a {account} -w"
        )
    # Gmail shows App Passwords as "abcd efgh ijkl mnop"; spaces (incl. non-breaking) aren't part of it
    password = "".join(out.stdout.split())
    if not password:
        raise RuntimeError(
            f"The Keychain entry for {account} is empty. Re-add it from a normal Terminal window:\n"
            f"  security add-generic-password -U -s {KEYCHAIN_SERVICE} -a {account} -w"
        )
    return password


def _short(s: str, n: int = 90) -> str:
    return s if len(s) <= n else s[: n - 3] + "..."


def match_line(m: dict) -> str:
    """'CV match 82% · strong: a, b · gaps: c'"""
    parts = [f"CV match {m['score']}%"] + [f"{k}: {v}" for k, v in (m.get("ratings") or {}).items()]
    if m.get("strengths"):
        parts.append("strong: " + ", ".join(m["strengths"]))
    if m.get("gaps"):
        parts.append("gaps: " + ", ".join(m["gaps"]))
    return " · ".join(parts)


def _match_html(m: dict) -> str:
    score = m["score"]
    color = ("#15803d", "#dcfce7") if score >= 75 else ("#a16207", "#fef9c3") if score >= 50 else ("#6b7280", "#f3f4f6")
    e = html.escape
    return (f'<div style="font-size:12px;margin-top:4px">'
            f'<span style="display:inline-block;padding:1px 7px;border-radius:10px;font-weight:600;'
            f'color:{color[0]};background:{color[1]}">CV match {score}%</span>'
            + "".join(f' <span style="color:#555">{e(k)}: <b>{e(v)}</b></span>' for k, v in (m.get("ratings") or {}).items())
            + (f' <span style="color:#15803d">✓ {e(", ".join(m.get("strengths") or []))}</span>' if m.get("strengths") else "")
            + (f' <span style="color:#a16207">△ {e(", ".join(m.get("gaps") or []))}</span>' if m.get("gaps") else "")
            + (f'<div style="color:#666;margin-top:2px">{e(m.get("summary") or "")}</div>' if m.get("summary") else "")
            + "</div>")


def render(jobs: List[Job], stats: Sequence[Tuple[str, str, str]],
           warnings: Sequence[str] = ()) -> Tuple[str, str]:
    """Return (plain_text, html) bodies."""
    lines, rows = [], []
    if warnings:
        lines += ["Source warnings:"] + [f"  ! {w}" for w in warnings] + [""]
    for j in jobs:
        date = j.published.strftime("%d %b") if j.published else ""
        place = _short(j.location, 60) + (f" ({j.work_hint})" if j.work_hint else "")
        meta = " · ".join(x for x in [j.company, place.strip(), j.salary, f"{j.source} {date}".strip()] if x)
        note = f"  ({'; '.join(j.notes)})" if j.notes else ""
        lines += [f"[{j.score}] {j.title}{note}", f"    {meta}", f"    matched: {', '.join(j.matched)}"]
        if j.match:
            lines += [f"    {match_line(j.match)}"] + ([f"    {j.match['summary']}"] if j.match.get("summary") else [])
        lines += [f"    {j.url}", ""]
        e = html.escape
        rows.append(
            f'<tr><td style="padding:10px 0;border-bottom:1px solid #e5e5e5;vertical-align:top">'
            f'<span style="display:inline-block;min-width:22px;padding:1px 6px;border-radius:10px;'
            f'background:#eef3ff;color:#2550c0;font-size:12px;text-align:center">{j.score}</span></td>'
            f'<td style="padding:10px 0 10px 10px;border-bottom:1px solid #e5e5e5">'
            f'<a href="{e(j.url)}" style="font-size:15px;font-weight:600;color:#1a1a1a;text-decoration:none">{e(j.title)}</a>'
            f'<div style="font-size:13px;color:#555;margin-top:2px">{e(meta)}</div>'
            f'<div style="font-size:12px;color:#888;margin-top:2px">{e(", ".join(j.matched))}'
            + (f' · <span style="color:#b45309">{e("; ".join(j.notes))}</span>' if j.notes else "")
            + '</div>' + (_match_html(j.match) if j.match else "") + '</td></tr>'
        )

    problems = [(n, m) for n, s, m in stats if s == "ERROR"]  # planned skips (runs_per_day) are not problems
    if problems:
        lines.append("Source problems:")
        lines += [f"  {n}: {m}" for n, m in problems]
    footer = "".join(f"<li>{html.escape(n)}: {html.escape(m)}</li>" for n, m in problems)
    warn_html = "".join(f"<li>{html.escape(w)}</li>" for w in warnings)
    html_body = (
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:680px">'
        + (f'<div style="background:#fff7ed;border:1px solid #fdba74;border-radius:6px;padding:8px 12px;'
           f'margin-bottom:12px;font-size:13px;color:#9a3412"><b>Source warnings</b><ul style="margin:4px 0">'
           f'{warn_html}</ul></div>' if warnings else "")
        + f'<table style="border-collapse:collapse;width:100%">{"".join(rows)}</table>'
        + (f'<p style="font-size:12px;color:#b00">Source problems:</p><ul style="font-size:12px;color:#b00">{footer}</ul>' if problems else "")
        + "</div>"
    )
    return "\n".join(lines), html_body


def send(cfg: dict, jobs: List[Job], stats, warnings: Sequence[str] = ()) -> None:
    """The alert email: new jobs, plus source warnings if any (it can be sent
    with warnings only, when a source broke but no new jobs were found)."""
    top = jobs[0].title if jobs else ""
    if jobs:
        subject = f"yojobs: {len(jobs)} new job{'s' if len(jobs) != 1 else ''}" + (f" — {_short(top, 60)}" if top else "")
    else:
        subject = f"yojobs: source problem ({len(warnings)})"
    text, html_body = render(jobs, stats, warnings)
    deliver(cfg, subject, text, html_body)


def deliver(cfg: dict, subject: str, text: str, html_body: str) -> None:
    user = cfg["username"]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.get("from") or user
    msg["To"] = cfg.get("to") or user
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")

    host, port = cfg.get("smtp_host", "smtp.gmail.com"), int(cfg.get("smtp_port", 465))
    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as s:
        s.login(user, keychain_password(user))
        s.send_message(msg)
