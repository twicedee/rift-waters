
import streamlit as st
from ui.common import authenticate
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


st.set_page_config(page_title="Riftwaters Pipeline", layout="wide")
authenticate("riftwaters")  # Google Earth Engine project ID

st.sidebar.title("Riftwaters")
section = st.sidebar.radio("Section", ["Acquisition", "Processing", "Analysis"])

if section == "Acquisition":
    import ui.acquisition as page
    page.render()  # map takes the full width; no right filter panel here

elif section == "Processing":
    import ui.processing as page
    main_col, right_col = st.columns([4, 1.3])
    with main_col:
        page.render(right_col)

elif section == "Analysis":
    import ui.analysis as page
    main_col, right_col = st.columns([4, 1.3])
    with main_col:
        page.render(right_col)