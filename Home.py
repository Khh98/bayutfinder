"""Bayut Finder - home page.  Run with:  streamlit run Home.py"""

import streamlit as st

from bayut_finder.analytics import list_datasets
from bayut_finder.ui import page_setup

page_setup("Home", "🏠")

st.title("🏠 Bayut Finder")
st.caption("Personal rental search for Dubai & Abu Dhabi - rent per month and per year, side by side.")

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("#### 1 · 🔎 Search")
    st.write("Pick emirates, monthly and/or yearly rent, bedrooms and a monthly budget. "
             "The app pages through bayut.com and saves the results to `data/`.")
    st.page_link("pages/1_Search.py", label="Start a search", icon="🔎")
with col2:
    st.markdown("#### 2 · 📊 Compare")
    st.write("Median rent by bedrooms and community, what paying monthly really costs "
             "versus a yearly contract, and the listings priced below their area median.")
    st.page_link("pages/2_Compare.py", label="Compare areas", icon="📊")
with col3:
    st.markdown("#### 3 · 🗺️ Map")
    st.write("See every listing on a map and find the closest options to your office, "
             "school or any place you type.")
    st.page_link("pages/3_Map.py", label="Open the map", icon="🗺️")

st.divider()

saved = list_datasets()
if saved:
    st.markdown(f"**{len(saved)} saved dataset(s)** in `data/` - newest: `{saved[0].name}`")
else:
    st.info("No saved data yet - run your first search.")

with st.expander("How rent is compared"):
    st.markdown("""
- Bayut listings are priced **per year** (a yearly contract, often paid in 1-4 cheques) or
  **per month** (usually furnished / flexible, sometimes bills included).
- Every listing gets both an **AED / month** and an **AED / year** column
  (`monthly × 12`, `yearly ÷ 12`), so you can compare them on one scale.
- **vs area median** compares a listing to similar ones: same emirate, community, bedrooms and
  rent period. `-15%` means it's 15% cheaper than comparable listings in this dataset.
- Data quality grows with pages scraped: 24 listings per page. For a decent area comparison
  scrape 10+ pages per search, or narrow the search to the communities you care about.
""")

with st.expander("If bayut blocks the scraper"):
    st.markdown("""
1. Increase the delay between pages (Search page → *Advanced*).
2. Switch the engine to **browser** (needs `pip install playwright && playwright install chromium`).
3. Or open the search on bayut.com in your own browser, save each results page with
   **Ctrl+S**, and drop the files into *Search → Import saved pages*. Same columns, same analysis.
""")
