"""Get one job ad's text from a link, a file or pasted text, for `--match`.

  link   Greenhouse / Lever / Ashby / Personio / Recruitee: their official APIs
         (clean, complete); any other page: its embedded JobPosting data
         (schema.org JSON-LD), else the page's visible text. A page that's blocked
         (403/429, bot challenge, timeout) isn't worked around: save it from the
         browser (File > Save As... HTML, or Print > Save as PDF) and use the file.
  file   .txt .md (as is), .pdf (pypdf), .docx (macOS textutil), .html/.htm (like a
         page: JobPosting data first, else visible text)
  -      text from standard input, e.g.  pbpaste | python -m yojobs --match -
"""
from __future__ import annotations

import html as htmllib
import json
import re
import subprocess
import sys
import urllib.error
from pathlib import Path
from typing import Optional

from .http import get_bytes, get_json
from .models import Job, strip_html


class BlockedError(Exception):
    """The site refused or challenged us; the user should save the page instead."""


SAVE_HINT = ("save the page from your browser (File > Save As... > Web Page, HTML only; or "
             "Print > Save as PDF) and run: python -m yojobs --match <saved file>")

_CHALLENGE = re.compile(r"cf-chl|challenge-platform|captcha|are you a robot|access denied|"
                        r"just a moment\.\.\.|enable javascript and cookies", re.I)


# --- HTML --------------------------------------------------------------------

def _job_postings(page: str):
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        stack = [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack.extend(d)
            elif isinstance(d, dict):
                types = d.get("@type")
                if types == "JobPosting" or (isinstance(types, list) and "JobPosting" in types):
                    yield d
                stack.extend(v for k, v in d.items() if k == "@graph")


def _place(posting: dict) -> str:
    out = []
    locs = posting.get("jobLocation") or []
    for loc in locs if isinstance(locs, list) else [locs]:
        addr = (loc or {}).get("address") or {}
        if isinstance(addr, dict):
            out += [addr.get("addressLocality"), addr.get("addressCountry") if isinstance(addr.get("addressCountry"), str)
                    else (addr.get("addressCountry") or {}).get("name")]
    if posting.get("jobLocationType") == "TELECOMMUTE":
        out.append("Remote")
    return ", ".join(dict.fromkeys(p for p in out if p))


def _visible_text(page: str) -> str:
    page = re.sub(r"(?is)<(script|style|noscript|svg|nav|header|footer|form)\b.*?</\1>", " ", page)
    page = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</div>", "\n", page)
    text = htmllib.unescape(re.sub(r"<[^>]+>", " ", page))
    lines = [re.sub(r"[ \t]+", " ", l).strip() for l in text.splitlines()]
    return "\n".join(l for l in lines if l)


def from_html(page: str, url: str = "") -> Job:
    for p in _job_postings(page):
        description = strip_html(p.get("description") or "")
        if len(description.split()) >= 30:
            org = p.get("hiringOrganization") or {}
            return Job(source="manual", title=strip_html(p.get("title") or ""), url=url, location=_place(p),
                       company=org.get("name", "") if isinstance(org, dict) else str(org), description=description)
    title = re.search(r"(?is)<title[^>]*>(.*?)</title>", page)
    return Job(source="manual", title=strip_html(title.group(1)) if title else "", company="", url=url,
               description=_visible_text(page))


# --- links -------------------------------------------------------------------

def _known_board(url: str) -> Optional[Job]:
    """Links to the hiring systems yojobs reads anyway: use their official APIs."""
    from .sources import companies  # lazy: keeps imports light for file/stdin use

    def find(jobs, key):
        return next((j for j in jobs if key in j.url), None)

    m = re.search(r"greenhouse\.io/(?:embed/job_app\?for=)?([\w-]+)/jobs/(\d+)", url) \
        or re.search(r"greenhouse\.io/embed/job_app\?for=([\w-]+)&token=(\d+)", url)
    if m:
        d = get_json(companies.GH_JOB.format(m.group(1), m.group(2)))
        return Job(source="manual", title=d.get("title", ""), company=m.group(1), url=url,
                   location=(d.get("location") or {}).get("name", ""),
                   description=strip_html(strip_html(d.get("content") or "")))
    m = re.search(r"jobs\.lever\.co/([\w.-]+)/([0-9a-f-]{36})", url)
    if m:
        return find(companies._lever(m.group(1)), m.group(2))
    m = re.search(r"jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-f-]{36})", url)
    if m:
        return find(companies._ashby(m.group(1)), m.group(2))
    m = re.search(r"https?://([\w-]+)\.jobs\.personio\.(de|com)/job/(\d+)", url)
    if m:
        board = m.group(1) + ("" if m.group(2) == "de" else ".com")
        return find(companies._personio(board), f"/job/{m.group(3)}")
    m = re.search(r"https?://([\w-]+)\.recruitee\.com/o/([^/?#]+)", url)
    if m:
        return find(companies._recruitee(m.group(1)), f"/o/{m.group(2)}")
    return None


def from_url(url: str) -> Job:
    try:
        job = _known_board(url)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"the hiring system's API answered {exc.code}; is the job still open?")
    if job:
        return job
    try:
        page = get_bytes(url).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 429, 503):
            raise BlockedError(f"the site refused the request (HTTP {exc.code})")
        raise
    except TimeoutError:
        raise BlockedError("the site didn't answer in time (often a sign of bot protection)")
    job = from_html(page, url)
    if len(job.description.split()) < 80 and _CHALLENGE.search(page):
        raise BlockedError("the site showed a bot check instead of the ad")
    return job


# --- files / stdin -----------------------------------------------------------

def from_file(path: Path) -> Job:
    suffix = path.suffix.lower()
    if suffix in (".html", ".htm"):
        return from_html(path.read_text(errors="replace"), str(path))
    if suffix in (".txt", ".md", ""):
        text = path.read_text(errors="replace")
    elif suffix == ".docx":
        text = subprocess.run(["textutil", "-convert", "txt", "-stdout", str(path)],
                              capture_output=True, text=True, check=True).stdout
    elif suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise RuntimeError("reading a PDF needs pypdf: .venv/bin/pip install pypdf")
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    else:
        raise RuntimeError(f"unsupported file type {suffix}: use .txt, .md, .pdf, .docx or .html")
    first = next((l.strip() for l in text.splitlines() if l.strip()), "")
    return Job(source="manual", title=first[:120], company="", url=str(path), description=text.strip())


def load(arg: str) -> Job:
    if arg == "-":
        text = sys.stdin.read()
        first = next((l.strip() for l in text.splitlines() if l.strip()), "")
        return Job(source="manual", title=first[:120], company="", url="(pasted text)", description=text.strip())
    if re.match(r"https?://", arg):
        return from_url(arg)
    path = Path(arg).expanduser()
    if not path.exists():
        raise RuntimeError(f"not a link and no such file: {arg}")
    return from_file(path)
