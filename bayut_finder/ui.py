"""Streamlit helpers shared by the app pages."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from .analytics import add_value_score, list_datasets, load_datasets

# Categorical slots (validated palette): identity colours follow the emirate,
# never its rank, so a filter never repaints the survivors.
EMIRATE_COLORS = {"Dubai": "#2a78d6", "Abu Dhabi": "#eb6834", "Al Ain": "#1baf7a"}
OTHER_COLOR = "#8a8984"
# One-hue sequential ramp (light -> dark blue) for rent magnitude on the map.
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
# Diverging blue <-> red with neutral grey midpoint: below / above area median.
DIVERGING = [[0.0, "#256abf"], [0.5, "#d9d8d4"], [1.0, "#c83a3a"]]

BEDROOM_ORDER = ["Studio", "1 BR", "2 BR", "3 BR", "4 BR", "5 BR", "6 BR", "7+ BR", "Unknown"]


def color_map(values) -> dict:
    return {v: EMIRATE_COLORS.get(v, OTHER_COLOR) for v in values}


def aed(x) -> str:
    return "–" if pd.isna(x) else f"AED {x:,.0f}"


def page_setup(title: str, icon: str = "🏙️") -> None:
    st.set_page_config(page_title=f"{title} · Bayut Finder", page_icon=icon, layout="wide")


def current_data() -> pd.DataFrame:
    """Dataset picker in the sidebar: the latest scrape or any saved CSVs."""
    saved = list_datasets()
    session_df = st.session_state.get("df")
    with st.sidebar:
        st.subheader("Data")
        options = []
        if session_df is not None and not session_df.empty:
            options.append("Latest search (this session)")
        options += [p.name for p in saved]
        if not options:
            st.info("No data yet. Run a search on the **Search** page first.")
            return pd.DataFrame()
        default = options[:1]
        picked = st.multiselect("Datasets", options, default=default,
                                help="Pick several to combine, e.g. a monthly and a yearly scrape.")
    frames = []
    if "Latest search (this session)" in picked:
        frames.append(session_df)
    paths = [p for p in saved if p.name in picked]
    if paths:
        frames.append(load_datasets(paths))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=["listing_id", "rent_frequency"], keep="first")
    return add_value_score(df)


def filters(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """One row of filters above the charts. Budget is always per month."""
    if df.empty:
        return df
    emirates = sorted(df["emirate"].dropna().unique())
    freqs = sorted(df["rent_frequency"].dropna().unique())
    beds = [b for b in BEDROOM_ORDER if b in set(df["bedrooms_label"])]
    types = sorted(df["property_type"].dropna().unique())

    # Pills for the small option sets: every choice stays readable (no truncated chips).
    # Nothing selected = no filter on that dimension.
    c1, c2, c3 = st.columns([1.3, 1, 2.7])
    sel_em = c1.pills("Emirate", emirates, selection_mode="multi", default=emirates,
                      key=f"{key}_em") or emirates
    sel_fr = c2.pills("Rent paid", freqs, selection_mode="multi", default=freqs, key=f"{key}_fr",
                      format_func=str.capitalize,
                      help="How the landlord lists the rent: per month or per year contract.") or freqs
    sel_bd = c3.pills("Bedrooms", beds, selection_mode="multi", default=beds,
                      key=f"{key}_bd") or beds

    c4, c5, c6 = st.columns([1.6, 2.2, 2.2])
    sel_ty = c4.multiselect("Type (empty = all)", types, key=f"{key}_ty") or types
    lo, hi = int(df["rent_monthly"].min()), int(df["rent_monthly"].max())
    if lo == hi:
        hi = lo + 1
    budget = c5.slider("Budget (AED / month equivalent)", lo, hi, (lo, hi), step=250,
                       key=f"{key}_budget")
    communities = sorted(df["community"].dropna().unique())
    sel_cm = c6.multiselect("Communities (empty = all)", communities, key=f"{key}_cm")

    c7, c8, _ = st.columns([1, 1.2, 3.8])
    verified_only = c7.toggle("Verified only", key=f"{key}_ver")
    has_area = df["area_sqft"].dropna()
    min_sqft = c8.number_input("Min size (sqft)", 0, int(has_area.max()) if len(has_area) else 10000,
                               0, step=50, key=f"{key}_sqft")

    mask = (df["emirate"].isin(sel_em) & df["rent_frequency"].isin(sel_fr)
            & df["bedrooms_label"].isin(sel_bd) & df["property_type"].isin(sel_ty)
            & df["rent_monthly"].between(*budget))
    if sel_cm:
        mask &= df["community"].isin(sel_cm)
    if verified_only:
        mask &= df["verified"].astype(str).str.lower().eq("true")
    if min_sqft:
        mask &= df["area_sqft"].fillna(0) >= min_sqft
    return df[mask]


LISTING_COLUMNS = {
    "url": st.column_config.LinkColumn("Open", display_text="bayut ↗", width="small"),
    "title": st.column_config.TextColumn("Title", width="large"),
    "rent_monthly": st.column_config.NumberColumn("AED / month", format="%d"),
    "rent_yearly": st.column_config.NumberColumn("AED / year", format="%d"),
    "rent_frequency": st.column_config.TextColumn("Listed"),
    "bedrooms_label": st.column_config.TextColumn("Beds"),
    "bathrooms": st.column_config.NumberColumn("Baths", format="%d"),
    "area_sqft": st.column_config.NumberColumn("Sqft", format="%d"),
    "yearly_per_sqft": st.column_config.NumberColumn("AED/sqft/yr", format="%.0f"),
    "vs_area_median": st.column_config.NumberColumn(
        "vs area median", format="%+.0f%%",
        help="Negative = cheaper than comparable listings (same community, beds, rent period)."),
    "distance_km": st.column_config.NumberColumn("km away", format="%.1f"),
}


def listings_table(df: pd.DataFrame, extra: list[str] | None = None, height: int = 420) -> None:
    cols = ["url", "title", "rent_monthly", "rent_yearly", "rent_frequency", "bedrooms_label",
            "bathrooms", "area_sqft", "yearly_per_sqft", "vs_area_median", "property_type",
            "community", "building", "emirate", "agency"]
    cols = (extra or []) + [c for c in cols if c in df.columns and c not in (extra or [])]
    st.dataframe(df[cols], column_config=LISTING_COLUMNS, hide_index=True,
                 width="stretch", height=height)


def download_button(df: pd.DataFrame, name: str) -> None:
    st.download_button("⬇️ Download CSV", df.to_csv(index=False).encode(), file_name=name,
                       mime="text/csv")


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent
