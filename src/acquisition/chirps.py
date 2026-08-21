import ee
import geemap
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
import numpy as np
from src.utils.export_utils import export_image_with_fallback


class CHIRPSAcquisition:
    def __init__(self, region):
        self.region = region
        self.base_dir = Path(f"./dataset/{region}")

    def _ensure_directories(self):
        dir_path = self.base_dir / "raw" / "chirps"
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            return dir_path
        except Exception as e:
            print(f"Error creating directory {dir_path}: {e}")
            return None

    def _save_metadata(self, metadata: dict):
        metadata_dir = self.base_dir / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)

        json_path = metadata_dir / f"{self.region}_chirps.json"

        json_entry = {
            "source": metadata.get("source", "UCSB-CHG/CHIRPS/DAILY"),
            "start_date": metadata.get("start_date", ""),
            "end_date": metadata.get("end_date", ""),
            "scale_m": metadata.get("scale", 5000),
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

        csv_path = metadata_dir / f"{self.region}_chirps.csv"

        # One row per image_id, carrying BOTH band paths — avoids the DEM row
        # getting evicted by a later WBM save for the same image_id.
        df_entry = pd.DataFrame(
            [
                {
                    "image_id": metadata.get("image_id", ""),
                    "chirps_path": metadata.get("chirps_path", ""),
                }
            ]
        )

        if csv_path.exists():
            df_existing = pd.read_csv(csv_path)
            df_combined = pd.concat([df_existing, df_entry], ignore_index=True)
            df_combined.to_csv(csv_path, index=False)
        else:
            df_entry.to_csv(csv_path, index=False)
            
    def acquire_chirps(self, start_date: str, end_date: str, scale: int = 5000, crs: str = "EPSG:4326", save_to_drive: bool = False) -> dict:
        """
        Acquire CHIRPS precipitation data for the specified region and date range.
        """
        chirps_dir = self._ensure_directories()
        if chirps_dir is None:
            raise Exception("Failed to create directories for CHIRPS data.")

        roi = ee.Geometry.Polygon(self.region)  # Assuming self.region is a list of coordinates

        chirps_collection = (
            ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
            .filterDate(start_date, end_date)
            .filterBounds(roi)
            .mean()  # Get mean precipitation over the period
        )

        image_id = f"chirps_{start_date}_{end_date}"
        output_path = chirps_dir / f"{image_id}.tif"

        export_image_with_fallback(
            image=chirps_collection,
            local_path=output_path,
            scale=scale,
            region=roi,
            crs=crs,
            drive_folder="GEE_exports",
            drive_filename=f"{self.region}_chirps.tif" if save_to_drive else None,
        )

        self._save_metadata(
            {
                "source": "UCSB-CHG/CHIRPS/DAILY",
                "start_date": start_date,
                "end_date": end_date,
                "scale": scale,
                "crs": crs,
                "image_id": image_id,
                "chirps_path": str(output_path),
            }
        )

        return {
            "image_id": image_id,
            "chirps_path": str(output_path),
        }   
        
    def batch_acquire_chirps(self, date_ranges: list, scale: int = 5000, crs: str = "EPSG:4326", save_to_drive: bool = False) -> list:
        """
        Acquire CHIRPS precipitation data for multiple date ranges.
        """
        results = []
        for start_date, end_date in date_ranges:
            result = self.acquire_chirps(start_date, end_date, scale, crs, save_to_drive)
            results.append(result)
        return results