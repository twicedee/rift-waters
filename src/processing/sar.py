import json
import pandas as pd
import numpy as np
import rasterio
import rasterio.features
import geopandas as gpd
import os
from pathlib import Path
from scipy import ndimage
from datetime import datetime
from sklearn.cluster import KMeans
from skimage import filters, morphology, measure
from shapely.geometry import shape


class SARProcessor:
    def __init__(self, region, image_id):
        self.region = region
        self.image_id = image_id

    def _save_results(self, results: dict):
        metadata_dir = f"dataset/{self.region}/metadata"
        os.makedirs(metadata_dir, exist_ok=True)
        
        json_path = Path(metadata_dir) / f"{self.region}_sar.json"
        
        json_entry = {
            "image_id": self.image_id,
            "processing_method": results.get("method", ""),
            "threshold_value": results.get("threshold_value", ""),
            "total_pixels": results.get("total_pixels", ""),
            "boundary_perimeter_m": results.get("boundary_perimeter_m", ""),
            "boundary_compactness": results.get("boundary_compactness", ""),
            "processed_at": datetime.now().isoformat(),
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

        csv_path = Path(metadata_dir) / f"{self.region}_sar.csv"
        df_entry = pd.DataFrame(
            [
                {
                    "image_id": self.image_id,
                    "total_pixels": results.get("total_pixels", ""),
                    "water_pixels": results.get("water_pixels", ""),
                    "water_area_m2": results.get("water_area_m2", ""),
                    "boundary_area_m2": results.get("boundary_area_m2", ""),
                    "boundary_perimeter_m": results.get("boundary_perimeter_m", ""),
                    "boundary_compactness": results.get("boundary_compactness", ""),
                    "method": results.get("method", ""),
                    "processed_at": datetime.now().isoformat(),
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

        print(f"  📝 Metadata saved to {json_path} and {csv_path}")

    def load_sentinel1_image(self, image_path):
        try:
            with rasterio.open(image_path) as src:
                image = src.read(1)
                profile = src.profile
                transform = src.transform
                crs = src.crs

            total_pixels = image.size
            return image, profile, transform, crs, total_pixels
            
        except Exception as e:
            print(f"❌ Error loading Sentinel-1 image from {image_path}: {e}")
            raise

    def process_sentinel1_sar(
        self,
        image_path,
        method="adaptive_threshold",
        threshold_value=15,
        min_area_m2=900,
        simplify_tolerance=10,
        save_shapefile=False,
    ):
        image, profile, transform, crs, total_pixels = self.load_sentinel1_image(image_path)
        
        mean = ndimage.uniform_filter(image, size=7)
        mean_sq = ndimage.uniform_filter(image**2, size=7)
        variance = mean_sq - mean**2
        overall_variance = ndimage.variance(image)
        
        weights = variance / (variance + overall_variance)
        filtered_image = mean + weights * (image - mean)

        if method == "threshold":
            water_mask = filtered_image < threshold_value

        elif method == "adaptive_threshold":
            threshold = filters.threshold_otsu(filtered_image)
            water_mask = filtered_image < threshold

        elif method == "local_threshold":
            threshold = filters.threshold_local(filtered_image, block_size=51, offset=0)
            water_mask = filtered_image < threshold

        elif method == "kmeans":
            pixels = filtered_image.reshape(-1, 1)
            kmeans = KMeans(n_clusters=2, random_state=0).fit(pixels)
            labels = kmeans.labels_.reshape(filtered_image.shape)
            cluster_means = [filtered_image[labels == i].mean() for i in range(2)]
            water_cluster = np.argmin(cluster_means)
            water_mask = labels == water_cluster

        elif method == "minimum_threshold":
            threshold = filters.threshold_minimum(filtered_image)
            water_mask = filtered_image < threshold

        else:
            raise ValueError(f"Unknown method: {method}")

        original_count = np.sum(water_mask)
        water_mask = morphology.remove_small_objects(water_mask, min_size=100)
        water_mask = morphology.closing(water_mask, morphology.disk(3))
        water_mask = morphology.opening(water_mask, morphology.disk(2))
        cleaned_count = np.sum(water_mask)

        water_pixels = np.sum(water_mask)
        pixel_area = 100
        water_area_m2 = water_pixels * pixel_area

        output_dir = f"dataset/{self.region}/processed/sar_water_mask/"
        os.makedirs(output_dir, exist_ok=True)
        output_path = Path(output_dir) / f"{self.region}_{self.image_id}.tif"

        out_profile = profile.copy()
        out_profile.update({"dtype": "uint8", "compress": "lzw", "nodata": 0})

        with rasterio.open(output_path, "w", **out_profile) as dst:
            dst.write(water_mask.astype("uint8"), 1)

        boundary_gdf = self._extract_lake_boundary(
            water_mask,
            transform,
            crs,
            min_area_m2=min_area_m2,
            simplify_tolerance=simplify_tolerance,
            save_shapefile=save_shapefile,
        )

        if boundary_gdf is not None:
            boundary_area_m2 = boundary_gdf["area_m2"].sum()
            boundary_perimeter_m = boundary_gdf["perimeter_m"].sum()
            boundary_compactness = boundary_gdf["compactness"].mean()
        else:
            boundary_area_m2 = ""
            boundary_perimeter_m = ""
            boundary_compactness = ""

        self._save_results(
            {
                "total_pixels": total_pixels,
                "water_pixels": water_pixels,
                "water_area_m2": water_area_m2,
                "boundary_area_m2": boundary_area_m2,
                "boundary_perimeter_m": boundary_perimeter_m,
                "boundary_compactness": boundary_compactness,
                "method": method,
                "threshold_value": threshold_value,
            }
        )

        return boundary_gdf

    def _extract_lake_boundary(
        self,
        water_mask,
        transform,
        crs,
        min_area_m2=5000,
        simplify_tolerance=10,
        save_shapefile=False,
    ):
        shapes_gen = rasterio.features.shapes(
            water_mask.astype("uint8"), transform=transform
        )
        geometries = [shape(geom) for geom, value in shapes_gen if value == 1]

        if not geometries:
            print(f"  ⚠️ No water polygons found for {self.region}_{self.image_id}")
            return None

        gdf = gpd.GeoDataFrame({"geometry": geometries}, crs=crs)

        if gdf.crs is not None and gdf.crs.is_geographic:
            gdf = gdf.to_crs(gdf.estimate_utm_crs())

        gdf["area_m2"] = gdf.geometry.area

        original_count = len(gdf)
        gdf = gdf[gdf["area_m2"] >= min_area_m2].reset_index(drop=True)

        if gdf.empty:
            print(f"  ⚠️ All polygons filtered out by min_area_m2={min_area_m2}")
            return None

        gdf["geometry"] = gdf.geometry.simplify(simplify_tolerance)

        gdf["area_m2"] = gdf.geometry.area
        gdf["perimeter_m"] = gdf.geometry.length
        gdf["compactness"] = (4 * np.pi * gdf["area_m2"]) / (gdf["perimeter_m"] ** 2)
        gdf["compactness"] = gdf["compactness"].clip(0, 1)

        if save_shapefile:
            output_dir = f"dataset/{self.region}/processed/boundaries/{self.region}_{self.image_id}"
            os.makedirs(output_dir, exist_ok=True)
            shp_path = Path(output_dir) / f"{self.region}_{self.image_id}.shp"
            gdf.to_file(shp_path)

        return gdf

    def process_sar_batch(self, image_paths, save_shapefile=False):
        if isinstance(image_paths, dict):
            for image_id, path in image_paths.items():
                self.image_id = image_id
                try:
                    self.process_sentinel1_sar(
                        path, 
                        save_shapefile=save_shapefile
                    )
                except Exception as e:
                    print(f"❌ Failed to process {image_id}: {e}")
        else:
            for path in image_paths:
                try:
                    self.process_sentinel1_sar(
                        path, 
                        save_shapefile=save_shapefile
                    )
                except Exception as e:
                    print(f"❌ Failed to process {path}: {e}")