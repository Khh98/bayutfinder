"""Build bayut.com rental search URLs from a SearchParams object."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from urllib.parse import urlencode

from .config import BASE_URL, CATEGORIES, EMIRATES, FURNISHING, RENT_FREQUENCIES


def slugify(text: str) -> str:
    """'Dubai Marina' -> 'dubai-marina' (matches bayut's location slugs)."""
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


@dataclass
class SearchParams:
    emirate: str = "dubai"
    rent_frequency: str = "yearly"           # yearly | monthly | weekly | daily
    category: str = "property"               # path segment, see config.CATEGORIES
    location: str | None = None              # e.g. "dubai-marina" or "jumeirah-village-circle-jvc"
    furnishing: str = "all"                  # all | furnished | unfurnished
    beds: list[int] = field(default_factory=list)   # 0 = studio
    baths: list[int] = field(default_factory=list)
    price_min: int | None = None             # in the chosen rent_frequency
    price_max: int | None = None
    area_min: int | None = None              # sqft
    area_max: int | None = None
    sort: str | None = None                  # see config.SORT_OPTIONS

    def __post_init__(self):
        self.emirate = slugify(self.emirate)
        if self.location:
            self.location = "/".join(slugify(p) for p in self.location.split("/") if p.strip())
        if self.emirate not in EMIRATES:
            raise ValueError(f"emirate must be one of {list(EMIRATES)}, got {self.emirate!r}")
        if self.rent_frequency not in RENT_FREQUENCIES:
            raise ValueError(f"rent_frequency must be one of {list(RENT_FREQUENCIES)}")
        if self.furnishing not in FURNISHING:
            raise ValueError(f"furnishing must be one of {FURNISHING}")
        if self.category not in CATEGORIES.values():
            raise ValueError(f"category must be one of {list(CATEGORIES.values())}")

    def to_dict(self) -> dict:
        return asdict(self)

    def label(self) -> str:
        """Short human description, used for file names and captions."""
        parts = [self.emirate]
        if self.location:
            parts.append(self.location.split("/")[-1])
        parts += [self.category, self.rent_frequency]
        if self.furnishing != "all":
            parts.append(self.furnishing)
        if self.beds:
            parts.append("beds-" + "-".join(map(str, sorted(self.beds))))
        return "_".join(parts)


def build_search_url(params: SearchParams, page: int = 1) -> str:
    path = f"/to-rent/{params.category}/{params.emirate}/"
    if params.location:
        path += f"{params.location}/"
    if page > 1:
        path += f"page-{page}/"

    query: dict[str, str | int] = {}
    # Bayut's default rental search is yearly; always be explicit so the
    # results really match what we label them as.
    query["rent_frequency"] = params.rent_frequency
    if params.furnishing != "all":
        query["furnishing_status"] = params.furnishing
    if params.beds:
        query["beds_in"] = ",".join(str(b) for b in sorted(set(params.beds)))
    if params.baths:
        query["baths_in"] = ",".join(str(b) for b in sorted(set(params.baths)))
    for key in ("price_min", "price_max", "area_min", "area_max"):
        value = getattr(params, key)
        if value:
            query[key] = int(value)
    if params.sort:
        query["sort"] = params.sort

    return f"{BASE_URL}{path}?{urlencode(query, safe=',')}"
