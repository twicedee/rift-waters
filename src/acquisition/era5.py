import ee
import os
import pandas as pd
from pathlib import Path


class ERA5Acquisition:
    def __init__(self, region, output_dir="dataset"):
        self.base_dir = output_dir
        self.region = region
        
        
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

            csv_path = metadata_dir / f"{self.region}_dem.csv"

            # One row per image_id, carrying BOTH band paths — avoids the DEM row
            # getting evicted by a later WBM save for the same image_id.
            df_entry = pd.DataFrame(
                [
                    {
                        
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

            print(f"  📝 Metadata saved to {csv_path}")


    def acquire_era5(
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
        )
        
        
        
        
        # Save metadata
        output_dir = (
            f"{self.base_dir}/{self.region}/raw/era5/"
        )
        os.makedirs(output_dir, exist_ok=True)

        return era5
