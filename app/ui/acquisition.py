# ui/acquisition.py

import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
import geemap
import ee
import streamlit as st

from config import get_roi_by_name
from src.acquisition.image_aquisition import ImageAcquisition
from src.acquisition.era5 import ERA5Acquisition
from src.acquisition.dem_aquisition import DEMAcquisition
from src.processing.wbm import WBMProcessor
from ui.common import run_job

REGIONS = ["bogoria", "baringo", "naivasha", "nakuru", "magadi", "turukana", "elementaita"]

S2_VIS = {"bands": ["Red", "Green", "Blue"], "min": 0, "max": 3000}


def _draw_map(region, roi, preview_image=None, vis_params=None):
    centroid = roi.centroid().coordinates().getInfo()  # [lon, lat]
    m = folium.Map(location=[centroid[1], centroid[0]], zoom_start=12)

    folium.GeoJson(
        roi.getInfo(), name="Saved ROI",
        style_function=lambda x: {"color": "blue", "fill": False},
    ).add_to(m)

    if preview_image is not None:
        geemap.ee_tile_layer(preview_image, vis_params or S2_VIS, "Preview").add_to(m)

    Draw(
        export=False,
        position="topleft",
        draw_options={
            "polygon": True, "rectangle": True,
            "circle": False, "marker": False, "circlemarker": False, "polyline": False,
        },
    ).add_to(m)
    folium.LayerControl().add_to(m)

    return st_folium(m, height=480, use_container_width=True, key=f"map_{region}")


def render():
    st.header("Acquisition")
    region = st.selectbox("Region", REGIONS, key="acq_region")
    roi = get_roi_by_name(region)

    st.subheader("Region of interest")
    st.caption("Draw a polygon/rectangle to override the saved ROI for this run. Leave blank to use the saved boundary from config.py.")

    preview_toggle = st.checkbox("Preview latest Sentinel-2 composite on map", value=False)
    preview_image = None
    if preview_toggle:
        col1, col2 = st.columns(2)
        p_start = col1.date_input("Preview start", key="preview_start")
        p_end = col2.date_input("Preview end", key="preview_end")
        s2 = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(roi).filterDate(str(p_start), str(p_end))
            .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", 30))
        )
        preview_image = s2.median().clip(roi).select(
            ["B4", "B3", "B2"], ["Red", "Green", "Blue"]
        )

    map_output = _draw_map(region, roi, preview_image)

    drawn_roi = None
    if map_output and map_output.get("last_active_drawing"):
        coords = map_output["last_active_drawing"]["geometry"]["coordinates"]
        drawn_roi = ee.Geometry.Polygon(coords)
        st.success("Using drawn polygon as ROI for this run.")

    active_roi = drawn_roi if drawn_roi is not None else roi

    tabs = st.tabs(["Sentinel-2 / Sentinel-1 / Landsat", "ERA5", "DEM", "WBM"])

    with tabs[0]:
        satellite = st.selectbox("Satellite", ["sentinel2", "sentinel1", "landsat8", "landsat9"])
        col1, col2 = st.columns(2)
        start_date = col1.date_input("Start date", key="acq_start")
        end_date = col2.date_input("End date", key="acq_end")
        max_cloud = st.slider("Max cloud %", 0, 100, 30)

        if st.button("Acquire", key="acq_btn"):
            acq = ImageAcquisition(region=region)
            s, e = str(start_date), str(end_date)
            if satellite == "sentinel2":
                run_job("Sentinel-2 acquisition", acq.acquire_sentinel2, active_roi, s, e, max_cloud)
            elif satellite == "sentinel1":
                run_job("Sentinel-1 acquisition", acq.acquire_sentinel1, active_roi, s, e)
            else:
                run_job(f"{satellite} acquisition", acq.acquire_landsat, active_roi, s, e, satellite, max_cloud)

    with tabs[1]:
        col1, col2 = st.columns(2)
        start_date = col1.date_input("Start date", key="era5_start")
        end_date = col2.date_input("End date", key="era5_end")
        freq = st.selectbox("Chunk frequency", ["MS", "YS", "W"], help="MS=monthly, YS=yearly, W=weekly")

        if st.button("Acquire ERA5", key="era5_btn"):
            era5 = ERA5Acquisition(region=region)
            s, e = str(start_date), str(end_date)
            chunks = run_job("ERA5 acquisition", era5.batch_acquire_era5, active_roi, s, e, freq)
            if chunks:
                run_job("Merging ERA5 chunks", era5.merge_chunks, s, e)

    with tabs[2]:
        col1, col2 = st.columns(2)
        start_date = col1.date_input("Start date", key="dem_start")
        end_date = col2.date_input("End date", key="dem_end")

        if st.button("Acquire DEM", key="dem_btn"):
            dem = DEMAcquisition(region=region)
            run_job("DEM acquisition", dem.acquire_dem, active_roi, str(start_date), str(end_date))

    with tabs[3]:
        st.caption("Computes WBM stats from an already-downloaded WBM band (see DEM tab).")
        wbm_path = st.text_input("WBM GeoTIFF path", placeholder=f"dataset/{region}/raw/dem/...")
        image_id = st.text_input("Image ID (8-digit)", key="wbm_id")

        if st.button("Compute WBM stats", key="wbm_btn"):
            processor = WBMProcessor(region, image_id)
            run_job("WBM processing", processor.process_wbm_batch, wbm_path)