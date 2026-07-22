import ee
import geemap
import json

import pandas as pd
from pathlib import Path
from datetime import datetime
import numpy as np


class DEMAcquisition:
    def __init__(self, region):
        self.region = region
        self.base_dir = Path(f"./dataset/{region}")

    def _ensure_directories(self):
        dir_path = self.base_dir / "raw" / "dem"
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            return dir_path
        except Exception as e:
            print(f"Error creating directory {dir_path}: {e}")
            return None

    def _save_metadata(self, metadata: dict):
        metadata_dir = self.base_dir / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)

        json_path = metadata_dir / f"{self.region}_dem.json"

        json_entry = {
            "source": metadata.get("source", "COPERNICUS/DEM/GLO30_2024_1"),
            "start_date": metadata.get("start_date", ""),
            "end_date": metadata.get("end_date", ""),
            "scale_m": metadata.get("scale", 30),
            "crs": metadata.get("crs", "EPSG:4326"),
            "include_wbm": metadata.get("include_wbm", False),
            "acquisition_time": datetime.now().strftime("%Y%m%d_%H%M%S"),
        }

        if json_path.exists():
            with open(json_path, "r") as f:
                existing_data = json.load(f)
                if isinstance(existing_data, list):
                    existing_data.append(json_entry)
                else:
                    existing_data = [existing_data, json_entry]
        else:
            existing_data = [json_entry]

        with open(json_path, "w") as f:
            json.dump(existing_data, f, indent=2)

        csv_path = metadata_dir / f"{self.region}_dem.csv"

        # One row per image_id, carrying BOTH band paths — avoids the DEM row
        # getting evicted by a later WBM save for the same image_id.
        df_entry = pd.DataFrame(
            [
                {
                    "image_id": metadata.get("image_id", ""),
                    "dem_path": metadata.get("dem_path", ""),
                    "wbm_path": metadata.get("wbm_path", ""),
                }
            ]
        )

        if csv_path.exists():
            existing_df = pd.read_csv(csv_path)
            existing_df = existing_df[
                existing_df["image_id"] != metadata.get("image_id", "")
            ]
            updated_df = pd.concat([existing_df, df_entry], ignore_index=True)
            updated_df.to_csv(csv_path, index=False)
        else:
            df_entry.to_csv(csv_path, index=False)

        print(f"  📝 Metadata saved to {json_path} and {csv_path}")

    def acquire_dem(
        self,
        roi: ee.Geometry,
        start_date: str,
        end_date: str,
        scale: int = 30,
        crs: str = "EPSG:4326",
        include_wbm: bool = True,
    ) -> dict:

        dem_dir = self._ensure_directories()
        if dem_dir is None:
            print("Error: Could not create dem directory")
            return None

        try:

            def get_band(band):
                image = (
                    ee.ImageCollection("COPERNICUS/DEM/GLO30_2024_1")
                    .select(band)
                    .filterBounds(roi)
                    .mosaic()
                    .clip(roi)
                )
                image_id = int(end_date.replace("-", ""))
                output_filename = f"{self.region}_{image_id}_{band}.tif"
                output_path = dem_dir / output_filename
                return image, output_path, image_id

            def save_image(image, output_path, band):
                # Single CRS used consistently for both direct download and
                # the Drive fallback, rather than re-detecting it per export.
                c
                print(f"  ✅ {band} saved to {output_path}")

                task = ee.batch.Export.image.toDrive(
                    image=image,
                    folder="GEE_exports",
                    fileNamePrefix=f"{self.region}_{image_id}_{band}",  # plain filename, not local path
                    region=roi,
                    scale=scale,
                    crs=crs,
                    maxPixels=1e10,
                )
                # task.start()

            print(f"  ⬇️ Downloading Copernicus GLO-30 DEM for {self.region}...")

            if crs == "EPSG:4326":
                print("  ⚠️ WARNING: DEM is in geographic CRS (EPSG:4326)")
                print("     Reproject to UTM before using with SAR boundaries")

            dem_image, dem_output_path, image_id = get_band("DEM")
            save_image(dem_image, dem_output_path, "DEM")

            wbm_output_path = None
            if include_wbm:
                wbm_image, wbm_output_path, image_id = get_band("WBM")
                save_image(wbm_image, wbm_output_path, "WBM")

            self._save_metadata(
                {
                    "source": "COPERNICUS/DEM/GLO30_2024_1",
                    "image_id": str(image_id),
                    "dem_path": str(dem_output_path),
                    "wbm_path": str(wbm_output_path) if wbm_output_path else "",
                    "start_date": start_date,
                    "end_date": end_date,
                    "scale": scale,
                    "crs": crs,
                    "include_wbm": include_wbm,
                }
            )

            return {
                "dem_path": str(dem_output_path),
                "wbm_path": str(wbm_output_path) if wbm_output_path else None,
            }

        except Exception as e:
            print(f"❌ Error acquiring DEM data: {e}")
            return None

    def batch_acquisition(
        self,
        roi: ee.Geometry,
        start_year: int,
        end_year: int,
        scale: int = 30,
        crs: str = "EPSG:4326",
        interval_months: int = 12,
        include_wbm: bool = True,
    ):
        month_ranges = []
        for year in range(start_year, end_year + 1):
            for month in range(1, 13, interval_months):
                start_date = datetime(year, month, 1).strftime("%Y-%m-%d")

                if month + interval_months - 1 > 12:
                    end_month = 12
                    end_year_temp = year
                else:
                    end_month = month + interval_months - 1
                    end_year_temp = year

                last_day = (
                    datetime(end_year_temp, end_month, 1).replace(day=28)
                    + pd.Timedelta(days=4)
                ).replace(day=1) - pd.Timedelta(days=1)
                end_date = last_day.strftime("%Y-%m-%d")
                month_ranges.append((start_date, end_date))

        for start_date, end_date in month_ranges:
            print(f"\n📅 Processing: {start_date} to {end_date}")
            self.acquire_dem(
                roi=roi,
                start_date=start_date,
                end_date=end_date,
                scale=scale,
                crs=crs,
                include_wbm=include_wbm,
            )