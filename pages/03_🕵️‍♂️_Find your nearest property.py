import streamlit as st
import requests
import pandas as pd
from streamlit_extras.let_it_rain import rain
from streamlit_extras.dataframe_explorer import dataframe_explorer
from streamlit_extras.colored_header import colored_header

from bs4 import BeautifulSoup as bs
import numpy as np
import re
import sys
from tqdm import tqdm
from datetime import datetime
import plotly.express as px
from geopy.distance import geodesic


colored_header(
    label="Find Nearest Property in Dubai (per month)",
    description="Prices are subject to changes due to real estate trends",
    color_name="blue-70"
)

# Load the property data
df_rental = pd.read_csv('ppties_dubai.csv')
df_rental['prices'] = df_rental['prices'].str.replace(",","").astype("int64")
df_rental[['property_name', 'location_name']] = df_rental['locations'].str.split(', ', 1, expand=True)


def filter_properties(price_range,location):
    min_price, max_price = price_range
    filtered_df = df_rental[(df_rental['prices'] >= min_price) & (df_rental['prices'] <= max_price)  & (df_rental['location_name'] == location)]
    return filtered_df

def get_nearest_properties(user_location, num_properties=5):
    user_lat, user_lon = user_location
    df_rental['distance'] = df_rental.apply(lambda row: geodesic((user_lat, user_lon), (row['Latitude'], row['Longitude'])).kilometers, axis=1)
    nearest_properties = df_rental.nsmallest(num_properties, 'distance')
    nearest_properties.drop(columns=['distance'], inplace=True)
    return nearest_properties

def main():
    min_price = st.slider('Minimum Price', min_value=1000, max_value=10000, step=1000, value=2000)
    max_price = st.slider('Maximum Price', min_value=1000, max_value=10000, step=1000, value=8000)
    price_range = (min_price, max_price)

    unique_locations = df_rental['location_name'].unique()
    loc_name = st.selectbox('Location', unique_locations)

    # Apply filters and display properties on the map
    filtered_properties = filter_properties(price_range, loc_name)
    nearest_properties = get_nearest_properties((filtered_properties['Latitude'].mean(), filtered_properties['Longitude'].mean()))

    # Get the latitude and longitude of the selected location
    selected_location = df_rental[df_rental['location_name'] == loc_name]
    selected_lat, selected_lon = selected_location.iloc[0]['Latitude'], selected_location.iloc[0]['Longitude']

    # Display filtered properties on the map
    fig = px.scatter_mapbox(filtered_properties, lat='Latitude', lon='Longitude', hover_name='Property_keywords', hover_data={'Latitude':False, 'Longitude':False, 'prices':True}, color='prices', size='prices')
    fig.update_traces(marker=dict(opacity=0.8), selector=dict(mode='markers+text'))
    fig.add_trace(px.scatter_mapbox(nearest_properties, lat='Latitude', lon='Longitude', hover_name='Property_keywords', hover_data={'Latitude':False, 'Longitude':False, 'prices':True, 'Property_keywords':True}, color='prices', size='prices').data[0])

# Set map layout with the initial zoom based on the selected location
    fig.update_layout(mapbox_style='open-street-map', height=900, margin={"r": 80, "t": 80, "l": 80, "b": 80},
                  mapbox=dict(center=dict(lat=selected_lat, lon=selected_lon), zoom=12))

    st.plotly_chart(fig)

    st.subheader('Nearest Properties Details')
    for _, row in nearest_properties.iterrows():
        st.markdown(f"* {row['Property_keywords']} located at {row['location_name']} with a price of {row['prices']}")

main()
