import streamlit as st
from src.processing.indices import CalculateIndices
from src.processing.sar import SARProcessor
from ui.common import run_job, file_filter_panel

REGIONS = ["bogoria", "baringo", "naivasha", "nakuru", "magadi", "turukana", "elementaita"]


def render(right_col):
    st.header("Processing")
    region = st.selectbox("Region", REGIONS, key="proc_region")

    with right_col:
        picked = file_filter_panel(region, stage="raw", key_prefix="proc")
        if picked:
            st.session_state["proc_selected_path"] = picked

    tabs = st.tabs(["Indices", "SAR"])

    with tabs[0]:
        image_path = st.text_input(
            "Local GeoTIFF path", key="idx_path",
            value=st.session_state.get("proc_selected_path", ""),
            placeholder=f"dataset/{region}/raw/sentinel2/...",
        )
        index_band = st.selectbox("Index", ["NDWI", "MNDWI", "NDVI", "AWEISH", "AWEI"])

        if st.button("Calculate", key="idx_btn"):
            calc = CalculateIndices(image=image_path, region=region, index_band=index_band)
            run_job(f"Calculating {index_band}", calc.save_indices_local, index_band)

    with tabs[1]:
        image_path = st.text_input(
            "Sentinel-1 GeoTIFF path", key="sar_path",
            value=st.session_state.get("proc_selected_path", ""),
            placeholder=f"dataset/{region}/raw/sentinel1/...",
        )
        image_id = st.text_input("Image ID (8-digit)", key="sar_id")
        method = st.selectbox(
            "Method",
            ["adaptive_threshold", "threshold", "local_threshold", "kmeans", "minimum_threshold"],
        )
        threshold_value = st.number_input("Threshold value", value=-15.0)
        save_shp = st.checkbox("Save shapefile", value=False)

        if st.button("Process SAR", key="sar_btn"):
            processor = SARProcessor(region, image_id)
            run_job(
                "SAR processing", processor.process_sentinel1_sar,
                image_path, method, threshold_value, save_shapefile=save_shp,
            )