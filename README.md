<div align="center">

# 📡 RW-AIMS

**Rift-Water Analysis and Image Management System**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Google Earth Engine](https://img.shields.io/badge/🌍-Earth%20Engine-34A853.svg)](https://earthengine.google.com/)
[![Geemap](https://img.shields.io/badge/🗺️-Geemap-4285F4.svg)](https://geemap.org/)
[![Pandas](https://img.shields.io/badge/🐼-Pandas-150458.svg)](https://pandas.pydata.org/)
[![NumPy](https://img.shields.io/badge/🔢-NumPy-013243.svg)](https://numpy.org/)
[![Rasterio](https://img.shields.io/badge/🖼️-Rasterio-6C9F3E.svg)](https://rasterio.readthedocs.io/)
[![GeoPandas](https://img.shields.io/badge/🌐-GeoPandas-139C5A.svg)](https://geopandas.org/)
[![Scikit-learn](https://img.shields.io/badge/🤖-Scikit--learn-F7931E.svg)](https://scikit-learn.org/)
[![Matplotlib](https://img.shields.io/badge/📊-Matplotlib-11557C.svg)](https://matplotlib.org/)
[![SciPy](https://img.shields.io/badge/📈-SciPy-8CAAE6.svg)](https://scipy.org/)
[![TQDM](https://img.shields.io/badge/⏳-TQDM-FFA500.svg)](https://tqdm.github.io/)

</div>
A comprehensive satellite imagery acquisition and processing system for monitoring water bodies in the East African Rift Valley region. RW-AIMS integrates Google Earth Engine (GEE) capabilities for acquiring, processing, and analyzing satellite data from multiple sources including Sentinel-2, Sentinel-1, and Landsat missions.

## 🚀 Features

- **Multi-satellite Acquisition**: Acquire imagery from Sentinel-2, Sentinel-1, and Landsat satellites
- **Spectral Indices Calculation**: Compute various vegetation and water indices (NDVI, NDWI, etc.)
- **SAR Processing**: Process Sentinel-1 SAR data for water detection and monitoring
- **Climate Data Integration**: Acquire ERA5 climate data for environmental analysis
- **Batch Processing**: Automated batch acquisition of satellite imagery over time periods
- **Visualization Tools**: Built-in visualization capabilities for acquired imagery
- **Predefined Regions**: Support for major East African lakes (Baringo, Bogoria, Naivasha, Nakuru, Magadi, Turkana)

## 📋 Prerequisites

- Python 3.8+
- Google Earth Engine account
- Google Cloud Project with Earth Engine API enabled
- Service account credentials (for automated authentication)

## 🔧 Installation

1. **Fork and Clone the repository:**
```
git clone https://github.com/yourusername/RW-AIMS.git
cd RW-AIMS
```

2. **Create a virtual environment**

   - On Windows:

```python -m venv env```
```env\Scripts\activate.bat```


   - On Mac/Linux:
```python3 -m venv env```
```source env/bin/activate```





## 📚 Additional Resources

- [Google Earth Engine Documentation](https://developers.google.com/earth-engine)
- [Sentinel Hub Documentation](https://docs.sentinel-hub.com/)
- [USGS Landsat Documentation](https://www.usgs.gov/landsat-missions)
- [ESA Sentinel-2 User Guide](https://sentinel.esa.int/web/sentinel/user-guides/sentinel-2-msi)
- [ECMWF ERA5 Climate Data](https://www.ecmwf.int/en/forecasts/datasets/reanalysis-datasets/era5)
- [Geemap Documentation](https://geemap.org/)
- [Earth Engine Python API Reference](https://developers.google.com/earth-engine/guides/python_install)




