"""Page fetchers: plain HTTP (requests) or a real headless browser (Playwright).

Bayut sits behind bot protection. A polite ``requests`` session with browser
headers usually works for a handful of pages; if you start getting 403/429 or
challenge pages, switch to ``PlaywrightFetcher`` (``pip install playwright``),
which renders the page in Chromium like a normal visitor.
"""

from __future__ import annotations

import random
import time
from typing import Protocol

import requests

from .config import DEFAULT_HEADERS
from .parser import looks_blocked


class BlockedError(RuntimeError):
    """Bayut returned a challenge / rate-limit page instead of results."""


class Fetcher(Protocol):
    def get(self, url: str) -> str: ...
    def close(self) -> None: ...


class _Polite:
    """Random delay between requests so we never hammer the site."""

    def __init__(self, delay: tuple[float, float]):
        self.delay = delay
        self._last = 0.0

    def wait(self) -> None:
        lo, hi = self.delay
        target = self._last + random.uniform(lo, hi)
        now = time.monotonic()
        if self._last and now < target:
            time.sleep(target - now)
        self._last = time.monotonic()


class RequestsFetcher:
    def __init__(self, delay: tuple[float, float] = (2.0, 4.0), retries: int = 3,
                 timeout: float = 30.0, headers: dict | None = None):
        self.session = requests.Session()
        self.session.headers.update(headers or DEFAULT_HEADERS)
        self.retries = retries
        self.timeout = timeout
        self._polite = _Polite(delay)

    def get(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            self._polite.wait()
            try:
                resp = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(2 ** attempt)
                continue
            if resp.status_code in (429, 500, 502, 503, 504):
                last_error = BlockedError(f"HTTP {resp.status_code} for {url}")
                time.sleep(5 * (attempt + 1))
                continue
            if resp.status_code == 403:
                raise BlockedError(
                    "Bayut answered 403 Forbidden (bot protection). Try the "
                    "'browser' engine (Playwright), a longer delay, or import "
                    "pages you saved from your browser.")
            resp.raise_for_status()
            if looks_blocked(resp.text):
                raise BlockedError(
                    "Got a challenge page instead of listings. Use the 'browser' "
                    "engine (Playwright) or import saved HTML pages.")
            return resp.text
        raise last_error or RuntimeError(f"Failed to fetch {url}")

    def close(self) -> None:
        self.session.close()


class PlaywrightFetcher:
    """Headless Chromium. Install with: pip install playwright && playwright install chromium"""

    def __init__(self, delay: tuple[float, float] = (2.0, 4.0), headless: bool = True,
                 timeout_ms: int = 45_000):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright && "
                "playwright install chromium") from exc
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=headless)
        self._context = self._browser.new_context(
            user_agent=DEFAULT_HEADERS["User-Agent"], locale="en-US",
            viewport={"width": 1366, "height": 900})
        self._page = self._context.new_page()
        self.timeout_ms = timeout_ms
        self._polite = _Polite(delay)

    def get(self, url: str) -> str:
        self._polite.wait()
        self._page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        try:
            self._page.wait_for_selector('[aria-label="Listing"], [aria-label="Summary text"]',
                                         timeout=self.timeout_ms)
        except Exception:
            pass  # zero-result pages have no listing cards; let the parser decide
        html = self._page.content()
        if looks_blocked(html):
            raise BlockedError("Bayut showed a challenge page in the browser too. "
                               "Run with headless=False and solve it once, or slow down.")
        return html

    def close(self) -> None:
        for closer in (self._context.close, self._browser.close, self._pw.stop):
            try:
                closer()
            except Exception:
                pass


def make_fetcher(engine: str = "requests", **kwargs) -> Fetcher:
    if engine == "requests":
        return RequestsFetcher(**kwargs)
    if engine in ("browser", "playwright"):
        return PlaywrightFetcher(**kwargs)
    raise ValueError(f"Unknown engine {engine!r}; use 'requests' or 'browser'")
