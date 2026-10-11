"""Cleaning, rent normalisation (monthly <-> yearly), comparisons and storage."""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .config import RENT_FREQUENCIES

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

COLUMNS = [
    "listing_id", "title", "property_type", "bedrooms", "bedrooms_label", "bathrooms",
    "area_sqft", "price", "rent_frequency", "rent_monthly", "rent_yearly",
    "yearly_per_sqft", "emirate", "community", "sub_community", "building", "location",
    "furnishing", "latitude", "longitude", "verified", "verified_on", "trubroker",
    "agent", "agent_phone", "agency", "url", "image",
]


def bedrooms_label(n) -> str:
    if n is None or (isinstance(n, float) and math.isnan(n)):
        return "Unknown"
    n = int(n)
    if n == 0:
        return "Studio"
    return f"{n} BR" if n < 7 else "7+ BR"


def normalize(df: pd.DataFrame, furnishing: str = "all") -> pd.DataFrame:
    """Typed columns + rent expressed both per month and per year."""
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    df = df.copy()
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    for col in ("price", "bedrooms", "bathrooms", "area_sqft", "latitude", "longitude"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    freq = df["rent_frequency"]
    if "search_frequency" in df.columns:
        freq = freq.fillna(df["search_frequency"])
    freq = freq.astype(str).str.lower()
    df["rent_frequency"] = freq.where(freq.isin(list(RENT_FREQUENCIES)), "yearly")
    multiplier = df["rent_frequency"].map(RENT_FREQUENCIES).astype(float)
    df["rent_yearly"] = (df["price"] * multiplier).round(0)
    df["rent_monthly"] = (df["rent_yearly"] / 12).round(0)
    df["yearly_per_sqft"] = (df["rent_yearly"] / df["area_sqft"].where(df["area_sqft"] > 0)).round(1)

    df["bedrooms_label"] = df["bedrooms"].map(bedrooms_label)
    if df["furnishing"].isna().all():
        df["furnishing"] = {"furnished": "Furnished", "unfurnished": "Unfurnished"}.get(
            furnishing, "Any")
    if "search_emirate" in df.columns:
        df["emirate"] = df["emirate"].fillna(
            df["search_emirate"].str.replace("-", " ").str.title())
    df["listing_id"] = df["listing_id"].astype(str)
    df = df[df["price"].notna() & (df["price"] > 0)]

    extra = [c for c in df.columns if c not in COLUMNS]
    return df[COLUMNS + extra].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Decision helpers
# --------------------------------------------------------------------------- #
def add_value_score(df: pd.DataFrame, by: tuple[str, ...] = ("emirate", "community",
                                                             "bedrooms_label", "rent_frequency"),
                    min_group: int = 3) -> pd.DataFrame:
    """``vs_area_median``: % above (+) / below (-) the median rent of comparable
    listings (same emirate, community, bedrooms and rent period). Negative = cheaper
    than similar places nearby. Groups smaller than ``min_group`` get NaN."""
    df = df.copy()
    if df.empty:
        df["area_median_monthly"] = np.nan
        df["vs_area_median"] = np.nan
        return df
    keys = [k for k in by if k in df.columns]
    grp = df.groupby(keys, dropna=False)["rent_monthly"]
    median = grp.transform("median")
    size = grp.transform("size")
    df["area_median_monthly"] = median.where(size >= min_group)
    df["vs_area_median"] = ((df["rent_monthly"] / df["area_median_monthly"] - 1) * 100).round(1)
    return df


def community_summary(df: pd.DataFrame, min_listings: int = 3) -> pd.DataFrame:
    """Median monthly/yearly rent per community, for ranking where to live."""
    if df.empty:
        return pd.DataFrame()
    out = (df.groupby(["emirate", "community"], dropna=True)
             .agg(listings=("listing_id", "count"),
                  median_monthly=("rent_monthly", "median"),
                  median_yearly=("rent_yearly", "median"),
                  min_monthly=("rent_monthly", "min"),
                  median_sqft=("area_sqft", "median"),
                  median_yearly_per_sqft=("yearly_per_sqft", "median"))
             .reset_index())
    out = out[out["listings"] >= min_listings]
    return out.sort_values("median_monthly").reset_index(drop=True)


def monthly_vs_yearly(df: pd.DataFrame, min_each: int = 2) -> pd.DataFrame:
    """How much more a monthly-paid listing costs than a yearly contract, for the
    same community and bedroom count. ``premium_pct`` > 0 means paying monthly is
    more expensive over a full year."""
    if df.empty or df["rent_frequency"].nunique() < 2:
        return pd.DataFrame()
    piv = (df[df["rent_frequency"].isin(["monthly", "yearly"])]
           .groupby(["emirate", "community", "bedrooms_label", "rent_frequency"])
           ["rent_yearly"].agg(["median", "count"]).unstack("rent_frequency"))
    piv.columns = [f"{a}_{b}" for a, b in piv.columns]
    needed = {"median_monthly", "median_yearly", "count_monthly", "count_yearly"}
    if not needed.issubset(piv.columns):
        return pd.DataFrame()
    piv = piv[(piv["count_monthly"] >= min_each) & (piv["count_yearly"] >= min_each)]
    piv = piv.rename(columns={"median_monthly": "monthly_listings_per_year",
                              "median_yearly": "yearly_contract"})
    piv["premium_pct"] = ((piv["monthly_listings_per_year"] / piv["yearly_contract"] - 1) * 100).round(1)
    return piv.reset_index().sort_values("premium_pct")


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def with_distance(df: pd.DataFrame, lat: float, lon: float) -> pd.DataFrame:
    df = df.copy()
    df["distance_km"] = haversine_km(lat, lon, df["latitude"], df["longitude"]).round(2)
    return df


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
def save_dataset(df: pd.DataFrame, label: str, data_dir: Path = DATA_DIR) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    path = data_dir / f"{stamp}_{label}.csv"
    df.to_csv(path, index=False)
    return path


def list_datasets(data_dir: Path = DATA_DIR) -> list[Path]:
    if not data_dir.exists():
        return []
    return sorted(data_dir.glob("*.csv"), reverse=True)


def load_datasets(paths: list[Path]) -> pd.DataFrame:
    frames = [pd.read_csv(p, dtype={"listing_id": str}) for p in paths]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return normalize(pd.DataFrame())
    df = pd.concat(frames, ignore_index=True)
    # Newest file first in `paths`, so keep="first" keeps the freshest price.
    return df.drop_duplicates(subset=["listing_id", "rent_frequency"], keep="first")
