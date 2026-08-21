# ui/common.py

import contextlib
from pathlib import Path
import ee
import streamlit as st


@st.cache_resource
def authenticate(project_id):
    try:
        # Try existing credentials first
        ee.Initialize(project=project_id)
        print("✓ Using existing credentials")
    except:
        # Authenticate if needed
        print("Authentication required...")
        ee.Authenticate()
        ee.Initialize(project=project_id)
        print("✓ Authentication complete")


class StreamlitLog:
    """Redirects stdout so existing print()-based progress shows up live."""
    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.lines = []

    def write(self, text):
        if text.strip():
            self.lines.append(text)
            self.placeholder.code("".join(self.lines))

    def flush(self):
        pass


def run_job(label, fn, *args, **kwargs):
    with st.status(label, expanded=True) as status:
        log_area = st.empty()
        logger = StreamlitLog(log_area)
        try:
            with contextlib.redirect_stdout(logger):
                result = fn(*args, **kwargs)
            status.update(label=f"✅ {label} complete", state="complete")
            return result
        except Exception as e:
            status.update(label=f"❌ {label} failed: {e}", state="error")
            st.exception(e)
            return None


def list_dataset_files(region, stage="raw"):
    """
    Group files under dataset/{region}/{stage}/** by subfolder
    (sentinel2, sentinel1, dem, era5, sar_water_mask, indices, ...).
    """
    base = Path(f"./dataset/{region}/{stage}")
    if not base.exists():
        return {}
    grouped = {}
    for sub in sorted(base.iterdir()):
        if sub.is_dir():
            files = sorted(sub.rglob("*.tif")) + sorted(sub.rglob("*.csv"))
            if files:
                grouped[sub.name] = files
    return grouped


def file_filter_panel(region, stage="raw", key_prefix=""):
    """
    Right-side filter panel. Lets the user narrow by subfolder + a text
    filter (matches on filename, e.g. an 8-digit image_id or 'VV').
    Returns the selected file path, or None.
    """
    st.caption(f"Files — {region}/{stage}")
    grouped = list_dataset_files(region, stage)
    if not grouped:
        st.info("No files found yet.")
        return None

    subfolder = st.selectbox("Folder", list(grouped.keys()), key=f"{key_prefix}_folder")
    text_filter = st.text_input("Filter (e.g. image_id)", key=f"{key_prefix}_filter")

    matches = [f for f in grouped[subfolder] if text_filter in f.name] if text_filter else grouped[subfolder]
    labels = [f.name for f in matches]

    if not labels:
        st.warning("No files match.")
        return None

    choice = st.radio("Select", labels, key=f"{key_prefix}_choice", label_visibility="collapsed")
    selected = str(next(f for f in matches if f.name == choice))
    if st.button("Use this file", key=f"{key_prefix}_use"):
        return selected
    return None