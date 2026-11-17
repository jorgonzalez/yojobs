from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from . import __version__

USER_AGENT = f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) yojobs/{__version__} (personal job alert)"
TIMEOUT = 30
RETRIES = 3


def get_bytes(url: str, params: Optional[dict] = None) -> bytes:
    if params:
        url = f"{url}{'&' if '?' in url else '?'}{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 502, 503) or attempt == RETRIES:
                raise
            retry_after = exc.headers.get("Retry-After", "")
            wait = int(retry_after) if retry_after.isdigit() else 5 * 2 ** attempt
            time.sleep(min(wait, 60))
    raise RuntimeError("unreachable")


def get_json(url: str, params: Optional[dict] = None) -> Any:
    return json.loads(get_bytes(url, params))
