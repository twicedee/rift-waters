import os
import json
import ee
import osmnx as ox
import geopandas as gpd
import pandas as pd
from pathlib import Path
from datetime import datetime
from shapely.geometry import Polygon


class RoadsAcquisition:
    def __init__(self, region):
        self.region = region
        self.base_dir = Path(f"./dataset/{region}")

    def _ensure_directories(self):
        dir_path = self.base_dir / "raw" / "roads"
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            return dir_path
        except Exception as e:
            print(f"Error creating directory {dir_path}: {e}")
            return None

    def _ee_geometry_to_polygon(self, roi: ee.Geometry) -> Polygon:
        """Convert an ee.Geometry ROI to a shapely Polygon for osmnx (lon/lat)."""
        coords = roi.getInfo()["coordinates"][0]
        return Polygon(coords)

    def _save_metadata(self, metadata: dict):
        metadata_dir = self.base_dir / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)

        json_path = metadata_dir / f"{self.region}_roads.json"
        json_entry = {
            "source": metadata.get("source", "OpenStreetMap (osmnx)"),
            "road_count": metadata.get("road_count", 0),
            "total_length_km": metadata.get("total_length_km", 0),
            "highway_types": metadata.get("highway_types", {}),
            "acquisition_time": datetime.now().strftime("%Y%m%d_%H%M%S"),
        }

        if json_path.exists():
            with open(json_path, "r") as f:
                existing_data = json.load(f)
                existing_data = existing_data if isinstance(existing_data, list) else [existing_data]
                existing_data.append(json_entry)
        else:
            existing_data = [json_entry]

        with open(json_path, "w") as f:
            json.dump(existing_data, f, indent=2)

        csv_path = metadata_dir / f"{self.region}_roads.csv"
        df_entry = pd.DataFrame(
            [
                {
                    "region": self.region,
                    "roads_path": metadata.get("roads_path", ""),
                    "road_count": metadata.get("road_count", 0),
                    "total_length_km": metadata.get("total_length_km", 0),
                }
            ]
        )

        if csv_path.exists():
            existing_df = pd.read_csv(csv_path)
            existing_df = existing_df[existing_df["region"] != self.region]
            updated_df = pd.concat([existing_df, df_entry], ignore_index=True)
            updated_df.to_csv(csv_path, index=False)
        else:
            df_entry.to_csv(csv_path, index=False)

        print(f"  📝 Metadata saved to {json_path} and {csv_path}")

    def acquire_roads(self, roi: ee.Geometry, utm_crs: str = "EPSG:32637"):
        """
        Acquire road network for the ROI from OpenStreetMap via osmnx.

        Args:
            roi: ee.Geometry polygon (same ROI used elsewhere in the pipeline)
            utm_crs: UTM zone for length calcs — match config.py's per-lake
                     convention (Bogoria=EPSG:32637, Naivasha=EPSG:32636)
        """
        roads_dir = self._ensure_directories()
        if roads_dir is None:
            print("Error: Could not create roads directory")
            return None

        try:
            polygon = self._ee_geometry_to_polygon(roi)

            print(f"  ⬇️ Downloading OSM roads for {self.region}...")
            roads_gdf = ox.features_from_polygon(polygon, tags={"highway": True})
            roads_gdf = roads_gdf[roads_gdf.geometry.type.isin(["LineString", "MultiLineString"])]

            if roads_gdf.empty:
                print(f"  ⚠️ No roads found for {self.region}")
                return None

            keep_cols = [c for c in ["highway", "name", "surface", "geometry"] if c in roads_gdf.columns]
            roads_gdf = roads_gdf[keep_cols].reset_index(drop=True)

            # OSM tag columns can contain lists — stringify for GPKG compatibility
            for col in roads_gdf.columns:
                if col != "geometry":
                    roads_gdf[col] = roads_gdf[col].apply(
                        lambda v: ",".join(v) if isinstance(v, list) else v
                    )

            # Geographic CRS gives meaningless lengths — same rule as sar.py's UTM guard
            roads_utm = roads_gdf.to_crs(utm_crs)
            total_length_km = roads_utm.geometry.length.sum() / 1000

            output_path = roads_dir / f"{self.region}_roads.gpkg"
            roads_gdf.to_file(output_path, driver="GPKG")

            highway_types = (
                roads_gdf["highway"].value_counts().to_dict() if "highway" in roads_gdf.columns else {}
            )

            self._save_metadata(
                {
                    "source": "OpenStreetMap (osmnx)",
                    "roads_path": str(output_path),
                    "road_count": len(roads_gdf),
                    "total_length_km": round(total_length_km, 2),
                    "highway_types": highway_types,
                }
            )

            print(f"  ✅ {len(roads_gdf)} road segments saved to {output_path}")
            return str(output_path)

        except Exception as e:
            print(f"❌ Error acquiring roads data: {e}")
            return None