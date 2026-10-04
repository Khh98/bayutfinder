import plotly.express as px
import streamlit as st

from bayut_finder.analytics import community_summary, monthly_vs_yearly
from bayut_finder.ui import (BEDROOM_ORDER, EMIRATE_COLORS, aed, color_map, current_data, download_button,
                             filters, listings_table, page_setup)

page_setup("Compare", "📊")
st.title("📊 Compare rents")

df = current_data()
if df.empty:
    st.stop()
view = filters(df, key="cmp")
if view.empty:
    st.warning("No listings match these filters.")
    st.stop()

colors = color_map(view["emirate"].unique())
# Same legend order on every chart: Dubai, Abu Dhabi, then the rest.
emirate_order = sorted(colors, key=lambda e: (list(EMIRATE_COLORS).index(e) if e in EMIRATE_COLORS else 99, e))


def style(fig, height=420):
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=40, b=8), legend_title_text="",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      hoverlabel=dict(namelength=-1))
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)", zeroline=False)
    fig.update_xaxes(showgrid=False)
    return fig


# ---------------------------------------------------------------- headline numbers
m1, m2, m3, m4 = st.columns(4)
m1.metric("Listings", f"{len(view):,}")
m2.metric("Median rent / month", aed(view["rent_monthly"].median()))
m3.metric("Median rent / year", aed(view["rent_yearly"].median()))
m4.metric("Median AED / sqft / year", aed(view["yearly_per_sqft"].median()))

# ---------------------------------------------------------------- by bedrooms
st.subheader("Typical rent by bedrooms")
by_beds = (view.groupby(["emirate", "bedrooms_label"])
               .agg(median_monthly=("rent_monthly", "median"),
                    median_yearly=("rent_yearly", "median"),
                    listings=("listing_id", "count"))
               .reset_index())
order = [b for b in BEDROOM_ORDER if b in set(by_beds["bedrooms_label"])]
left, right = st.columns([3, 2])
with left:
    fig = px.bar(by_beds, x="bedrooms_label", y="median_monthly", color="emirate",
                 barmode="group", category_orders={"bedrooms_label": order, "emirate": emirate_order},
                 color_discrete_map=colors,
                 labels={"bedrooms_label": "", "median_monthly": "Median AED / month"},
                 hover_data={"median_yearly": ":,.0f", "listings": True, "median_monthly": ":,.0f"})
    fig.update_traces(marker_cornerradius=4, marker_line_width=0)
    fig.update_layout(bargap=0.3, bargroupgap=0.08)
    st.plotly_chart(style(fig), width="stretch")
with right:
    table = by_beds.pivot(index="bedrooms_label", columns="emirate", values="median_monthly")
    table = table.reindex([b for b in order if b in table.index])
    table.index.name = "Bedrooms"
    table.columns.name = None
    st.caption("Median AED / month (× 12 for the yearly equivalent)")
    st.dataframe(table.style.format("{:,.0f}", na_rep="–"), width="stretch")

# ---------------------------------------------------------------- spread
st.subheader("Price spread")
fig = px.box(view, x="bedrooms_label", y="rent_monthly", color="emirate",
             category_orders={"bedrooms_label": order, "emirate": emirate_order}, color_discrete_map=colors,
             points=False, labels={"bedrooms_label": "", "rent_monthly": "AED / month"})
fig.update_traces(line_width=1.5)
st.plotly_chart(style(fig, 380), width="stretch")
st.caption("Box = middle 50% of listings, line = median. Very long whiskers usually mean a mix "
           "of budget and luxury buildings - narrow down by community.")

# ---------------------------------------------------------------- communities
st.subheader("Where is it cheaper?")
c1, c2 = st.columns([1, 3])
min_listings = c1.number_input("Min listings per community", 1, 50, 3,
                               help="Ignore communities with too few listings to trust the median.")
top_n = c1.slider("Show", 5, 40, 15)
rank_by = c1.radio("Rank by", ["Cheapest per month", "Cheapest per sqft", "Most listings"])
summary = community_summary(view, min_listings=min_listings)
if summary.empty:
    c2.info("Not enough listings per community yet - scrape more pages or lower the minimum.")
else:
    sort_col, asc = {"Cheapest per month": ("median_monthly", True),
                     "Cheapest per sqft": ("median_yearly_per_sqft", True),
                     "Most listings": ("listings", False)}[rank_by]
    top = summary.sort_values(sort_col, ascending=asc).head(top_n)
    x_col = "median_yearly_per_sqft" if sort_col == "median_yearly_per_sqft" else "median_monthly"
    fig = px.bar(top.iloc[::-1], y="community", x=x_col, color="emirate", orientation="h",
                 category_orders={"emirate": emirate_order},
                 color_discrete_map=colors,
                 labels={"community": "", "median_monthly": "Median AED / month",
                         "median_yearly_per_sqft": "Median AED / sqft / year"},
                 hover_data={"listings": True, "median_yearly": ":,.0f",
                             "min_monthly": ":,.0f", "median_sqft": ":,.0f"})
    fig.update_traces(marker_cornerradius=4, marker_line_width=0)
    fig.update_layout(bargap=0.35, yaxis=dict(categoryorder="array",
                                              categoryarray=list(top["community"].iloc[::-1])))
    fig.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.15)")
    fig.update_yaxes(showgrid=False)
    c2.plotly_chart(style(fig, max(320, 28 * len(top) + 80)), width="stretch")
    with st.expander("Community table"):
        st.dataframe(summary, hide_index=True, width="stretch",
                     column_config={c: st.column_config.NumberColumn(format="%d")
                                    for c in ("median_monthly", "median_yearly", "min_monthly",
                                              "median_sqft")})

# ---------------------------------------------------------------- monthly vs yearly
st.subheader("Paying monthly vs a yearly contract")
mvy = monthly_vs_yearly(view)
if mvy.empty:
    st.info("Needs both monthly and yearly listings for the same community and bedroom count. "
            "Run a search with **Rent paid = monthly + yearly** (and enough pages) to see this.")
else:
    overall = (mvy["monthly_listings_per_year"].sum() / mvy["yearly_contract"].sum() - 1) * 100
    st.markdown(f"Across **{len(mvy)}** comparable community × bedroom groups, monthly listings "
                f"cost **{overall:+.0f}%** over a full year compared to yearly contracts.")
    st.dataframe(
        mvy[["emirate", "community", "bedrooms_label", "yearly_contract",
             "monthly_listings_per_year", "premium_pct", "count_yearly", "count_monthly"]],
        hide_index=True, width="stretch",
        column_config={
            "yearly_contract": st.column_config.NumberColumn("Yearly contract (AED/yr)", format="%d"),
            "monthly_listings_per_year": st.column_config.NumberColumn("Monthly × 12 (AED/yr)",
                                                                       format="%d"),
            "premium_pct": st.column_config.NumberColumn("Monthly premium", format="%+.0f%%"),
            "emirate": "Emirate", "community": "Community", "bedrooms_label": "Beds",
            "count_yearly": "# yearly", "count_monthly": "# monthly",
        })

# ---------------------------------------------------------------- shortlist
st.subheader("Shortlist: priced below similar listings")
deals = view[view["vs_area_median"].notna()].sort_values("vs_area_median")
if deals.empty:
    st.info("Value scores need at least 3 comparable listings (same community, beds, rent period).")
else:
    listings_table(deals.head(50))
download_button(view, "bayut_filtered.csv")
