import ee
import os


class ClimateAcquisition:
    def __init__(self, region, output_dir="dataset"):
        self.base_dir = output_dir
        self.region = region

    def acquire_era5_lake_temperature(
        self,
        roi: ee.Geometry,
        start_date: str,
        end_date: str,
    ):
        """Acquire ERA5 climate data for the specified region and time period."""

        era5 = (
            ee.ImageCollection("ECMWF/ERA5/DAILY")
            .filterBounds(roi)
            .filterDate(start_date, end_date)
            .select(
                [
                    "lake_bottom_temperature",
                    "lake_mix_layer_depth",
                    "lake_mix_layer_temperature",
                    "lake_total_layer_temperature",
                    "lake_bottom_temperature_min",
                    "lake_bottom_temperature_max",
                    "lake_mix_layer_depth_min",
                    "lake_mix_layer_depth_max",
                    "lake_mix_layer_temperature_min",
                    "lake_mix_layer_temperature_max",
                    "lake_total_layer_temperature_min",
                    "lake_total_layer_temperature_max",
                ]
            )
        )
        roi_climate = era5.reduceRegions(roi, ee.Reducer.first())

        roi_climates_dataframe = ee.data.computeFeatures(
            {"expression": roi_climate, "fileFormat": "PANDAS_DATAFRAME"}
        )
        roi_climates_dataframe
        # Save metadata
        output_dir = (
            f"{self.base_dir}/{self.region}/raw/climate/{roi_climates_dataframe}"
        )
        os.makedirs(output_dir, exist_ok=True)

        return era5
