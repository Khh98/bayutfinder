import streamlit as st

from bayut_finder.analytics import add_value_score, save_dataset
from bayut_finder.config import CATEGORIES, EMIRATES, LISTINGS_PER_PAGE, RENT_FREQUENCIES, SORT_OPTIONS
from bayut_finder.scraper import parse_saved_pages, scrape_many
from bayut_finder.ui import aed, download_button, listings_table, page_setup
from bayut_finder.urls import SearchParams, build_search_url

page_setup("Search", "🔎")
st.title("🔎 Search bayut rentals")

live_tab, import_tab = st.tabs(["Live search", "Import saved pages"])

# --------------------------------------------------------------------------- live
with live_tab:
    with st.form("search"):
        c1, c2, c3 = st.columns(3)
        emirates = c1.multiselect("Emirates", list(EMIRATES), default=["dubai", "abu-dhabi"],
                                  format_func=EMIRATES.get)
        freqs = c2.multiselect("Rent paid", ["monthly", "yearly"], default=["monthly", "yearly"],
                               help="Run both to compare monthly listings against yearly contracts.")
        category_label = c3.selectbox("Property type", list(CATEGORIES), index=1)

        c4, c5, c6 = st.columns(3)
        bed_options = {"Studio": 0, **{f"{n} BR": n for n in range(1, 8)}}
        beds = c4.multiselect("Bedrooms", list(bed_options), default=[])
        furnishing = c5.selectbox("Furnishing", ["all", "furnished", "unfurnished"])
        location = c6.text_input(
            "Area (optional)", placeholder="e.g. dubai-marina, jumeirah-village-circle-jvc",
            help="Bayut's area slug as it appears in the URL after the emirate. Only used for the "
                 "first emirate if you picked several; leave empty to search the whole emirate.")

        c7, c8, c9 = st.columns(3)
        budget_min = c7.number_input("Min budget (AED / month)", 0, 500_000, 0, step=500)
        budget_max = c8.number_input("Max budget (AED / month)", 0, 500_000, 0, step=500,
                                     help="0 = no limit. Converted to a yearly price for yearly searches.")
        pages = c9.slider("Pages per search", 1, 50, 5,
                          help=f"{LISTINGS_PER_PAGE} listings per page. Each emirate × rent period "
                               "is its own search.")

        with st.expander("Advanced"):
            a1, a2, a3, a4 = st.columns(4)
            area_min = a1.number_input("Min size (sqft)", 0, 50_000, 0, step=50)
            area_max = a2.number_input("Max size (sqft)", 0, 50_000, 0, step=50)
            sort_label = a3.selectbox("Sort", list(SORT_OPTIONS), index=2)
            engine = a4.radio("Engine", ["requests", "browser"], horizontal=True,
                              help="'browser' uses Playwright/Chromium - slower but gets past "
                                   "bot protection more often.")
            delay = st.slider("Delay between pages (seconds)", 1.0, 15.0, (2.0, 4.0), step=0.5)

        submitted = st.form_submit_button("Search bayut", type="primary", width="stretch")

    if submitted:
        if not emirates or not freqs:
            st.error("Pick at least one emirate and one rent period.")
            st.stop()
        searches = []
        for i, em in enumerate(emirates):
            for fr in freqs:
                per_year = RENT_FREQUENCIES[fr] / 12  # monthly budget -> price in this period
                searches.append(SearchParams(
                    emirate=em, rent_frequency=fr, category=CATEGORIES[category_label],
                    location=location if (location and i == 0) else None,
                    furnishing=furnishing, beds=[bed_options[b] for b in beds],
                    price_min=int(budget_min / per_year) if budget_min else None,
                    price_max=int(budget_max / per_year) if budget_max else None,
                    area_min=area_min or None, area_max=area_max or None,
                    sort=SORT_OPTIONS[sort_label]))

        with st.expander(f"{len(searches)} search URL(s)"):
            for s in searches:
                st.code(build_search_url(s), language=None)

        bar = st.progress(0.0, text="Starting...")
        n_searches = len(searches)
        done = {"i": -1, "label": None}

        def progress(params, page, total, n):
            if params.label() != done["label"]:
                done["i"] += 1
                done["label"] = params.label()
            frac = (done["i"] + page / max(total, 1)) / n_searches
            bar.progress(min(frac, 1.0),
                         text=f"{params.label()} - page {page}/{total} - {n} listings")

        try:
            df = scrape_many(searches, max_pages=pages, engine=engine, delay=tuple(delay),
                             progress=progress)
        except Exception as exc:  # e.g. Playwright not installed, network down
            bar.empty()
            st.error(f"Search failed: {exc}")
            st.stop()
        bar.empty()

        for err in df.attrs.get("errors", []):
            st.warning(err)
        if df.empty:
            st.error("No listings collected. If bayut blocked the request, see the tips on the "
                     "Home page or use **Import saved pages**.")
            st.stop()

        label = "+".join(dict.fromkeys(f"{s.emirate}-{s.rent_frequency}" for s in searches))
        label += f"_{CATEGORIES[category_label]}"
        path = save_dataset(df, label)
        st.session_state["df"] = df
        st.success(f"Collected **{len(df)}** listings → saved to `data/{path.name}`. "
                   "Open **Compare** or **Map** to dig in.")

# --------------------------------------------------------------------------- import
with import_tab:
    st.markdown(
        "Bayut blocking the scraper? Open your search on **bayut.com** in your browser, "
        "save each results page (**Ctrl+S → Webpage, HTML only** is enough) and drop the files "
        "here. Same columns, same analysis.")
    files = st.file_uploader("Saved bayut search pages", type=["html", "htm"],
                             accept_multiple_files=True)
    furn = st.selectbox("These pages were filtered as", ["all", "furnished", "unfurnished"],
                        key="import_furn")
    if files and st.button("Parse pages", type="primary"):
        df = parse_saved_pages([f.getvalue() for f in files], furnishing=furn)
        if df.empty:
            st.error("No listings found in these files - are they bayut search result pages?")
        else:
            path = save_dataset(df, "imported-pages")
            st.session_state["df"] = df
            st.success(f"Parsed **{len(df)}** listings from {len(files)} file(s) → `data/{path.name}`")

# --------------------------------------------------------------------------- results
df = st.session_state.get("df")
if df is not None and not df.empty:
    st.divider()
    st.subheader("Results")
    df = add_value_score(df)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Listings", f"{len(df):,}")
    m2.metric("Median rent / month", aed(df["rent_monthly"].median()))
    m3.metric("Median rent / year", aed(df["rent_yearly"].median()))
    m4.metric("Communities", df["community"].nunique())
    listings_table(df.sort_values("rent_monthly"))
    download_button(df, "bayut_listings.csv")
