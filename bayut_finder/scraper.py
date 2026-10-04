"""Paginate a bayut search and return a clean DataFrame."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

from .analytics import normalize
from .config import LISTINGS_PER_PAGE
from .fetcher import BlockedError, Fetcher, make_fetcher
from .parser import parse_search_page
from .urls import SearchParams, build_search_url

ProgressCallback = Callable[[int, int, int], None]   # (page, total_pages, listings_so_far)


def scrape(params: SearchParams, max_pages: int = 5, fetcher: Fetcher | None = None,
           progress: ProgressCallback | None = None, engine: str = "requests",
           delay: tuple[float, float] = (2.0, 4.0)) -> pd.DataFrame:
    """Scrape up to ``max_pages`` result pages for one search.

    Stops early when a page comes back empty or the last page is reached.
    If bayut blocks us midway, whatever was collected so far is returned
    (``df.attrs['error']`` holds the reason).
    """
    own_fetcher = fetcher is None
    fetcher = fetcher or make_fetcher(engine, delay=delay)
    rows: list[dict] = []
    seen: set[str] = set()
    total_count: int | None = None
    total_pages = max_pages
    error: str | None = None
    scraped_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    try:
        page = 1
        while page <= total_pages:
            url = build_search_url(params, page)
            try:
                html = fetcher.get(url)
            except BlockedError as exc:
                error = str(exc)
                break
            listings, count = parse_search_page(html)
            if page == 1 and count is not None:
                total_count = count
                total_pages = min(max_pages, max(1, math.ceil(count / LISTINGS_PER_PAGE)))
            new = 0
            for rec in listings:
                key = rec.get("listing_id") or rec.get("url")
                if key in seen:
                    continue
                seen.add(key)
                rec.update(search_emirate=params.emirate, search_frequency=params.rent_frequency,
                           search_furnishing=params.furnishing, search_page=page,
                           scraped_at=scraped_at)
                rows.append(rec)
                new += 1
            if progress:
                progress(page, total_pages, len(rows))
            if new == 0:
                break
            page += 1
    finally:
        if own_fetcher:
            fetcher.close()

    df = normalize(pd.DataFrame(rows), furnishing=params.furnishing)
    df.attrs.update(total_count=total_count, error=error, params=params.to_dict())
    return df


def scrape_many(searches: Iterable[SearchParams], max_pages: int = 5,
                engine: str = "requests", delay: tuple[float, float] = (2.0, 4.0),
                progress: Callable[[SearchParams, int, int, int], None] | None = None
                ) -> pd.DataFrame:
    """Run several searches with one shared fetcher (e.g. Dubai + Abu Dhabi, monthly + yearly)."""
    fetcher = make_fetcher(engine, delay=delay)
    frames, errors = [], []
    try:
        for params in searches:
            cb = (lambda p, t, n, _s=params: progress(_s, p, t, n)) if progress else None
            df = scrape(params, max_pages=max_pages, fetcher=fetcher, progress=cb)
            if df.attrs.get("error"):
                errors.append(f"{params.label()}: {df.attrs['error']}")
            frames.append(df)
    finally:
        fetcher.close()
    frames = [f for f in frames if not f.empty]
    out = pd.concat(frames, ignore_index=True) if frames else normalize(pd.DataFrame())
    if not out.empty:
        # Same listing can show up in two searches; keep the first.
        out = out.drop_duplicates(subset=["listing_id", "rent_frequency"], keep="first")
    out.attrs["errors"] = errors
    return out


def parse_saved_pages(paths_or_html: Iterable[str | Path | bytes],
                      furnishing: str = "all") -> pd.DataFrame:
    """Build a dataset from HTML pages you saved from your own browser (Ctrl+S)."""
    rows = []
    for item in paths_or_html:
        if isinstance(item, (str, Path)) and Path(item).exists():
            html = Path(item).read_text(encoding="utf-8", errors="ignore")
            source = str(item)
        else:
            html = item.decode("utf-8", "ignore") if isinstance(item, bytes) else str(item)
            source = "upload"
        listings, _ = parse_search_page(html)
        for rec in listings:
            rec["source_file"] = source
        rows.extend(listings)
    df = normalize(pd.DataFrame(rows), furnishing=furnishing)
    if not df.empty:
        df = df.drop_duplicates(subset=["listing_id"], keep="first")
    return df
