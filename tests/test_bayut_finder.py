import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pandas as pd
import pytest

from bayut_finder import (SearchParams, add_value_score, build_search_url, community_summary,
                          monthly_vs_yearly, normalize, parse_saved_pages, parse_search_page,
                          scrape, with_distance)
from bayut_finder.fetcher import BlockedError, ChromeFetcher, make_fetcher
from bayut_finder.parser import looks_blocked

FIXTURE = Path(__file__).parent / "fixtures" / "dubai_rent_page1.html"


@pytest.fixture(scope="module")
def html():
    return FIXTURE.read_text(encoding="utf-8")


# ---------------------------------------------------------------- urls
def test_url_first_page_defaults():
    url = build_search_url(SearchParams())
    assert url == "https://www.bayut.com/to-rent/property/dubai/?rent_frequency=yearly"


def test_url_with_filters_and_page():
    p = SearchParams(emirate="Abu Dhabi", rent_frequency="monthly", category="apartments",
                     location="Al Reem Island", furnishing="furnished", beds=[2, 1],
                     price_max=9000, sort="price_asc")
    url = build_search_url(p, page=3)
    assert url.startswith("https://www.bayut.com/to-rent/apartments/abu-dhabi/al-reem-island/page-3/?")
    assert "rent_frequency=monthly" in url
    assert "furnishing_status=furnished" in url
    assert "beds_in=1,2" in url
    assert "price_max=9000" in url
    assert "sort=price_asc" in url


def test_invalid_emirate():
    with pytest.raises(ValueError):
        SearchParams(emirate="atlantis")


# ---------------------------------------------------------------- parser
def test_parse_saved_page(html):
    listings, total = parse_search_page(html)
    assert total == 118_858
    assert len(listings) == 24
    first = listings[0]
    assert first["listing_id"] == "16646069"
    assert first["url"] == "https://www.bayut.com/property/details-16646069.html"
    assert first["price"] == 42_000
    assert first["rent_frequency"] == "yearly"
    assert first["bedrooms"] == 0  # studio
    assert first["bathrooms"] == 1
    assert first["area_sqft"] == 295
    assert first["property_type"] == "Apartment"
    assert first["community"] == "Meydan"
    assert first["building"] == "Azizi Riviera 16"
    assert first["emirate"] == "Dubai"
    assert first["latitude"] == pytest.approx(25.1725, abs=1e-3)
    assert first["longitude"] == pytest.approx(55.3022, abs=1e-3)
    assert first["verified"] is True
    for rec in listings:
        for key in ("price", "latitude", "longitude", "title", "community", "url"):
            assert rec.get(key) not in (None, ""), (key, rec["listing_id"])


def test_cards_alone_still_parse(html):
    """If bayut drops the JSON-LD block, aria-label cards are enough."""
    no_ld = re.sub(r'<script type="application/ld\+json">.*?</script>', "", html, flags=re.S)
    listings, total = parse_search_page(no_ld)
    assert total == 118_858
    assert len(listings) == 24
    assert listings[0]["price"] == 42_000 and listings[0]["bedrooms"] == 0


def test_jsonld_alone_still_parses(html):
    """If bayut renames the aria-labels, the JSON-LD block is enough."""
    no_cards = html.replace('aria-label="Listing"', 'aria-label="x"')
    listings, _ = parse_search_page(no_cards)
    assert len(listings) == 24
    assert all(r["latitude"] for r in listings)


def test_blocked_detection(html):
    assert not looks_blocked(html)
    assert looks_blocked("<html><body>Please verify you are human (captcha)</body></html>")


# ---------------------------------------------------------------- analytics
def test_normalize_monthly_and_yearly(html):
    listings, _ = parse_search_page(html)
    listings[1] = {**listings[1], "price": 6000, "rent_frequency": "monthly"}
    df = normalize(pd.DataFrame(listings))
    yearly = df.iloc[0]
    assert yearly.rent_yearly == 42_000 and yearly.rent_monthly == 3_500
    monthly = df.iloc[1]
    assert monthly.rent_monthly == 6_000 and monthly.rent_yearly == 72_000
    assert yearly.bedrooms_label == "Studio"
    assert yearly.yearly_per_sqft == round(42_000 / 295, 1)


def test_value_score_and_summaries(html):
    df = normalize(pd.DataFrame(parse_search_page(html)[0]))
    scored = add_value_score(df)
    lagoons_4br = scored[(scored.community == "DAMAC Lagoons") & (scored.bedrooms_label == "4 BR")]
    assert lagoons_4br["vs_area_median"].notna().all()
    assert (lagoons_4br["vs_area_median"] <= 0).any()
    summary = community_summary(df)
    assert "Meydan" in summary["community"].values


