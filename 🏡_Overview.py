import streamlit as st
import base64
from PIL import Image
import requests
from streamlit_lottie import st_lottie

def load_lottieurl(url):
    r = requests.get(url)
    if r.status_code != 200:
        return None
    return r.json()

# ---- LOAD ASSETS ----
lottie_coding = load_lottieurl("https://lottie.host/1112f618-f3f7-4ed5-8bc7-5315eebcab7a/qEognHBE66.json")



#Homepage configuration
# Fetch the image from the GitHub repository
im = Image.open("logo.jpeg")
st.set_page_config(
    page_title="Find your bayt",
    page_icon=im,
    layout="wide",
    initial_sidebar_state="expanded")

hide_st_style = """
<style>
#MainMenu {visibility: hidden;}
header{visibility: hidden;}
footer {visibility: hidden;}
</style>

"""
st.markdown(hide_st_style, unsafe_allow_html=True)

# ---Side-Bar----

with st.sidebar:
    st_lottie(lottie_coding, height=200, key="coding")
    st.markdown("""<h1>Web scraping Bayut to find your ideal property</h1>""",unsafe_allow_html=True)
    with st.expander(" App Description"):
      st.markdown('''
    <br><p>
    The app offers a straightforward journey through real estate data from Bayut. <br>Kick-off your exploration by selecting <b>'overview'</b> to get acquainted with the utilized features.</br> Subsequent sections of the app will seamlessly fetch Bayut data for you, providing a close-up examination of properties through interactive maps. Immerse yourself in this user-friendly interface to discover potential dream homes!</p></br>
        ''',unsafe_allow_html=True)
title = "<h1 style='text-align:center;color:#50C878; font-size:25px;'>Bayut Finder Analysis</h1>" 
st.markdown(title, unsafe_allow_html=True)
html="""<p style="font-family: Serif;font-size:24px;line-height:1.5em;color: #333333;">Explore a diverse range of properties with our interactive filters, enabling you to uncover real estate options that match your preferences. <br>Delve into property prices, discover trends, and utilize our map feature to visualize locations of interest.<br>Find your ideal property and explore the nearby areas effortlessly.</br></p>"""
st.markdown(html, unsafe_allow_html=True)
file_ = open("bayout.gif", "rb")
contents = file_.read()
data_url = base64.b64encode(contents).decode("utf-8")
file_.close()
st.write("")
st.markdown(
           f'<img src="data:image/gif;base64,{data_url}" alt="gif" width="660" height= "390">',
         unsafe_allow_html=True,)