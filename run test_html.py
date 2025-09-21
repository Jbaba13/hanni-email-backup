import streamlit as st

st.set_page_config(page_title="HTML Test")

st.write("Test 1: Basic HTML")
st.markdown("<h1>This should be a heading</h1>", unsafe_allow_html=True)

st.write("Test 2: Styled HTML")
st.markdown('<p style="color: red;">This should be red text</p>', unsafe_allow_html=True)

st.write("Test 3: Div with background")
st.markdown('''
<div style="background: purple; color: white; padding: 20px;">
    This should have purple background
</div>
''', unsafe_allow_html=True)

st.write("Test 4: Without unsafe_allow_html")
st.markdown("<h1>This should show as raw HTML</h1>")

st.write("Test 5: Using components.html")
import streamlit.components.v1 as components
components.html("<h1 style='color: blue;'>Blue heading via components</h1>", height=100)