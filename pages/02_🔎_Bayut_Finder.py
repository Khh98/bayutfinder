import streamlit as st
import requests
import pandas as pd
from streamlit_extras.let_it_rain import rain
from streamlit_extras.dataframe_explorer import dataframe_explorer
from streamlit_extras.colored_header import colored_header
from streamlit_echarts import st_echarts

from bs4 import BeautifulSoup as bs
import numpy as np
import re
import sys
from tqdm import tqdm
from datetime import datetime
import plotly.express as px
from geopy.distance import geodesic


Emirates_values = ['dubai','abu-dhabi','sharjah','ajman','umm-al-quwain','ras-al-khaimah','fujairah']
Properties_per_page = 24
def get_url(furnished='all',rent_frequency='yearly',emirate='dubai',page=1):
  '''
  args:
  - furnished: all will include furnished and unfurnished properties
  - rent frequency: yearly by default and It may be monthly rent or weekly daily etc.
  - emirates: dubai or abu dhabi or you may choose any emirate , we will focus on these two for our current analysis
  - page: pages including the properties data
  <This function will get the appropriate url for bayut.com based on the search criteria we set>
  '''
  if page ==1:
    url=f'https://www.bayut.com/to-rent/property/{emirate}/'
  else:
    url = f'https://www.bayut.com/to-rent/property/{emirate}/page-{page}/'
  if rent_frequency == 'monthly':
    url += "?rent_frequency=monthly"
  elif rent_frequency == 'daily':
    url += "?rent_frequency=daily"
  elif rent_frequency == 'weekly':
    url += "?rent_frequency=weekly"
  if furnished == 'furnished':
    url += "&furnishing_status=furnished"
  elif furnished == 'unfurnished':
    url += "&furnishing_status=unfurnished"
  return url



