# landcover_aquisition.py

import ee
import geemap
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from src.utils.export_utils import export_image_with_fallback

[
     'trees', 'grass', 'flooded_vegetation', 'crops',
    'shrub_and_scrub', 'built', 'bare']

class LandCoverAcquisition:
    def __init__(self, region):
        self.region = region
        self.base_dir = Path(f"./dataset/{region}")

    def _ensure_directories(self):
        dir_path = self.base_dir / "raw" / "landcover"
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            return dir_path
        except Exception as e:
            print(f"Error creating directory {dir_path}: {e}")
            return None

    def _save_metadata(self, metadata: dict):
        metadata_dir = self.base_dir / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)

        json_path = metadata_dir / f"{self.region}_landcover.json"

        json_entry = {
            "source": metadata.get("source", "GOOGLE/DYNAMICWORLD/V1"),
            "start_date": metadata.get("start_date", ""),
            "end_date": metadata.get("end_date", ""),
            "scale_m": metadata.get("scale", 10),
            "crs": metadata.get("crs", "EPSG:4326"),
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

        csv_path = metadata_dir / f"{self.region}_landcover.csv"

        # One row per image_id, carrying paths for BOTH the probability
        # stack and the label band — same pattern as the DEM/WBM/slope row.
        df_entry = pd.DataFrame(
            [
                {
                    "image_id": metadata.get("image_id", ""),
                    "probs_path": metadata.get("probs_path", ""),
                    "label_path": metadata.get("label_path", ""),
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

    def acquire_landcover(
        self,
        roi: ee.Geometry,
        start_date: str,
        end_date: str,
        scale: int = 10,
        crs: str = "EPSG:4326",
        save_to_drive: bool = False,
    ) -> dict:

        landcover_dir = self._ensure_directories()
        if landcover_dir is None:
            print("Error: Could not create landcover directory")
            return None

        try:
            prob_bands = [
                "trees",
                "grass",
                "flooded_vegetation",
                "crops",
                "shrub_and_scrub",
                "built",
                "bare",
            ]

            dw = (
                ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
                .filterBounds(roi)
                .filterDate(start_date, end_date)
            )

            # Mean composite of class probabilities over the date range —
            # smooths out single-scene noise/cloud gaps, same rationale as
            # the SAR speckle filtering step.
            probs_image = dw.select(prob_bands).mean().clip(roi)
            label_image = dw.select("label").mode().clip(roi).rename("label")

            image_id = int(end_date.replace("-", ""))

            def save_image(image, output_path=None, band=None, save_to_drive=False):
                export_image_with_fallback(
                    image,
                    local_path=output_path,
                    scale=scale,
                    region=roi,
                    drive_folder="GEE_exports",
                    drive_filename=f"{self.region}_{image_id}_{band}.tif",
                )
                print(f"  ✅ {band} saved to {output_path}")

            print(f"  ⬇️ Downloading Dynamic World land cover for {self.region}...")

            # if crs == "EPSG:4326":
            #     print("  ⚠️ WARNING: land cover is in geographic CRS (EPSG:4326)")
            #     print("     Reproject to UTM before aligning with SAR/DEM rasters")

            probs_output_path = landcover_dir / f"{self.region}_{image_id}_probs.tif"
            label_output_path = landcover_dir / f"{self.region}_{image_id}_label.tif"

            save_image(
                probs_image, probs_output_path, "LandCoverProbs",
                save_to_drive=save_to_drive,
            )
            # save_image(
            #     label_image, label_output_path, "LandCoverLabel",
            #     save_to_drive=save_to_drive,
            # )

            self._save_metadata(
                {
                    "source": "GOOGLE/DYNAMICWORLD/V1",
                    "image_id": str(image_id),
                    "probs_path": str(probs_output_path),
                    "label_path": str(label_output_path),
                    "start_date": start_date,
                    "end_date": end_date,
                    "scale": scale,
                    "crs": crs,
                }
            )

            return {
                "probs_path": str(probs_output_path),
                "label_path": str(label_output_path),
            }

        except Exception as e:
            print(f"❌ Error acquiring land cover data: {e}")
            return None

    def batch_acquisition(
        self,
        roi: ee.Geometry,
        start_year: int,
        end_year: int,
        scale: int = 10,
        crs: str = "EPSG:4326",
        interval_months: int = 1,
        save_to_drive: bool = False,
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
            self.acquire_landcover(
                roi=roi,
                start_date=start_date,
                end_date=end_date,
                scale=scale,
                crs=crs,
                save_to_drive=save_to_drive,
            )