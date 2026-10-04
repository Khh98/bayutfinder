"""Parse a bayut.com search results page into listing records.

Two independent sources on the page are combined:

1. The schema.org JSON-LD block (<script type="application/ld+json">). It holds
   clean numbers for every listing: price, rent period, beds, baths, size,
   GPS coordinates, agent and agency. No geocoding needed.
2. The listing cards, located by their ``aria-label`` attributes ("Listing",
   "Price", "Location", ...). These are accessibility labels and stay stable
   across bayut deploys, unlike the hashed CSS class names (``_475e888a`` etc.)
   the old scrapers relied on. The cards add the full location path
   ("Building, Sub-community, Community, Emirate") and the verified date.

Either source alone is enough to produce a record; they are merged on the
listing id when both are present.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from bs4 import BeautifulSoup, Tag

from .config import BASE_URL

_ID_RE = re.compile(r"details-(\d+)\.html")
_NUM_RE = re.compile(r"[\d,]+(?:\.\d+)?")
_SUMMARY_RE = re.compile(r"of\s+([\d,]+)\s+Propert", re.I)


def _to_number(text: Any) -> float | None:
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    match = _NUM_RE.search(str(text))
    if not match:
        return None
    try:
        return float(match.group().replace(",", ""))
    except ValueError:
        return None


def _listing_id(url: str | None) -> str | None:
    if not url:
        return None
    match = _ID_RE.search(url)
    return match.group(1) if match else None


def _abs_url(href: str) -> str:
    return href if href.startswith("http") else BASE_URL + href


def _soup(html: str | bytes) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # lxml missing -> stdlib parser
        return BeautifulSoup(html, "html.parser")


# --------------------------------------------------------------------------- #
# Page level
# --------------------------------------------------------------------------- #
def parse_total_count(soup: BeautifulSoup) -> int | None:
    """Total number of matching properties, e.g. '1 to 24 of 118,858 Properties'."""
    summary = soup.find(attrs={"aria-label": "Summary text"})
    if summary:
        match = _SUMMARY_RE.search(summary.get_text(" ", strip=True))
        if match:
            return int(match.group(1).replace(",", ""))
    for data in _iter_jsonld(soup):
        for node in _walk(data):
            offers = node.get("offers") if isinstance(node, dict) else None
            if isinstance(offers, dict) and "offerCount" in offers:
                return int(offers["offerCount"])
    return None


def looks_blocked(html: str | bytes) -> bool:
    """Heuristic for a bot-challenge / captcha page instead of real results."""
    text = html.decode("utf-8", "ignore") if isinstance(html, bytes) else html
    if 'aria-label="Listing"' in text or "RealEstateListing" in text:
        return False
    markers = ("captcha", "are you a robot", "access denied", "request blocked",
               "humbucker", "verify you are human", "unusual traffic")
    lowered = text.lower()
    return any(m in lowered for m in markers)


# --------------------------------------------------------------------------- #
# JSON-LD
# --------------------------------------------------------------------------- #
def _iter_jsonld(soup: BeautifulSoup) -> Iterable[Any]:
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text()
        if not raw or not raw.strip():
            continue
        try:
            yield json.loads(raw)
        except json.JSONDecodeError:
            continue


def _walk(node: Any) -> Iterable[Any]:
    """Depth-first walk over every dict/list in a JSON document."""
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            yield cur
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)


def _types(node: dict) -> list[str]:
    t = node.get("@type", [])
    return t if isinstance(t, list) else [t]


def parse_jsonld_listings(soup: BeautifulSoup) -> list[dict]:
    records = []
    for data in _iter_jsonld(soup):
        for node in _walk(data):
            if "RealEstateListing" not in _types(node):
                continue
            entity = node.get("mainEntity") or {}
            geo = entity.get("geo") or {}
            address = entity.get("address") or {}
            floor = entity.get("floorSize") or {}
            price = entity.get("priceSpecification") or {}
            agent = entity.get("realEstateAgent") or {}
            agency = agent.get("memberOf") or {}
            url = node.get("url")
            entity_types = [t for t in _types(entity) if t != "RentAction"]
            records.append({
                "listing_id": _listing_id(url),
                "url": url,
                "title": entity.get("description"),
                "property_type": entity.get("accommodationCategory")
                                 or (entity_types[0] if entity_types else None),
                "price": _to_number(price.get("price")),
                "currency": price.get("priceCurrency"),
                "rent_frequency": (price.get("unitText") or "").lower() or None,
                "bedrooms": _to_number(entity.get("numberOfBedrooms")),
                "bathrooms": _to_number(entity.get("numberOfBathroomsTotal")),
                "area_sqft": _area_sqft(floor.get("value"), floor.get("unitText")),
                "latitude": _to_number(geo.get("latitude")),
                "longitude": _to_number(geo.get("longitude")),
                "emirate": address.get("addressRegion"),
                "community": address.get("addressLocality"),
                "agent": agent.get("name"),
                "agent_phone": agent.get("telephone"),
                "agency": agency.get("name"),
                "image": (entity.get("image") or [None])[0]
                         if isinstance(entity.get("image"), list) else entity.get("image"),
            })
    return records


def _area_sqft(value: Any, unit: str | None) -> float | None:
    num = _to_number(value)
    if num is None:
        return None
    unit = (unit or "sqft").lower()
    if unit in ("sqm", "mtk", "m2", "square meter", "square metre"):
        return round(num * 10.7639, 1)
    return num


# --------------------------------------------------------------------------- #
# HTML cards (aria-label based)
# --------------------------------------------------------------------------- #
def _label_text(card: Tag, label: str) -> str | None:
    el = card.find(attrs={"aria-label": label})
    if not el:
        return None
    text = el.get_text(" ", strip=True)
    return text or None


def parse_card(card: Tag) -> dict:
    link = card.find("a", attrs={"aria-label": "Listing link"}) or card.find(
        "a", href=_ID_RE)
    href = link.get("href") if link else None

    beds_text = _label_text(card, "Beds") or _label_text(card, "Studio")
    if beds_text and beds_text.lower().startswith("studio"):
        bedrooms = 0.0
    else:
        bedrooms = _to_number(beds_text)

    location_el = card.find(attrs={"aria-label": "Location"})
    location = location_el.get_text(" ", strip=True) if location_el else None

    verified_el = card.find(attrs={"aria-label": "Property Verified Button"})
    verified_text = verified_el.get_text(" ", strip=True) if verified_el else ""

    area_text = _label_text(card, "Area")
    area = _to_number(area_text)
    if area is not None and area_text and "sqm" in area_text.lower():
        area = round(area * 10.7639, 1)

    title = _label_text(card, "Title") or (link.get("title") if link else None)

    return {
        "listing_id": _listing_id(href),
        "url": _abs_url(href) if href else None,
        "title": title,
        "property_type": _label_text(card, "Type"),
        "price": _to_number(_label_text(card, "Price")),
        "currency": _label_text(card, "Currency"),
        "rent_frequency": (_label_text(card, "Frequency") or "").lower() or None,
        "bedrooms": bedrooms,
        "bathrooms": _to_number(_label_text(card, "Baths")),
        "area_sqft": area,
        "location": location,
        "verified": bool(verified_el),
        "verified_on": re.sub(r"^on\s+", "", verified_text) or None,
        "trubroker": card.find(attrs={"aria-label": "TruBroker"}) is not None,
    }


def parse_card_listings(soup: BeautifulSoup) -> list[dict]:
    cards = soup.find_all(attrs={"aria-label": "Listing"})
    return [rec for rec in (parse_card(c) for c in cards) if rec["listing_id"]]


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def parse_search_page(html: str | bytes) -> tuple[list[dict], int | None]:
    """Return (listings, total_count) for one search results page."""
    soup = _soup(html)
    total = parse_total_count(soup)
    from_json = parse_jsonld_listings(soup)
    from_cards = parse_card_listings(soup)

    merged: dict[str, dict] = {}
    # Cards first (page order), then JSON-LD on top: its numbers are cleaner
    # than scraped text. Empty values never overwrite filled ones.
    for rec in from_cards + from_json:
        key = rec["listing_id"] or rec["url"]
        if not key:
            continue
        target = merged.setdefault(key, {})
        for k, v in rec.items():
            if v is not None and v != "":
                target[k] = v
    listings = list(merged.values())
    for rec in listings:
        _derive_location_parts(rec)
    return listings, total


def _derive_location_parts(rec: dict) -> None:
    """Split 'Building, Sub, Community, Emirate' into named columns."""
    loc = rec.get("location")
    if not loc:
        parts = [p for p in (rec.get("community"), rec.get("emirate")) if p]
        rec["location"] = ", ".join(parts) or None
        return
    parts = [p.strip() for p in loc.split(",") if p.strip()]
    if len(parts) >= 2:
        if not rec.get("emirate"):
            rec["emirate"] = parts[-1]
        rec["community"] = parts[-2]
    if len(parts) >= 3:
        rec["building"] = parts[0]
    if len(parts) >= 4:
        rec["sub_community"] = ", ".join(parts[1:-2])
