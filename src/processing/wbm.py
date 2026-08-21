import os
import rasterio
import numpy as np
import pandas as pd
from pathlib import Path


class WBMProcessor:
    def __init__(self, region, image_id, wbm_path=None):
        self.region = region
        self.image_id = image_id
        self.base_dir = Path(f"./dataset/{region}")
        self.wbm_path = wbm_path 

    def _save_results(self, results: dict):
        metadata_dir = f"dataset/{self.region}/metadata"
        os.makedirs(metadata_dir, exist_ok=True)

        csv_path = Path(metadata_dir) / f"{self.region}_wbm.csv"
        df_entry = pd.DataFrame(
            [
                {
                    "image_id": self.image_id,
                    "wbm_land_pct": results.get("wbm_land_pct", ""),
                    "wbm_ocean_pct": results.get("wbm_ocean_pct", ""),
                    "wbm_lake_pct": results.get("wbm_lake_pct", ""),
                    "wbm_river_pct": results.get("wbm_river_pct", ""),
                    "wbm_water_pct": results.get("wbm_water_pct", ""),
                }
            ]
        )

        if csv_path.exists():
            existing_df = pd.read_csv(csv_path)
            existing_df = existing_df[existing_df["image_id"] != self.image_id]
            updated_df = pd.concat([existing_df, df_entry], ignore_index=True)
            updated_df.to_csv(csv_path, index=False)
        else:
            df_entry.to_csv(csv_path, index=False)

        print(f"  📝 Metadata saved to {csv_path}")

    def load_wbm(self, wbm_path=None):
        try:
            with rasterio.open(wbm_path) as src:
                image = src.read(1)
                profile = src.profile
                transform = src.transform
                crs = src.crs

            total_pixels = image.size
            return image, profile, transform, crs, total_pixels

        except Exception as e:
            print(f"❌ Error loading WBM from {wbm_path}: {e}")
            raise

    # ------------------------------------------------------------------
    # WBM stats
    # ------------------------------------------------------------------

    def compute_wbm_stats(self, wbm_path=None):
        """
        Summarize the Water Body Mask band: 0=land, 1=ocean, 2=lake, 3=river.
        wbm_water_pct combines lake+river — the relevant "baseline water"
        signal for an inland AOI like Juja (ocean expected to be ~0 there).
        """
        wbm, _, _ = self.load_wbm(wbm_path)
        if wbm is None:
            return {}

        total = wbm.size
        if total == 0:
            return {}

        land_pct = float(np.sum(wbm == 0)) / total * 100
        ocean_pct = float(np.sum(wbm == 1)) / total * 100
        lake_pct = float(np.sum(wbm == 2)) / total * 100
        river_pct = float(np.sum(wbm == 3)) / total * 100

        results = {
            "wbm_land_pct": round(land_pct, 3),
            "wbm_ocean_pct": round(ocean_pct, 3),
            "wbm_lake_pct": round(lake_pct, 3),
            "wbm_river_pct": round(river_pct, 3),
            "wbm_water_pct": round(lake_pct + river_pct, 3),
        }
        self._save_results(results)
        return results


    def process_wbm_batch(self, wbm_path=None):

        try:
            self.compute_wbm_stats(wbm_path)

        except Exception as e:
            error_msg = f"Failed to process {self.image_id}: {str(e)}"
            print(f"❌ {error_msg}")