def get_property(emirate='dubai',furnished='all',rent_frequency='yearly',fast_scrape=False):
    emirate = emirate.lower().replace(' ','-')
    assert emirate in Emirates_values, f'emirate attr must be one of {Emirates_values}'
    assert furnished in ['all','furnished','unfurnished'], f"furnished attr must be one of {['all','furnished','unfurnished']}"
    bedrooms,bathrooms,area,prices,locations,property_types,property_keywords = [],[],[],[],[],[],[]
    url = get_url(furnished='furnished',rent_frequency='monthly',emirate='dubai',page=1)


    html_text =  requests.get(url).content
    soup = bs(html_text,'lxml')
    num_properties = int(soup.find('span',class_='ca3976f7').text.split(' ')[-2].replace(',',''))

    pages = (num_properties//Properties_per_page) + 1
    print(f"Found {num_properties} properties with furnished={furnished} ({pages} pages)")
    for page in tqdm(range(1,pages)):
        try:
            url = get_url(furnished=furnished,rent_frequency=rent_frequency,emirate=emirate,page=page)
            html_text = requests.get(url).content
            soup = bs(html_text,'lxml')
            properties = soup.find_all('div',class_='d6e81fd0')
            for property in properties:
                try:
                    prices.append(property.find('span',class_='f343d9ce').text)
                except:
                    prices.append(-1)
                try:
                    locations.append(property.find('div',class_='_00a37089').text)
                except:
                    locations.append(-1)
                try:
                    property_types.append(property.find('span',class_='_6acf48d3 fd8e0e18',attrs={'aria-label': 'Type'}).text)
                except:
                    property_types.append(-1)
                try:
                    property_keywords.append(property.find('h2',class_='_7f17f34f').text)  
                except:
                    property_keywords.append(-1)
                try:
                    bedrooms_element = property.find('span', class_='_6acf48d3 fd8e0e18', attrs={'aria-label': ['Studio', 'Beds']})
                    bedrooms_value = bedrooms_element.text if bedrooms_element else None
                    bedrooms.append(bedrooms_value)
                except:
                    bedrooms.append(None)
                try:
                    bathrooms.append(property.find('span',class_='_6acf48d3 fd8e0e18',attrs={'aria-label': 'Baths'}).text)
                except:
                    bathrooms.append(-1)
                try:
                    area.append(property.find('span',class_='_4bdd430c').text)
                except:
                    area.append(-1)

        except Exception as e:
            print(e)
            print(f"Exiting early.. scraped {page-1}/{pages}")
            break
            continue
    col_dict = {
    "Property_keywords": property_keywords,
    "bedrooms" : bedrooms,
    "bathrooms": bathrooms,
    "area": area,
    "prices" : prices,
    "locations" : locations,
    "property_types" : property_types,
}

    df = pd.DataFrame(col_dict)
    filtered_df= dataframe_explorer(df)
    st.dataframe(filtered_df, use_container_width=True)
 # Input options
colored_header(
    label="Data Collection",
    description="Use the following filters and click on scrape to get your desired property data",
    color_name="blue-70"
)
col1,col2,col3 = st.columns([2,2,2])
with col1:
   emirate = st.selectbox('Emirate', ['dubai','abu-dhabi','sharjah','ajman','umm-al-quwain','ras-al-khaimah','fujairah'])
with col2:
   furnished = st.selectbox('Furnished:', ['all','furnished', 'unfurnished'])
with col3:
   rent_frequency = st.selectbox('Rent Frequency:', ['monthly', 'yearly'])
# Scrape button
if st.button('Scrape'):
        liquidfill_option = {
    "series": [{"type": "liquidFill", "data": [0.6, 0.5, 0.4, 0.3]}]
}
        st_echarts(liquidfill_option)
        get_property(emirate=emirate, furnished=furnished, rent_frequency=rent_frequency, fast_scrape=True)
        # Display the scraped data in a DataFrame
        st.write('Scraping complete!')
        rain(
    emoji="🥳",
    font_size=54,
    falling_speed=5,
    animation_length="5",
)

st.write("")
st.write("")
colored_header(
    label="Locate My Bayut",
    description="Interactive map to find your ideal property in Dubai (per month)",
    color_name="green-70"
)


df_rental = pd.read_csv('ppties_dubai.csv')
df_rental['prices'] = df_rental['prices'].str.replace(",","").astype("int64")

#filters
col11,col12,col13 = st.columns([2,2,2])
with col11:
   selected_bedrooms = st.selectbox("Number of Rooms", df_rental["bedrooms"].unique())
with col12:
   min_price = st.number_input("Min Price", min_value=df_rental["prices"].min(), max_value=df_rental["prices"].max(), value=df_rental["prices"].min())
with col13:
   max_price = st.number_input("Max Price", min_value=df_rental["prices"].min(), max_value=df_rental["prices"].max(), value=df_rental["prices"].max())
# Filter the data based on selected filters
filtered_data = df_rental[(df_rental["bedrooms"] == selected_bedrooms) & (df_rental["prices"].between(min_price, max_price))]

# Create the map
cscale = [
    [0.0, 'rgb(165,0,38)'],
    [0.0001, 'rgb(215,48,39)'],
    [0.001, 'rgb(250, 152, 122)'],
    [0.01, 'rgb(255, 204, 153)'],
    [0.05, 'rgb(255, 255, 153)'],
    [0.1, 'rgb(0, 255, 179)'],
    [0.3, 'rgb(171,217,233)'],
    [0.7, 'rgb(116,173,209)'],
    [0.9, 'rgb(69,117,180)'],
    [1.0, 'rgb(49,54,149)']
]
map = px.scatter_mapbox(filtered_data, lat="Latitude", lon="Longitude", opacity=1.0, 
                        color='prices', size="prices",
                        color_continuous_scale=cscale,
                        height=900,width=800, zoom=9,
                        text='bedrooms',
                        hover_name='locations')

map.update_layout(mapbox_style="open-street-map") 
map.update_layout(margin={"r": 80, "t": 80, "l": 80, "b": 80})
map_container = st.container()
with map_container:
    st.plotly_chart(map)

# Display the map



