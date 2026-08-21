import ee
import os
import pandas as pd
from pathlib import Path


class ERA5Acquisition:
    FEATURE_CATEGORIES = {
        "lake": [
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
        ],
        "precipitation": [
            "total_precipitation_sum",
            "total_precipitation_min",
            "total_precipitation_max",
            "runoff_sum",
            "runoff_min",
            "runoff_max",
            "surface_runoff_sum",
            "surface_runoff_min",
            "surface_runoff_max",
            "sub_surface_runoff_sum",
            "sub_surface_runoff_min",
            "sub_surface_runoff_max",
        ],
        "evaporation": [
            "total_evaporation_sum",
            "total_evaporation_min",
            "total_evaporation_max",
            "evaporation_from_open_water_surfaces_excluding_oceans_sum",
            "evaporation_from_open_water_surfaces_excluding_oceans_min",
            "evaporation_from_open_water_surfaces_excluding_oceans_max",
            "evaporation_from_bare_soil_sum",
        ],
        "thermal": [
            "skin_temperature",
            "temperature_2m",
            "dewpoint_temperature_2m",
            "surface_net_solar_radiation_sum",
            "surface_net_thermal_radiation_sum",
            "surface_sensible_heat_flux_sum",
            "surface_latent_heat_flux_sum",
            "surface_solar_radiation_downwards_sum",
            "surface_thermal_radiation_downwards_sum",
        ],
        "atmospheric": [
            "surface_pressure",
            "u_component_of_wind_10m",
            "v_component_of_wind_10m",
        ],
        "soil": [
            "volumetric_soil_water_layer_1",
            "volumetric_soil_water_layer_2",
            "volumetric_soil_water_layer_3",
            "volumetric_soil_water_layer_4",
        ],
    }

    def __init__(self, region, output_dir="dataset"):
        self.base_dir = output_dir
        self.region = region

    def _ensure_directories(self):
        dir_path = Path(self.base_dir) / self.region / "raw" / "era5"
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            return dir_path
        except Exception as e:
            print(f"Error creating directory {dir_path}: {e}")
            return None

    def _make_chunks(self, start_date: str, end_date: str, freq: str = "MS"):
        """Split a date range into contiguous chunks.

        freq: pandas offset alias, e.g. 'MS' (month start), 'YS' (year start),
        'W' (weekly).
        """
        bounds = pd.date_range(start=start_date, end=end_date, freq=freq)
        edges = sorted(
            set([pd.Timestamp(start_date)] + list(bounds) + [pd.Timestamp(end_date)])
        )

        chunks = []
        for i in range(len(edges) - 1):
            chunk_start = edges[i].strftime("%Y-%m-%d")
            chunk_end = edges[i + 1].strftime("%Y-%m-%d")
            if chunk_start != chunk_end:
                chunks.append((chunk_start, chunk_end))
        return chunks

    def acquire_era5(
        self,
        roi: ee.Geometry,
        start_date: str,
        end_date: str,
    ):
        """Acquire ERA5 climate data for the specified region and time period.

        Returns the output CSV path on success, or None on failure.
        """

        dir_path = self._ensure_directories()
        if dir_path is None:
            print("Error: Could not create era5 directory")
            return None

        try:
            bands = [
                "volumetric_soil_water_layer_1",
                "volumetric_soil_water_layer_2",
                "volumetric_soil_water_layer_3",
                "volumetric_soil_water_layer_4",
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
                "total_precipitation_sum",
                "total_precipitation_min",
                "total_precipitation_max",
                "runoff_sum",
                "runoff_min",
                "runoff_max",
                "surface_runoff_sum",
                "surface_runoff_min",
                "surface_runoff_max",
                "sub_surface_runoff_sum",
                "sub_surface_runoff_min",
                "sub_surface_runoff_max",
                "total_evaporation_sum",
                "total_evaporation_min",
                "total_evaporation_max",
                "evaporation_from_open_water_surfaces_excluding_oceans_sum",
                "evaporation_from_open_water_surfaces_excluding_oceans_min",
                "evaporation_from_open_water_surfaces_excluding_oceans_max",
                "evaporation_from_bare_soil_sum",
                "skin_temperature",
                "temperature_2m",
                "dewpoint_temperature_2m",
                "surface_net_solar_radiation_sum",
                "surface_net_thermal_radiation_sum",
                "surface_sensible_heat_flux_sum",
                "surface_latent_heat_flux_sum",
                "surface_solar_radiation_downwards_sum",
                "surface_thermal_radiation_downwards_sum",
                "surface_pressure",
                "u_component_of_wind_10m",
                "v_component_of_wind_10m",
            ]

            era5 = (
                ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR")
                .select(bands)
                .filterBounds(roi)
                .filterDate(start_date, end_date)
            )

            def mean(image):
                mean = image.reduceRegion(
                    reducer=ee.Reducer.mean(), geometry=roi, scale=9000, bestEffort=True
                )
                # image.set() accepts a dictionary directly — sets all bands at once
                return image.set(mean).set(
                    "system:time_start", image.get("system:time_start")
                )

            daily_averages = era5.map(mean)

            # Pull dates once
            dates = daily_averages.aggregate_array("system:time_start").getInfo()
            if not dates:
                print(f"  ⚠️ No ERA5 images found for {start_date} → {end_date}")
                return None
            dates = pd.to_datetime(dates, unit="ms")

            # Pull each band separately — aggregate_array can't take a list
            data = {}
            for band in bands:
                data[band] = daily_averages.aggregate_array(band).getInfo()

            daily_averages_df = pd.DataFrame(data, index=dates)
            daily_averages_df.index.name = "date"

            output_dir = f"{self.base_dir}/{self.region}/raw/era5/"
            os.makedirs(output_dir, exist_ok=True)

            out_path = f"{output_dir}/era5_{self.region}_{start_date}_{end_date}.csv"
            daily_averages_df.to_csv(out_path)

            # print(f"  📝 ERA5 data saved to {out_path}")
            return out_path

        except Exception as e:
            print(f"Error acquiring ERA5 data ({start_date} → {end_date}): {e}")
            return None

    def batch_acquire_era5(
        self, roi: ee.Geometry, start_date: str, end_date: str, freq: str = "MS"
    ):
        """Acquire ERA5 data in chunks (default: monthly) to avoid large getInfo() payloads.

        freq: 'MS' for monthly chunks, 'YS' for yearly chunks, 'W' for weekly.
        Returns a list of output CSV paths for successfully acquired chunks.
        """
        chunks = self._make_chunks(start_date, end_date, freq=freq)
        # print(f"  🗂️ Acquiring ERA5 data in {len(chunks)} chunk(s) ({freq})")

        results = []
        for chunk_start, chunk_end in chunks:
            # print(f"  📅 Acquiring ERA5 chunk: {chunk_start} → {chunk_end}")
            out_path = self.acquire_era5(roi, chunk_start, chunk_end)
            if out_path is None:
                # print(f"  ⚠️ Skipped/failed chunk {chunk_start} → {chunk_end}")
                continue
            results.append(out_path)

        # print(f"  ✅ {len(results)}/{len(chunks)} chunks acquired successfully")
        return results

    def merge_chunks(self, start_date: str, end_date: str):
        """Merge all previously acquired ERA5 chunk CSVs for this region into one file."""
        chunk_dir = Path(self.base_dir) / self.region / "raw" / "era5"
        files = sorted(chunk_dir.glob(f"era5_{self.region}_*.csv"))
        files = [f for f in files if "merged" not in f.stem]

        if not files:
            print(f"  ⚠️ No ERA5 chunk files found in {chunk_dir}")
            return None

        dfs = [pd.read_csv(f, index_col="date", parse_dates=True) for f in files]
        merged = pd.concat(dfs).sort_index()
        merged = merged[~merged.index.duplicated(keep="first")]

        out_path = chunk_dir / f"era5_{self.region}_{start_date}_{end_date}_merged.csv"
        merged.to_csv(out_path)
        # print(f"  📝 Merged {len(files)} chunk(s) into {out_path}")
        return out_path
    
    def split_by_category(self, csv_path, start_date: str, end_date: str):
        """Split a merged ERA5 CSV into one file per feature category.

        Reads the merged CSV (output of merge_chunks), slices columns by
        FEATURE_CATEGORIES, and writes each category to its own subdirectory
        under processed/era5/.
        """
        df = pd.read_csv(csv_path, index_col="date", parse_dates=True)

        output_paths = {}
        for category, bands in self.FEATURE_CATEGORIES.items():
            available_bands = [b for b in bands if b in df.columns]
            if not available_bands:
                print(f"  ⚠️ No columns found for category '{category}', skipping")
                continue

            category_dir = Path(self.base_dir) / self.region / "processed" / "era5" / category
            category_dir.mkdir(parents=True, exist_ok=True)

            out_path = category_dir / f"era5_{category}_{self.region}_{start_date}_{end_date}.csv"
            df[available_bands].to_csv(out_path)
            output_paths[category] = out_path
            # print(f"  📝 {category} features saved to {out_path}")

        return output_paths
    
    
    
    
#ERA5Acquisition(region="bogoria").split_by_category("dataset/bogoria/raw/era5/era5_bogoria_2023-01-01_2023-02-01.csv", "2023-01-01", "2023-12-31")
