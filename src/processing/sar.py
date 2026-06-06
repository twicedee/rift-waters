import numpy as np
import rasterio
from rasterio.plot import show
from scipy import ndimage
from skimage import filters, morphology, measure
import geopandas as gpd
from shapely.geometry import Polygon
import warnings
from sklearn.cluster import KMeans

warnings.filterwarnings("ignore")


class SARProcessor:
    def __init__(self, image):
        self.image = image

    ####Update to handle Sentinel-1 images in dB scale
    def load_sentinel1_image(image):

        with rasterio.open(image) as src:
            image = src.read(1)
            profile = src.profile
            transform = src.transform
            bounds = src.bounds

        # Convert to decibels (dB) if image is in linear scale
        # Avoid log of zero or negative values
        # image_abs = np.abs(image)
        # image_abs[image_abs == 0] = 1e-10
        # image_db = 10 * np.log10(image)

        print(f"Image shape: {image.shape}")
        print(f"Image bounds: {bounds}")
        print(f"CRS: {profile['crs']}")
        # print(image_db.min(), image_db.max())
        # print(image_abs)

        return image, profile, transform, bounds

    def process_sentinel1_sar(image, method="threshold", threshold_value=10):
        """
        Detect water using SAR backscatter properties

        Water typically has low backscatter (smooth surface) in SAR imagery
        """

        # Apply speckle filtering
        def apply_lee_filter(image, window_size=7):

            mean = ndimage.uniform_filter(image, size=window_size)
            mean_sq = ndimage.uniform_filter(image**2, size=window_size)
            variance = mean_sq - mean**2

            overall_variance = ndimage.variance(image)

            weights = variance / (variance + overall_variance)
            filtered = mean + weights * (image - mean)

            return filtered

        filtered_image = apply_lee_filter(image)

        if method == "threshold":
            # Simple thresholding (water has lower backscatter)
            water_mask = filtered_image < threshold_value
            print(f"Using fixed threshold: {threshold_value} dB")

        elif method == "adaptive_threshold":
            # Otsu's method for automatic threshold selection
            threshold = filters.threshold_otsu(filtered_image)
            water_mask = filtered_image < threshold
            print(f"Using Otsu's threshold: {threshold:.2f} dB")

        elif method == "local_threshold":
            # Local thresholding for heterogeneous areas
            threshold = filters.threshold_local(filtered_image, block_size=51, offset=0)
            water_mask = filtered_image < threshold
            print("Using local adaptive thresholding")
        elif method == "kmeans":
            

            # Reshape for clustering
            pixels = filtered_image.reshape(-1, 1)
            kmeans = KMeans(n_clusters=2, random_state=0).fit(pixels)
            labels = kmeans.labels_.reshape(filtered_image.shape)
            # Assume water is the cluster with lower mean backscatter
            cluster_means = [filtered_image[labels == i].mean() for i in range(2)]
            water_cluster = np.argmin(cluster_means)
            water_mask = labels == water_cluster
            print("Using K-means clustering for thresholding")
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

        return water_mask

    def calculate_water_area(water_mask, transform, pixel_area=100):
        """
        Calculate water surface area in square meters and square kilometers
        """
        water_pixels = np.sum(water_mask)

        if pixel_area is None:
            # Calculate pixel area from transform (assuming UTM projection)
            pixel_width = abs(transform[0])
            pixel_height = abs(transform[4])
            pixel_area = pixel_width * pixel_height
            print(f"Pixel size: {pixel_width:.2f}m x {pixel_height:.2f}m")
            print(f"Pixel area: {pixel_area:.2f} m²")

        water_area_m2 = water_pixels * pixel_area
        water_area_km2 = water_area_m2 / 1_000_000

        return water_area_m2, water_area_km2
    
    def process_sentinel1_sar(image, method="threshold", threshold_value=10):
        water_mask = detect_water_sar(image, method, threshold_value)
        return water_mask
    
    def _save_results(self, results, file_path):
        pass
