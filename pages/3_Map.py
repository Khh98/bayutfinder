import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

from bayut_finder.analytics import with_distance
from bayut_finder.ui import (SEQUENTIAL_BLUE, current_data, download_button, filters,
                             listings_table, page_setup)

page_setup("Map", "🗺️")
st.title("🗺️ Map & nearest listings")

# Common reference points so no geocoding is needed for the usual suspects.
LANDMARKS = {
    "Downtown Dubai (Burj Khalifa)": (25.1972, 55.2744),
    "DIFC": (25.2110, 55.2797),
    "Business Bay": (25.1856, 55.2650),
    "Dubai Marina": (25.0805, 55.1403),
    "Dubai Internet City / Media City": (25.0950, 55.1590),
    "Al Barsha / Mall of the Emirates": (25.1181, 55.2006),
    "TECOM / Al Barsha Heights": (25.0975, 55.1770),
    "Dubai Silicon Oasis": (25.1180, 55.3800),
    "Dubai International Airport (DXB)": (25.2532, 55.3657),
    "Deira": (25.2711, 55.3075),
    "Abu Dhabi Corniche": (24.4764, 54.3434),
    "Al Reem Island": (24.4990, 54.4060),
    "Saadiyat Island": (24.5440, 54.4330),
    "Yas Island": (24.4880, 54.6030),
    "Khalifa City": (24.4200, 54.5770),
    "Abu Dhabi Airport (AUH)": (24.4330, 54.6511),
}


@st.cache_data(show_spinner=False, ttl=24 * 3600)
def geocode(place: str):
    """OpenStreetMap Nominatim, limited to the UAE. Free, no API key."""
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search",
                         params={"q": place, "format": "json", "limit": 1, "countrycodes": "ae"},
                         headers={"User-Agent": "bayut-finder-personal/1.0"}, timeout=15)
        r.raise_for_status()
        hits = r.json()
        if hits:
            return float(hits[0]["lat"]), float(hits[0]["lon"]), hits[0].get("display_name", place)
    except requests.RequestException:
        pass
    return None


df = current_data()
if df.empty:
    st.stop()
view = filters(df, key="map")
view = view[view["latitude"].notna() & view["longitude"].notna()]
if view.empty:
    st.warning("No listings with coordinates match these filters.")
    st.stop()

# ---------------------------------------------------------------- reference point
c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
landmark = c1.selectbox("Near", ["(none)", *LANDMARKS, "Custom place..."])
custom = c2.text_input("Custom place", placeholder="e.g. Dubai Hills Mall, Cleveland Clinic Abu Dhabi",
                       disabled=landmark != "Custom place...")
radius = c3.number_input("Radius (km)", 0.5, 100.0, 5.0, step=0.5)
nearest_n = c4.number_input("Nearest", 5, 200, 20, step=5)

point = None
if landmark in LANDMARKS:
    point = (*LANDMARKS[landmark], landmark)
elif landmark == "Custom place..." and custom:
    with st.spinner("Looking up place..."):
        point = geocode(custom)
    if not point:
        st.warning("Couldn't find that place. Try a more specific name or pick a landmark.")

if point:
    lat, lon, name = point
    view = with_distance(view, lat, lon)
    within = view[view["distance_km"] <= radius]
    st.caption(f"📍 {name} - **{len(within)}** listings within {radius:g} km")
    plot_df = within if not within.empty else view
else:
    plot_df = view

# ---------------------------------------------------------------- map
plot_df = plot_df.assign(
    beds=plot_df["bedrooms_label"],
    monthly=plot_df["rent_monthly"].map("AED {:,.0f}/mo".format),
    yearly=plot_df["rent_yearly"].map("AED {:,.0f}/yr".format),
)
scatter = getattr(px, "scatter_map", None)  # plotly >= 5.24 (MapLibre, no token)
kwargs = dict(lat="latitude", lon="longitude", color="rent_monthly",
              color_continuous_scale=SEQUENTIAL_BLUE[1:], hover_name="title",
              hover_data={"latitude": False, "longitude": False, "rent_monthly": False,
                          "monthly": True, "yearly": True, "beds": True, "area_sqft": ":,.0f",
                          "community": True, "building": True},
              labels={"rent_monthly": "AED / month"}, zoom=11 if point else 9.5, height=640)
if point:
    kwargs["center"] = {"lat": point[0], "lon": point[1]}
if scatter:
    fig = scatter(plot_df, **kwargs)
    fig.update_layout(map_style="open-street-map")
    marker_trace = go.Scattermap
else:  # older plotly
    fig = px.scatter_mapbox(plot_df, **kwargs)
    fig.update_layout(mapbox_style="open-street-map")
    marker_trace = go.Scattermapbox
fig.update_traces(marker=dict(size=10, opacity=0.85))
if point:
    fig.add_trace(marker_trace(lat=[point[0]], lon=[point[1]], mode="markers+text",
                               marker=dict(size=16, color="#c83a3a"), text=["📍"],
                               name=point[2][:40], hovertext=point[2], hoverinfo="text"))
fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), showlegend=False,
                  coloraxis_colorbar=dict(title="AED/mo", thickness=12))
st.plotly_chart(fig, width="stretch")
st.caption("Several listings in one building share a pin - hover to see them, or use the table below.")

# ---------------------------------------------------------------- table
if point:
    st.subheader(f"Nearest {nearest_n} to {point[2][:60]}")
    nearest = view.nsmallest(int(nearest_n), "distance_km")
    listings_table(nearest, extra=["distance_km"])
    download_button(nearest, "bayut_nearest.csv")
else:
    st.subheader("Listings on the map")
    listings_table(plot_df.sort_values("rent_monthly"))
