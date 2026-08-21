
from setuptools import setup, find_packages

setup(
    name="riftwaters",
    version="0.1.0",
    description="Flood investigation and predictive AI pipeline for Rift Valley lake water levels",
    author="Desy",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.10",
    install_requires=[
        "earthengine-api",
        "geemap",
        "rasterio",
        "geopandas",
        "numpy",
        "pandas",
        "scipy",
        "scikit-learn",
        "scikit-image",
        "shapely",
        "matplotlib",
    ],
    entry_points={
        "console_scripts": [
            "riftwaters=main:main",
        ],
    },
)