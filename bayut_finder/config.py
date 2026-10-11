"""Static search vocabulary for bayut.com rental searches."""

BASE_URL = "https://www.bayut.com"

# URL slug -> display name. Dubai and Abu Dhabi are the focus, the rest work too.
EMIRATES = {
    "dubai": "Dubai",
    "abu-dhabi": "Abu Dhabi",
    "al-ain": "Al Ain",
    "sharjah": "Sharjah",
    "ajman": "Ajman",
    "ras-al-khaimah": "Ras Al Khaimah",
    "umm-al-quwain": "Umm Al Quwain",
    "fujairah": "Fujairah",
}

# Display name -> URL path segment used by /to-rent/<category>/<emirate>/
CATEGORIES = {
    "Any residential": "property",
    "Apartment": "apartments",
    "Villa": "villas",
    "Townhouse": "townhouses",
    "Penthouse": "penthouse",
    "Hotel apartment": "hotel-apartments",
    "Villa compound": "villa-compound",
}

# How bayut labels the rent period; also the multiplier to turn one period into a year.
RENT_FREQUENCIES = {
    "yearly": 1,
    "monthly": 12,
    "weekly": 52,
    "daily": 365,
}

FURNISHING = ("all", "furnished", "unfurnished")

SORT_OPTIONS = {
    "Popular": None,
    "Newest": "date_desc",
    "Lowest price": "price_asc",
    "Highest price": "price_desc",
    "Verified first": "verified_score",
}

LISTINGS_PER_PAGE = 24

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}
