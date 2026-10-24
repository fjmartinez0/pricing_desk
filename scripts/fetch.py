"""Download pages politely: robots.txt first, one identifiable user agent, no retries storms.

Static fetching uses the standard library. Pages that only show prices after
JavaScript runs go through browser_capture.py (Playwright), which is the only
module in the project that needs a third-party library.
"""
from __future__ import annotations

import gzip
import urllib.error
import urllib.request
import urllib.robotparser
from urllib.parse import urlparse

from common import REQUEST_TIMEOUT_SEC, USER_AGENT

_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}


class Blocked(Exception):
    """robots.txt disallows this URL for our user agent."""


class FetchError(Exception):
    pass


def allowed_by_robots(url: str) -> bool:
    parts = urlparse(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            req = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as resp:
                rp.parse(_decode(resp).splitlines())
        except Exception:
            # No readable robots.txt (404, timeout…) means no rules. If the site is
            # down, the page fetch itself fails and is counted as a failed capture.
            rp = None
        _robots_cache[base] = rp
    rp = _robots_cache[base]
    return True if rp is None else rp.can_fetch(USER_AGENT, url)


def _decode(resp) -> str:
    raw = resp.read()
    if resp.headers.get("Content-Encoding", "").lower() == "gzip":
        raw = gzip.decompress(raw)
    charset = resp.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def fetch_html(url: str) -> str:
    """Return the raw HTML of url, or raise Blocked / FetchError."""
    if not allowed_by_robots(url):
        raise Blocked(url)
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.8",
        "Accept-Encoding": "gzip",
    })
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as resp:
            return _decode(resp)
    except urllib.error.HTTPError as e:
        raise FetchError(f"HTTP {e.code}") from e
    except Exception as e:  # DNS, TLS, timeout
        raise FetchError(f"{type(e).__name__}: {e}") from e
