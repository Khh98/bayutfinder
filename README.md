# Bayut Finder

Personal rental finder for **Dubai and Abu Dhabi**. It scrapes bayut.com rental listings and
shows every price as both **AED / month** and **AED / year**, so monthly listings and yearly
contracts can be compared on one scale before you decide where to rent.

- **Search**: emirates, monthly and/or yearly rent, property type, bedrooms, furnishing,
  area, size and a *monthly* budget (converted automatically for yearly searches).
- **Compare**: median rent by bedrooms and community, price spread, cheapest communities
  (per month or per sqft), the real cost of paying monthly vs a yearly contract, and a
  shortlist of listings priced below comparable ones nearby.
- **Map**: every listing on an OpenStreetMap map; find the closest options to a landmark
  or any place you type (OpenStreetMap geocoding, no API key).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run Home.py
```

Optional browser engine (use it if bayut starts returning 403 / challenge pages):

```bash
pip install playwright && playwright install chromium
```

## Command line

```bash
# 1-2 bed apartments in Dubai listed per month, up to AED 9,000/month, 5 pages
python -m bayut_finder scrape --emirate dubai --frequency monthly --category apartments \
    --beds 1 2 --price-max 9000 --pages 5

# Dubai + Abu Dhabi, monthly and yearly listings, one CSV
python -m bayut_finder scrape --emirate dubai abu-dhabi --frequency monthly yearly --pages 3

# Parse search pages you saved from your browser (Ctrl+S)
python -m bayut_finder parse ~/Downloads/bayut*.html
```

Results are saved to `data/<timestamp>_<search>.csv` (git-ignored) and show up in the app's
sidebar dataset picker. You can combine several datasets, for example a monthly scrape
and a yearly scrape.

## How it works

`bayut_finder/parser.py` reads two independent sources from each results page:

1. **The schema.org JSON-LD block.** Bayut embeds structured data for every listing on the
   page: price, rent period, beds, baths, size, **GPS coordinates**, agent and agency. That
   gives us coordinates without any geocoding.
2. **The listing cards, located by `aria-label`** (`Listing`, `Price`, `Frequency`, `Beds`,
   `Location`, ...). Accessibility labels stay stable across bayut deploys. The hashed CSS
   class names the old notebooks used (`_475e888a`, `dc381b54`, ...) change regularly,
   which is why the old scrapers kept breaking.

Either source alone is enough, and the tests check that. Records are merged on the listing
id.

| Module | Purpose |
|---|---|
| `urls.py` | `SearchParams` → bayut search URL (`/to-rent/<type>/<emirate>/<area>/page-N/?rent_frequency=...`) |
| `fetcher.py` | polite `requests` session (random delay, retries, block detection) or Playwright |
| `scraper.py` | pagination, de-duplication, partial results when blocked, saved-page import |
| `analytics.py` | monthly ↔ yearly normalisation, value score, community summary, monthly premium, distances |
| `ui.py` | shared Streamlit filters, tables, colours |

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests run offline against a saved bayut results page (`tests/fixtures/`).

## Notes

- 24 listings per page. For meaningful community medians, scrape 10+ pages per search
  or narrow the search to the areas you care about.
- Bayut's query-parameter names (`beds_in`, `price_max`, `furnishing_status`, `sort`...)
  are not documented. Each search's URLs are shown in the app, so you can open one in your
  browser and check the filters were applied.
- If bayut changes its markup, save a fresh results page into `tests/fixtures/` and run
  `pytest` to see what broke.
- `ppties_dubai.csv` / `ppties_furnished_per_month.csv` are datasets from the 2023 version
  of the app, kept for reference.
