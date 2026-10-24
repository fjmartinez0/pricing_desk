"""Render JavaScript-heavy pricing pages with Playwright (Chromium).

This is the only module that needs a third-party library. If Playwright is
missing or broken, capture.py keeps working for every static page and reports
the browser pages as failed captures.
"""
from __future__ import annotations

from common import USER_AGENT
from fetch import Blocked, FetchError, allowed_by_robots


class BrowserSession:
    """One Chromium for the whole run; open lazily, close at the end."""

    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._context = None

    def _start(self) -> None:
        from playwright.sync_api import sync_playwright  # imported here so static runs never need it
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch()
        self._context = self._browser.new_context(user_agent=USER_AGENT, locale="en-US")

    def fetch_html(self, url: str, timeout_ms: int = 45_000) -> str:
        if not allowed_by_robots(url):
            raise Blocked(url)
        try:
            if self._context is None:
                self._start()
            page = self._context.new_page()
            try:
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                page.wait_for_timeout(1500)  # late price widgets
                return page.content()
            finally:
                page.close()
        except Blocked:
            raise
        except Exception as e:
            raise FetchError(f"browser: {type(e).__name__}: {e}") from e

    def close(self) -> None:
        for thing in (self._context, self._browser):
            try:
                if thing:
                    thing.close()
            except Exception:
                pass
        if self._pw:
            self._pw.stop()
