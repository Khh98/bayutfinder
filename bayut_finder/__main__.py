"""Command line interface.

Examples
--------
# 1-2 bed apartments in Dubai, paid monthly, up to AED 9,000/month, 5 pages
python -m bayut_finder scrape --emirate dubai --frequency monthly --category apartments \
    --beds 1 2 --price-max 9000 --pages 5

# Dubai + Abu Dhabi, both monthly and yearly listings, into one CSV
python -m bayut_finder scrape --emirate dubai abu-dhabi --frequency monthly yearly --pages 3

# Parse pages you saved from your browser (Ctrl+S) when bayut blocks scripts
python -m bayut_finder parse ~/Downloads/bayut_page*.html
"""

from __future__ import annotations

import argparse
import sys

from .analytics import community_summary, save_dataset
from .config import CATEGORIES, EMIRATES, FURNISHING, RENT_FREQUENCIES, SORT_OPTIONS
from .scraper import parse_saved_pages, scrape_many
from .urls import SearchParams


def _print_summary(df) -> None:
    if df.empty:
        print("No listings.")
        return
    print(f"\n{len(df)} listings")
    print(df.groupby(["emirate", "rent_frequency", "bedrooms_label"])["rent_monthly"]
            .median().rename("median AED / month").to_string())
    top = community_summary(df).head(10)
    if not top.empty:
        print("\nCheapest communities (median AED / month):")
        print(top[["emirate", "community", "listings", "median_monthly", "median_yearly"]]
              .to_string(index=False))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="bayut_finder", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scrape", help="scrape bayut search results")
    s.add_argument("--emirate", nargs="+", default=["dubai"], choices=list(EMIRATES))
    s.add_argument("--frequency", nargs="+", default=["yearly"], choices=list(RENT_FREQUENCIES))
    s.add_argument("--category", default="property", choices=list(CATEGORIES.values()))
    s.add_argument("--location", help="area slug, e.g. dubai-marina or al-reem-island")
    s.add_argument("--furnishing", default="all", choices=FURNISHING)
    s.add_argument("--beds", nargs="*", type=int, default=[], help="0 = studio")
    s.add_argument("--baths", nargs="*", type=int, default=[])
    s.add_argument("--price-min", type=int)
    s.add_argument("--price-max", type=int, help="in the chosen rent period")
    s.add_argument("--area-min", type=int, help="sqft")
    s.add_argument("--area-max", type=int, help="sqft")
    s.add_argument("--sort", choices=[v for v in SORT_OPTIONS.values() if v])
    s.add_argument("--pages", type=int, default=3, help="max pages per search (24 listings/page)")
    s.add_argument("--engine", default="requests", choices=["requests", "browser"])
    s.add_argument("--delay", type=float, nargs=2, default=[2.0, 4.0], metavar=("MIN", "MAX"))
    s.add_argument("--out", help="CSV path (default: data/<timestamp>_<search>.csv)")

    p = sub.add_parser("parse", help="parse saved bayut HTML pages")
    p.add_argument("files", nargs="+")
    p.add_argument("--furnishing", default="all", choices=FURNISHING)
    p.add_argument("--out")

    args = ap.parse_args(argv)

    if args.cmd == "scrape":
        searches = [
            SearchParams(emirate=e, rent_frequency=f, category=args.category,
                         location=args.location, furnishing=args.furnishing, beds=args.beds,
                         baths=args.baths, price_min=args.price_min, price_max=args.price_max,
                         area_min=args.area_min, area_max=args.area_max, sort=args.sort)
            for e in args.emirate for f in args.frequency
        ]

        def progress(params, page, total, n):
            print(f"  {params.label()}: page {page}/{total} - {n} listings", file=sys.stderr)

        df = scrape_many(searches, max_pages=args.pages, engine=args.engine,
                         delay=tuple(args.delay), progress=progress)
        for err in df.attrs.get("errors", []):
            print(f"WARNING: {err}", file=sys.stderr)
        label = "+".join(dict.fromkeys(s.label() for s in searches))[:120]
    else:
        df = parse_saved_pages(args.files, furnishing=args.furnishing)
        label = "saved-pages"

    if df.empty:
        print("No listings collected.", file=sys.stderr)
        return 1
    if args.out:
        df.to_csv(args.out, index=False)
        path = args.out
    else:
        path = save_dataset(df, label)
    _print_summary(df)
    print(f"\nSaved {len(df)} listings -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
