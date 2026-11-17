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


def render(jobs: List[Job], stats: Sequence[Tuple[str, str, str]]) -> Tuple[str, str]:
    """Return (plain_text, html) bodies."""
    lines, rows = [], []
    for j in jobs:
        date = j.published.strftime("%d %b") if j.published else ""
        place = _short(j.location, 60) + (f" ({j.work_hint})" if j.work_hint else "")
        meta = " · ".join(x for x in [j.company, place.strip(), j.salary, f"{j.source} {date}".strip()] if x)
        note = f"  ({'; '.join(j.notes)})" if j.notes else ""
        lines += [f"[{j.score}] {j.title}{note}", f"    {meta}", f"    matched: {', '.join(j.matched)}", f"    {j.url}", ""]
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
            + '</div></td></tr>'
        )

    problems = [(n, m) for n, s, m in stats if s != "ok"]
    if problems:
        lines.append("Source problems:")
        lines += [f"  {n}: {m}" for n, m in problems]
    footer = "".join(f"<li>{html.escape(n)}: {html.escape(m)}</li>" for n, m in problems)
    html_body = (
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:680px">'
        f'<table style="border-collapse:collapse;width:100%">{"".join(rows)}</table>'
        + (f'<p style="font-size:12px;color:#b00">Source problems:</p><ul style="font-size:12px;color:#b00">{footer}</ul>' if problems else "")
        + "</div>"
    )
    return "\n".join(lines), html_body


def send(cfg: dict, jobs: List[Job], stats) -> None:
    user = cfg["username"]
    to = cfg.get("to") or user
    top = jobs[0].title if jobs else ""
    msg = EmailMessage()
    msg["Subject"] = f"yojobs: {len(jobs)} new job{'s' if len(jobs) != 1 else ''}" + (f" — {_short(top, 60)}" if top else "")
    msg["From"] = cfg.get("from") or user
    msg["To"] = to
    text, html_body = render(jobs, stats)
    msg.set_content(text)
    msg.add_alternative(html_body, subtype="html")

    host, port = cfg.get("smtp_host", "smtp.gmail.com"), int(cfg.get("smtp_port", 465))
    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as s:
        s.login(user, keychain_password(user))
        s.send_message(msg)
