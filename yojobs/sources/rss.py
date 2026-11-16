"""Tiny RSS 2.0 helper shared by RSS-based sources."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Dict, Iterator, Optional

from ..http import get_bytes
from ..models import to_utc


def parse_rfc822(value: Optional[str]):
    if not value:
        return None
    try:
        return to_utc(parsedate_to_datetime(value))
    except (TypeError, ValueError):
        return None


def items(url: str) -> Iterator[Dict[str, str]]:
    """Yield each <item> as a dict of child-tag -> text (namespaces stripped)."""
    root = ET.fromstring(get_bytes(url))
    for item in root.iter("item"):
        d: Dict[str, str] = {}
        for child in item:
            tag = child.tag.split("}")[-1]
            d.setdefault(tag, (child.text or "").strip())
        yield d
