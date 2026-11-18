"""Decide from the wording whether a job is really remote.

LinkedIn's public pages don't show the work mode and its remote filter also returns
on-site jobs; Indeed marks "mobiles Arbeiten" jobs as remote. So for those sources
a job only counts as remote with clear wording in its title or description."""
from __future__ import annotations

import re

_REMOTE_TITLE = re.compile(r"\bremote\b", re.I)
_REMOTE_TEXT = re.compile(
    r"\b(fully|full|100\s?%|completely|komplett|vollständig|vollstaendig|permanently)[\s-]*remote\b"
    r"|\bremote[\s-](first|only)\b"
    r"|\bremote\s*\(\s*(germany|deutschland|eu|europe|emea|cet)\b"
    r"|\bremote\s+(in|within|from|across)\s+(germany|deutschland|europe|the\s+eu|eu|emea)\b"
    r"|\b(work|working)\s+from\s+anywhere\b"
    r"|\bremote[\s-]+(position|role|job)\b"
    r"|\b(100\s?%|komplett|vollständig|vollstaendig|ausschließlich|ausschliesslich)\s*(im\s+|aus\s+dem\s+)?home[\s-]?office\b"
    r"|\bortsunabhängig\b|\bortsunabhaengig\b",
    re.I,
)


def remote_evidence(title: str, description: str) -> str:
    """'' if no clear sign of a remote job, else where it was found."""
    if _REMOTE_TITLE.search(title or ""):
        return "title"
    if _REMOTE_TEXT.search(description or ""):
        return "description"
    return ""


# Regions an ad can name for where a remote role may be done from. Returned in the
# words of the remote_regions setting, so the normal region rule can check them.
_REGION_WORDS = {
    "global": r"global(ly)?", "worldwide": r"world[\s-]?wide", "anywhere": r"anywhere",
    "Europe": r"europe|european\s+union", "EU": r"eu", "EMEA": r"emea", "CET": r"cet|cest",
    "Germany": r"germany|deutschland",
}
_REGION_RE = re.compile(r"\b(" + "|".join(f"(?P<{k}>{v})" for k, v in _REGION_WORDS.items()) + r")\b", re.I)
_SENTENCE = re.compile(r"[^.!?\n]*\bremote\b[^.!?\n]*", re.I)


def remote_region(description: str) -> str:
    """Regions named in the same sentence as "remote" ("Fully remote and global",
    "remote within the EU"), e.g. "global" or "Europe, EU"; "" if none.
    "Fully remote role based in Barcelona, Spain" gives "" (no allowed region)."""
    found = []
    for sentence in _SENTENCE.findall(description or ""):
        for m in _REGION_RE.finditer(sentence):
            name = next(k for k, v in m.groupdict().items() if v)
            if name not in found:
                found.append(name)
    return ", ".join(found)