def test_monthly_vs_yearly_premium():
    rows = []
    for price in (60_000, 66_000):
        rows.append(dict(listing_id=f"y{price}", price=price, rent_frequency="yearly",
                         bedrooms=1, emirate="Dubai", community="JVC"))
    for price in (6_000, 6_600):
        rows.append(dict(listing_id=f"m{price}", price=price, rent_frequency="monthly",
                         bedrooms=1, emirate="Dubai", community="JVC"))
    out = monthly_vs_yearly(normalize(pd.DataFrame(rows)))
    assert len(out) == 1
    assert out.iloc[0]["premium_pct"] == pytest.approx(20.0)


def test_distance(html):
    df = normalize(pd.DataFrame(parse_search_page(html)[0]))
    near = with_distance(df, 25.1972, 55.2744).sort_values("distance_km")  # Burj Khalifa
    assert near.iloc[0]["community"] == "Downtown Dubai"
    assert near.iloc[0]["distance_km"] < 2


# ---------------------------------------------------------------- scraper
class FakeFetcher:
    """Serves the saved page for page 1..n, then an empty page."""

    def __init__(self, html, pages_with_results=2, block_on=None):
        self.html = html
        self.pages = pages_with_results
        self.block_on = block_on
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        page = int(re.search(r"page-(\d+)", url).group(1)) if "page-" in url else 1
        if self.block_on == page:
            raise BlockedError("blocked")
        if page > self.pages:
            return "<html><body>No results</body></html>"
        # Give each page distinct listing ids so dedupe doesn't stop pagination.
        return re.sub(r"details-(\d+)", lambda m: f"details-{page}{m.group(1)}", self.html)

    def close(self):
        pass


def test_scrape_paginates_and_stops(html):
    fake = FakeFetcher(html, pages_with_results=2)
    df = scrape(SearchParams(rent_frequency="yearly"), max_pages=5, fetcher=fake)
    assert len(df) == 48
    assert len(fake.urls) == 3  # page 3 empty -> stop
    assert "page-2/" in fake.urls[1]
    assert df.attrs["total_count"] == 118_858


def test_scrape_returns_partial_results_when_blocked(html):
    fake = FakeFetcher(html, pages_with_results=5, block_on=2)
    df = scrape(SearchParams(), max_pages=5, fetcher=fake)
    assert len(df) == 24
    assert df.attrs["error"] == "blocked"


def test_parse_saved_pages_from_file():
    df = parse_saved_pages([FIXTURE])
    assert len(df) == 24
    assert {"rent_monthly", "rent_yearly", "latitude"} <= set(df.columns)


# ---------------------------------------------------------------- chrome engine (curl_cffi)
@pytest.fixture()
def fake_bayut(html, monkeypatch):
    """Local server: /ok serves the saved page, /block403-once refuses the first hit,
    /empty serves a page without listings."""
    for var in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    hits = {"block": 0, "agents": []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            hits["agents"].append(self.headers.get("User-Agent", ""))
            if self.path.startswith("/block403-once") and hits["block"] == 0:
                hits["block"] += 1
                code, body = 403, "Forbidden"
            elif self.path.startswith("/empty"):
                code, body = 200, "<html><body><p>nothing here</p></body></html>"
            else:
                code, body = 200, html
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", hits
    server.shutdown()


def test_chrome_engine_is_default():
    pytest.importorskip("curl_cffi")
    fetcher = make_fetcher(delay=(0, 0))
    assert isinstance(fetcher, ChromeFetcher)
    fetcher.close()


def test_chrome_fetcher_parses_page_and_sends_chrome_user_agent(fake_bayut):
    pytest.importorskip("curl_cffi")
    base, hits = fake_bayut
    fetcher = ChromeFetcher(delay=(0, 0))
    listings, total = parse_search_page(fetcher.get(f"{base}/ok"))
    fetcher.close()
    assert len(listings) == 24 and total == 118_858
    assert "Chrome/" in hits["agents"][0]  # UA comes from the impersonation, not from us


def test_chrome_fetcher_rotates_fingerprint_after_403(fake_bayut, monkeypatch):
    pytest.importorskip("curl_cffi")
    monkeypatch.setattr("bayut_finder.fetcher.time.sleep", lambda s: None)
    base, hits = fake_bayut
    fetcher = ChromeFetcher(delay=(0, 0))
    first = fetcher.impersonate
    page = fetcher.get(f"{base}/block403-once")
    assert "RealEstateListing" in page
    assert fetcher.impersonate != first
    fetcher.close()


def test_empty_page_reports_and_saves_debug_html(fake_bayut, tmp_path, monkeypatch):
    pytest.importorskip("curl_cffi")
    monkeypatch.setattr("bayut_finder.scraper.DATA_DIR", tmp_path)
    monkeypatch.setattr("bayut_finder.scraper.build_search_url", lambda p, page: f"{base}/empty")
    base, _ = fake_bayut
    df = scrape(SearchParams(), max_pages=3, fetcher=ChromeFetcher(delay=(0, 0)))
    assert df.empty
    assert "HTTP 200" in df.attrs["error"] and "saved" in df.attrs["error"]
    saved = list((tmp_path / "debug").glob("*.html"))
    assert len(saved) == 1 and "nothing here" in saved[0].read_text()
