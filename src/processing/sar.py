import json
import profile
import pandas as pd
import numpy as np
import rasterio
import os
from pathlib import Path
from scipy import ndimage
from datetime import datetime
from rasterio.plot import show
from sklearn.cluster import KMeans
from skimage import filters, morphology, measure
from rasterio.transform import from_bounds



class SARProcessor:
    def __init__(self, image, image_id, region):
        self.image = image
        self.region = region
        self.image_id = image_id
        # self._save_results = self._save_results()

    ####Update to handle Sentinel-1 images in dB scale
    def _save_results(self, results: dict):
        metadata_dir = f"dataset/{self.region}/metadata"
        os.makedirs(metadata_dir, exist_ok=True)
        # Single JSON file for each satellite
        json_path = Path(metadata_dir )/ f"{self.region}_sar.json"

        # Prepare new entry
        json_entry = {
            "processing_method": results.get("method", ""),
            "threshold_value": results.get("threshold_value", ""),
            "total_pixels": results.get("total_pixels", ""),
        }
        print(f"Saving metadata to {json_path}...")
        # Read existing data or create new list
        if json_path.exists():
            with open(json_path, "r") as f:
                existing_data = json.load(f)
                # If it's a list, append; if it's a dict, convert to list
                if isinstance(existing_data, list):
                    existing_data.append(json_entry)
                else:
                    existing_data = [existing_data, json_entry]
        else:
            existing_data = [json_entry]

        # Write back to single JSON file
        with open(json_path, "w") as f:
            json.dump(existing_data, f, indent=2)
            
        print(f"  📝 Metadata saved to {json_path}")
        # Also update CSV similarly (if needed)
        csv_path = Path(metadata_dir) / f"{self.region}_sar.csv"
        df_entry = pd.DataFrame([{
            "image_id": self.image_id,
            "total_pixels": results.get("total_pixels", ""),
            "water_pixels": results.get("water_pixels", ""),
            "water_area_m2": results.get("water_area_m2", ""),
        }])
        print(f"Saving metadata to {csv_path}...")
        if csv_path.exists():
            existing_df = pd.read_csv(csv_path)
            updated_df = pd.concat([existing_df, df_entry], ignore_index=True)
            updated_df.to_csv(csv_path, index=False)
        else:
            df_entry.to_csv(csv_path, index=False)

        print(f"  📝 Metadata appended to {json_path}")

    def load_sentinel1_image(self, image):

        try:

            with rasterio.open(image) as src:
                image = src.read(1)
                profile = src.profile
                transform = src.transform
                crs = src.crs

            # Convert to decibels (dB) if image is in linear scale
            # Avoid log of zero or negative values
            # image_abs = np.abs(image)
            # image_abs[image_abs == 0] = 1e-10
            # image_db = 10 * np.log10(image)

            # print(f"Image shape: {image.shape}")
            # print(f"Image bounds: {bounds}")
            # print(f"CRS: {profile['crs']}")
            # print(image_db.min(), image_db.max())
            # print(image_abs)
            total_pixels = image.size

            return image, profile, transform, crs ,total_pixels
        except Exception as e:
            print(f"❌ Error loading Sentinel-1 image: {e}")

    def process_sentinel1_sar(
        self, image, method="threshold", threshold_value=10
    ):
        """
        Detect water using SAR backscatter properties

        Water typically has low backscatter (smooth surface) in SAR imagery
        """
        image, profile, transform, crs, total_pixels = self.load_sentinel1_image(image)
        # Apply speckle filtering
        mean = ndimage.uniform_filter(image, size=7)
        mean_sq = ndimage.uniform_filter(image**2, size=7)
        variance = mean_sq - mean**2
        overall_variance = ndimage.variance(image)

        weights = variance / (variance + overall_variance)
        filtered_image = mean + weights * (image - mean)

        if method == "threshold":
            # Simple thresholding (water has lower backscatter)
            water_mask = filtered_image < threshold_value

        elif method == "adaptive_threshold":
            # Otsu's method for automatic threshold selection
            threshold = filters.threshold_otsu(filtered_image)
            water_mask = filtered_image < threshold

        elif method == "local_threshold":
            # Local thresholding for heterogeneous areas
            threshold = filters.threshold_local(filtered_image, block_size=51, offset=0)
            water_mask = filtered_image < threshold

        elif method == "kmeans":
            # Reshape for clustering
            pixels = filtered_image.reshape(-1, 1)
            kmeans = KMeans(n_clusters=2, random_state=0).fit(pixels)
            labels = kmeans.labels_.reshape(filtered_image.shape)

            # Assume water is the cluster with lower mean backscatter
            cluster_means = [filtered_image[labels == i].mean() for i in range(2)]
            water_cluster = np.argmin(cluster_means)
            water_mask = labels == water_cluster

        elif method == "minimum_threshold":
            # Minimum error thresholding (Kittler-Illingworth)
            threshold = filters.threshold_minimum(filtered_image)
            water_mask = filtered_image < threshold
            print(f"Using minimum error threshold: {threshold:.2f} dB")

        # Apply morphological operations to clean up the mask
        original_count = np.sum(water_mask)
        water_mask = morphology.remove_small_objects(water_mask, min_size=100)
        water_mask = morphology.binary_closing(water_mask, morphology.disk(3))
        water_mask = morphology.binary_opening(water_mask, morphology.disk(2))
        cleaned_count = np.sum(water_mask)

        print(f"Mask cleaning: {original_count} -> {cleaned_count} water pixels")




        """
        Calculate water surface area in square meters and square kilometers
        """
        

        water_pixels = np.sum(water_mask)

        pixel_area = 100  # Assuming 10m x 10m pixels for Sentinel-1
        water_area_m2 = water_pixels * pixel_area
        
        #save watermask and metadata
        
        
        
        output_dir= f"dataset/{self.region}/processed/sar_water_mask/"
        os.makedirs(output_dir, exist_ok=True)
        output_path = Path(output_dir )/ f"{self.image_id}.tif"
        
        # if transform is None:
        #     transform = from_bounds(
        #         0, 0, water_mask.shape[1], water_mask.shape[0], water_mask.shape[1], water_mask.shape[0]
        #     )

        # Save as GeoTIFF
        out_profile = profile.copy()
        out_profile.update({
        'dtype': 'uint8',
        'compress': 'lzw',
        'nodata': 0
        })
    
        with rasterio.open(output_path, 'w', **out_profile) as dst:
            dst.write(water_mask.astype('uint8'), 1)
        

        self._save_results(
            {
                "total_pixels": total_pixels,
                "water_pixels": water_pixels,
                "water_area_m2": water_area_m2,
                "method": method,
                "threshold_value": threshold_value,
                "profile": profile,
                "transform": transform,
            }
        )

    
    

    def batch_process_sentinel1(self, images, method="threshold", threshold_value=-15):
        for image in images:
            self.process_sentinel1_sar(
                image, method, threshold_value
            )
            
    
