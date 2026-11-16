"""Hacker News "Ask HN: Who is hiring?" monthly threads, via the HN Search API
(hn.algolia.com, linked from news.ycombinator.com). One request finds the latest
threads by the `whoishiring` account; one request per thread returns every post.

Posts follow a loose convention on their first line:
    Company | Role(s) | Location | REMOTE (EU) | Full-time | salary | link
so we split that line on "|" to get company, the role segment, and where you can
work from. The whole post is the description (for the Kubernetes check).
"""
from __future__ import annotations

import html
import re

from ..http import get_json
from ..models import Job, from_timestamp

SEARCH = "https://hn.algolia.com/api/v1/search_by_date"
ITEM = "https://hn.algolia.com/api/v1/items/{}"

_ROLE_HINT = re.compile(
    r"\b(manager|head|director|lead|vp|engineer|sre|devops|developer|architect|teamleiter|cto)\b", re.I)
_REMOTE = re.compile(r"\b(remote|anywhere|distributed|wfh)\b", re.I)
_EU = re.compile(r"\b(eu|europe|european|emea|cet|cest|germany|deutschland|berlin|worldwide|anywhere|global|"
                 r"any\s+time\s*zone)\b", re.I)
_US_ONLY = re.compile(r"\b(us|usa|u\.s\.|united states|north america|americas|canada|"
                      r"pst|pt|est|et|cst|mst|us\s+time\s*zones?)\b", re.I)
_URL = re.compile(r"https?://\S+")


def _text(fragment: str) -> str:
    fragment = re.sub(r"<p>", "\n", fragment or "")
    return html.unescape(re.sub(r"<[^>]+>", " ", fragment))


def parse_post(first_line: str):
    """-> (company, role segment, location string, remote flag)"""
    line = _URL.sub(" ", first_line)
    parts = [p.strip(" -–—") for p in re.split(r"\s*\|\s*", line) if p.strip(" -–—")]
    if not parts:
        return "", "", "", None
    company = parts[0]
    rest = parts[1:] or [line]
    roles = [p for p in rest if _ROLE_HINT.search(p)]
    role = "; ".join(roles) if roles else rest[0]
    others = " | ".join(p for p in rest if p not in roles)
    remote = bool(_REMOTE.search(others) or _REMOTE.search(role))
    # Where can you work from? Make it something the location rules understand.
    if re.search(r"\bberlin\b", others, re.I):
        location = "Berlin" + (" / Remote" if remote else "")
    elif remote and _EU.search(others):
        location = "Remote, " + ", ".join(dict.fromkeys(m.group(0) for m in _EU.finditer(others)))
    elif remote and _US_ONLY.search(others):
        location = "Remote, US only"
    elif remote:
        location = "Remote"  # no region given
    else:
        location = others[:120]
    return company, role, location, remote


def fetch(cfg, since):
    hits = get_json(SEARCH, {"tags": "story,author_whoishiring", "hitsPerPage": 12})["hits"]
    threads = [h for h in hits if "who is hiring" in (h.get("title") or "").lower()]
    jobs = []
    for thread in threads[: cfg.get("threads", 2)]:  # posts are filtered by date later
        item = get_json(ITEM.format(thread["objectID"]))
        for post in item.get("children") or []:
            if not post.get("text") or post.get("author") in (None, "whoishiring"):
                continue
            body = _text(post["text"]).strip()
            first = body.split("\n", 1)[0]
            company, role, location, remote = parse_post(first)
            if not role:
                continue
            jobs.append(Job(
                source="hackernews",
                title=role,
                company=company,
                url=f"https://news.ycombinator.com/item?id={post['id']}",
                location=location,
                published=from_timestamp(post.get("created_at_i")),
                description=body,
                remote=remote,
            ))
    return jobs
