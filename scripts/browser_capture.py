"""Render JavaScript-heavy pricing pages with Playwright (Chromium).

This is the only module that needs a third-party library. If Playwright is
missing or broken, capture.py keeps working for every static page and reports
the browser pages as failed captures.
"""
from __future__ import annotations

import os
import signal
import subprocess
import threading

from common import BROWSER_PAGE_LIMIT_SEC, USER_AGENT, log
from fetch import Blocked, FetchError, allowed_by_robots


def _browser_pids() -> list[int]:
    """Chromium processes started by this Python process (through the Playwright driver)."""
    out = subprocess.run(["ps", "-ax", "-o", "pid=,ppid=,comm="], capture_output=True, text=True).stdout
    kids: dict[int, list[tuple[int, str]]] = {}
    for line in out.splitlines():
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit():
            kids.setdefault(int(parts[1]), []).append((int(parts[0]), parts[2]))
    found, todo = [], [os.getpid()]
    while todo:
        for pid, comm in kids.get(todo.pop(), []):
            todo.append(pid)
            if "chrom" in comm.lower() or "headless" in comm.lower():
                found.append(pid)
    return found


class _Guard:
    """Kill the browser if one page takes longer than BROWSER_PAGE_LIMIT_SEC in all (D57).

    Playwright limits loading a page, but not reading it: a page whose script never yields blocks
    page.content() forever (19 Nov: one company froze the run for 3.5 days). Killing Chromium makes the
    blocked call fail at once; the session starts a new browser for the next company."""

    def __init__(self, url: str, limit: float):
        self.url, self.fired = url, False
        self._timer = threading.Timer(limit, self._fire)
        self._timer.daemon = True

    def _fire(self) -> None:
        self.fired = True
        for pid in _browser_pids():
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    def __enter__(self):
        self._timer.start()
        return self

    def __exit__(self, *exc):
        self._timer.cancel()
        return False


class BrowserSession:
    """One Chromium for the whole run; open lazily, close at the end."""

    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._context = None

    def _start(self) -> None:
        if self._pw is None:
            from playwright.sync_api import sync_playwright  # imported here so static runs never need it
            self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._context = self._browser.new_context(user_agent=USER_AGENT, locale="en-US")

    def _stuck(self, guard: _Guard) -> FetchError:
        """After the guard killed Chromium: forget it (the next page starts a new one) and explain."""
        self._browser = self._context = None
        log(f"  browser: {guard.url} still not read after {BROWSER_PAGE_LIMIT_SEC} s; browser killed and restarted")
        return FetchError(f"browser: page stuck for {BROWSER_PAGE_LIMIT_SEC} s (script never yields); skipped")

    def fetch_html(self, url: str, timeout_ms: int = 45_000) -> str:
        if not allowed_by_robots(url):
            raise Blocked(url)
        with _Guard(url, BROWSER_PAGE_LIMIT_SEC) as guard:
            try:
                if self._context is None:
                    self._start()
                page = self._context.new_page()
                try:
                    try:
                        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                    except Exception as e:
                        # Some sites never go quiet (analytics, chat widgets, live updates). If the document
                        # itself loaded, use what is on screen; capture.py still checks that it shows prices.
                        if "Timeout" not in type(e).__name__:
                            raise
                        page.wait_for_load_state("domcontentloaded", timeout=15_000)
                        page.wait_for_timeout(5000)
                        return page.content()
                    page.wait_for_timeout(1500)  # late price widgets
                    return page.content()
                finally:
                    if not guard.fired:
                        page.close()
            except Blocked:
                raise
            except Exception as e:
                if guard.fired:
                    raise self._stuck(guard) from e
                raise FetchError(f"browser: {type(e).__name__}: {e}") from e

    def collect_links(self, url: str, href_pattern: str, button_text: str = "load more", max_clicks: int = 40,
                      known: set[str] | None = None, timeout_ms: int = 45_000) -> tuple[list[str], int]:
        """Open url, click the "Load more" button until it disappears, and return (links, clicks).

        Links are absolute hrefs matching href_pattern (a regex), in page order. Stops early when a click
        brings no link that isn't in `known` (everything older was read on an earlier run).
        """
        import re
        if not allowed_by_robots(url):
            raise Blocked(url)
        rx = re.compile(href_pattern)
        known = known or set()
        guard = _Guard(url, BROWSER_PAGE_LIMIT_SEC * 4)    # up to 40 "Load more" clicks
        guard.__enter__()
        try:
            if self._context is None:
                self._start()
            page = self._context.new_page()
            try:
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)

                def links() -> list[str]:
                    hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
                    out, seen = [], set()
                    for h in hrefs:
                        h = h.split("#")[0].split("?")[0].rstrip("/")
                        if rx.search(h) and h not in seen:
                            seen.add(h)
                            out.append(h)
                    return out

                found, clicks = links(), 0
                button = page.get_by_role("button", name=re.compile(button_text, re.I))
                while clicks < max_clicks and button.count() and button.first.is_visible():
                    before = set(found)
                    button.first.click()
                    clicks += 1
                    try:
                        page.wait_for_load_state("networkidle", timeout=15_000)
                    except Exception:
                        pass
                    page.wait_for_timeout(800)
                    found = links()
                    fresh = set(found) - before
                    if not fresh or not (fresh - known):
                        break
                return found, clicks
            finally:
                if not guard.fired:
                    page.close()
        except Blocked:
            raise
        except Exception as e:
            if guard.fired:
                raise self._stuck(guard) from e
            raise FetchError(f"browser: {type(e).__name__}: {e}") from e
        finally:
            guard.__exit__()

    def close(self) -> None:
        for thing in (self._context, self._browser):
            try:
                if thing:
                    thing.close()
            except Exception:
                pass
        if self._pw:
            self._pw.stop()
