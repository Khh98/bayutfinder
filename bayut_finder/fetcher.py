"""Page fetchers.

Bayut's bot protection looks at the TLS/HTTP2 fingerprint of the client, not
just the headers. Plain ``requests`` has a Python fingerprint and gets refused
no matter which User-Agent it sends. Three engines:

- ``chrome`` (default): ``curl_cffi`` impersonating Chrome's TLS stack. Fast,
  no browser needed, and what actually gets through.
- ``browser``: Playwright/Chromium, a real browser. Slowest; last resort.
- ``requests``: plain requests. Kept for completeness; expect 403s from bayut.
"""

from __future__ import annotations

import random
import time
from typing import Protocol

import requests

from .config import DEFAULT_HEADERS
from .parser import looks_blocked

# Impersonation targets tried in order; on a block we start a fresh session
# with the next one. "chrome" = newest Chrome curl_cffi knows.
IMPERSONATE_TARGETS = ("chrome", "chrome131", "edge101", "safari17_0")

# With impersonation, curl_cffi sets a User-Agent matching the TLS fingerprint.
# Overriding it would create a mismatch bot filters look for, so only send these.
BROWSER_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class BlockedError(RuntimeError):
    """Bayut returned a challenge / rate-limit page instead of results."""


class Fetcher(Protocol):
    last_status: int | None
    last_html: str | None

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


class _HttpFetcher:
    """Retry / block-detection loop shared by the requests and curl_cffi engines."""

    name = "http"

    def __init__(self, delay: tuple[float, float] = (2.0, 4.0), retries: int = 3,
                 timeout: float = 30.0):
        self.retries = retries
        self.timeout = timeout
        self._polite = _Polite(delay)
        self.last_status: int | None = None
        self.last_html: str | None = None
        self.session = self._new_session(0)

    def _new_session(self, attempt: int):  # pragma: no cover - overridden
        raise NotImplementedError

    def _rotate(self, attempt: int) -> bool:
        """Start a fresh session (new cookies / fingerprint). False if nothing to rotate to."""
        return False

    def get(self, url: str) -> str:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            self._polite.wait()
            try:
                resp = self.session.get(url, timeout=self.timeout)
            except Exception as exc:  # network errors from either library
                last_error = exc
                time.sleep(2 ** attempt)
                continue
            self.last_status = resp.status_code
            self.last_html = resp.text
            if resp.status_code in (429, 500, 502, 503, 504):
                last_error = BlockedError(f"HTTP {resp.status_code} for {url}")
                time.sleep(5 * (attempt + 1))
                continue
            if resp.status_code == 403 or looks_blocked(resp.text):
                last_error = BlockedError(
                    f"Bayut refused the '{self.name}' engine (HTTP {resp.status_code}, bot "
                    "protection). Use the default 'chrome' engine (pip install curl_cffi), "
                    "slow down, or import pages saved from your browser.")
                if self._rotate(attempt + 1):
                    time.sleep(3 + 2 * attempt)
                    continue
                raise last_error
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code} for {url}")
            return resp.text
        raise last_error or RuntimeError(f"Failed to fetch {url}")

    def close(self) -> None:
        try:
            self.session.close()
        except Exception:
            pass


class ChromeFetcher(_HttpFetcher):
    """curl_cffi session that presents a real Chrome TLS fingerprint."""

    name = "chrome"

    def _new_session(self, attempt: int):
        try:
            from curl_cffi import requests as cf_requests
        except ImportError as exc:
            raise RuntimeError("The 'chrome' engine needs curl_cffi: pip install curl_cffi") from exc
        target = IMPERSONATE_TARGETS[attempt % len(IMPERSONATE_TARGETS)]
        session = cf_requests.Session(impersonate=target)
        session.headers.update(BROWSER_HEADERS)
        self.impersonate = target
        return session

    def _rotate(self, attempt: int) -> bool:
        self.close()
        self.session = self._new_session(attempt)
        return True


class RequestsFetcher(_HttpFetcher):
    name = "requests"

    def _new_session(self, attempt: int):
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)
        return session


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
        self.last_status: int | None = None
        self.last_html: str | None = None

    def get(self, url: str) -> str:
        self._polite.wait()
        resp = self._page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        self.last_status = resp.status if resp else None
        try:
            self._page.wait_for_selector('[aria-label="Listing"], [aria-label="Summary text"]',
                                         timeout=self.timeout_ms)
        except Exception:
            pass  # zero-result pages have no listing cards; let the parser decide
        html = self._page.content()
        self.last_html = html
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


ENGINES = ("chrome", "browser", "requests")


def make_fetcher(engine: str = "chrome", **kwargs) -> Fetcher:
    if engine == "chrome":
        return ChromeFetcher(**kwargs)
    if engine == "requests":
        return RequestsFetcher(**kwargs)
    if engine in ("browser", "playwright"):
        return PlaywrightFetcher(**kwargs)
    raise ValueError(f"Unknown engine {engine!r}; use one of {ENGINES}")
