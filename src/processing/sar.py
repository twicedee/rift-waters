import os
import json
import pandas as pd
import numpy as np
import rasterio
import rasterio.features
import geopandas as gpd
from shapely.geometry import box
from pathlib import Path
from scipy import ndimage
from datetime import datetime
from sklearn.cluster import KMeans
from skimage import filters, morphology, measure
from shapely.geometry import shape
from rasterio.warp import calculate_default_transform, reproject, Resampling



class SARProcessor:
    def __init__(self, region, image_id):
        self.region = region
        self.image_id = image_id

    def _save_results(self, results: dict):
        metadata_dir = f"dataset/{self.region}/metadata"
        os.makedirs(metadata_dir, exist_ok=True)
        
        

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

        print(f"  📝 Metadata saved to  {csv_path}")
        
    
    def load_sentinel1_image(self, image_path):
        try:
            with rasterio.open(image_path) as src:
                image = src.read(1)
                profile = src.profile
                transform = src.transform
                crs = src.crs
                bounds = src.bounds
                width = src.width
                height = src.height

            if crs is None:
                raise ValueError(f"No CRS found for {self.region}_{self.image_id}")

            if crs.is_projected:
                # print("  ✅ CRS is projected, no reprojection needed.")
                total_pixels = image.size
                return image, profile, transform, crs, total_pixels

            # print("Projecting to UTM (in memory)...")
            bounds_gdf = gpd.GeoDataFrame(geometry=[box(*bounds)], crs=crs)
            dst_crs = bounds_gdf.estimate_utm_crs()
            # print(f"Estimated UTM CRS: {dst_crs}")

            dst_transform, dst_width, dst_height = calculate_default_transform(
                crs, dst_crs, width, height, *bounds
            )

            reprojected_image = np.empty((dst_height, dst_width), dtype=image.dtype)

            reproject(
                source=image,
                destination=reprojected_image,
                src_transform=transform,
                src_crs=crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                resampling=Resampling.bilinear,
            )

            profile = profile.copy()
            profile.update({
                "crs": dst_crs,
                "transform": dst_transform,
                "width": dst_width,
                "height": dst_height,
            })

            # print(f"New pixel width: {dst_transform.a} m, height: {dst_transform.e} m")
            # print(f"New pixel area: {abs(dst_transform.a * dst_transform.e)} m²")

            total_pixels = reprojected_image.size
            return reprojected_image, profile, dst_transform, dst_crs, total_pixels

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
        # print(f"  📝 Total pixels in image: {total_pixels}")
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
        water_mask = morphology.remove_small_objects(water_mask, max_size=10000)
        water_mask = morphology.closing(water_mask, morphology.disk(3))
        water_mask = morphology.opening(water_mask, morphology.disk(2))
        cleaned_count = np.sum(water_mask)

        water_pixels = np.sum(water_mask)

        

        pixel_area = abs(transform.a * transform.e)  # derived from actual transform, in m²
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
        min_area_m2=20000,
        simplify_tolerance=10,
        save_shapefile=False,
    ):
        shapes_gen = rasterio.features.shapes(
            water_mask.astype("uint8"), transform=transform
        )
        geometries = [shape(geom) for geom, value in shapes_gen if value == 1]

        if not geometries:
            # print(f"  ⚠️ No water polygons found for {self.region}_{self.image_id}")
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
    
    def flag_outliers(self, perimeter_ratio_threshold=2.0):
        metadata_dir = f"dataset/{self.region}/metadata"
        csv_path = Path(metadata_dir) / f"{self.region}_sar.csv"

        if not csv_path.exists():
            print(f"  ⚠️ No metadata CSV found at {csv_path}")
            return None

        df = pd.read_csv(csv_path)
        median_perimeter = df["boundary_perimeter_m"].median()
        df["perimeter_ratio"] = df["boundary_perimeter_m"] / median_perimeter
        df["is_outlier"] = df["perimeter_ratio"] > perimeter_ratio_threshold

        df.to_csv(csv_path, index=False)

        n_outliers = df["is_outlier"].sum()
        print(f"  📝 Flagged {n_outliers} outlier(s) out of {len(df)} in {csv_path}")

        return df
    
    
    
    

    def process_sar_batch(self, image_path, save_shapefile=False):
        try:
            self.process_sentinel1_sar(
                image_path, 
                save_shapefile=save_shapefile
            )
        except Exception as e:
            print(f"❌ Failed to process {image_path}: {e}")
            