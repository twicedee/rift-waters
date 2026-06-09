import os
import json
import geemap
import rasterio
import numpy as np
from pathlib import Path
from datetime import datetime
import matplotlib.pyplot as plt
from rasterio.transform import from_bounds


class CalculateIndices:
    def __init__(self, image, region, image_id=None, index_band=None):
        """
        Initialize the indices calculator

        Args:
            image: Either file path (string) or ee.Image object
            region: The region for which to calculate indices
            image_id: Optional ID for the image
            index_band: Optional band name for the index
        """
            
        self.image = image
        self.index_band = index_band
        self.image_id = image_id
        self.region = region
        # Determine if local file or Earth Engine object
        self.is_local = isinstance(image, str)

    def calculate_index_from_local(self, image_path, index_name):
        """Calculate index from local GeoTIFF file"""
        with rasterio.open(image_path) as src:
            # Read bands (adjust band indices based on your file)
            # Typical order: Band1=Red, Band2=Green, Band3=NIR, Band4=SWIR1
            n_bands = src.count

            if n_bands < 4:
                raise ValueError(f"Need at least 4 bands, got {n_bands}")

            red = src.read(3).astype(float)
            green = src.read(2).astype(float)
            nir = src.read(4).astype(float)
            swir1 = src.read(5).astype(float)

            # Get transform and CRS for saving
            transform = src.transform
            crs = src.crs

            # Avoid division by zero
            epsilon = 1e-10

            if index_name == "ndwi":
                index = (green - nir) / (green + nir + epsilon)
            elif index_name == "mndwi":
                index = (green - swir1) / (green + swir1 + epsilon)
            elif index_name == "ndvi":
                index = (nir - red) / (nir + red + epsilon)
            elif index_name == "aweish":
                index = (green - swir1) / (green + swir1 + 0.5 * nir + epsilon)
            elif index_name == "awei":
                index = 4 * (green - swir1) - (0.25 * nir + 2.75 * swir1)
            else:
                raise ValueError(f"Unknown index: {index_name}")

            return index, transform, crs

    def calculate_ndwi(self):
        """Calculate NDWI (Normalized Difference Water Index)"""
        if self.is_local:
            index, transform, crs = self.calculate_index_from_local(self.image, "ndwi")
            return index
        else:
            ndwi = self.image.normalizedDifference(["Green", "NIR"]).rename("NDWI")
            return self.image.addBands(ndwi)

    def calculate_mndwi(self):
        """Calculate MNDWI (Modified NDWI)"""
        if self.is_local:
            index, transform, crs = self.calculate_index_from_local(self.image, "mndwi")
            return index
        else:
            mndwi = self.image.normalizedDifference(["Green", "SWIR1"]).rename("MNDWI")
            return self.image.addBands(mndwi)

    def calculate_ndvi(self):
        """Calculate NDVI (Normalized Difference Vegetation Index)"""
        if self.is_local:
            index, transform, crs = self.calculate_index_from_local(self.image, "ndvi")
            return index
        else:
            ndvi = self.image.normalizedDifference(["NIR", "Red"]).rename("NDVI")
            return self.image.addBands(ndvi)

    def calculate_aweish(self):
        """Calculate AWEIsh (Automated Water Extraction Index with shadow)"""
        if self.is_local:
            index, transform, crs = self.calculate_index_from_local(
                self.image, "aweish"
            )
            return index
        else:
            aweish = self.image.expression(
                "(Green - SWIR1) / (Green + SWIR1 + 0.5 * NIR)",
                {
                    "Green": self.image.select("Green"),
                    "SWIR1": self.image.select("SWIR1"),
                    "NIR": self.image.select("NIR"),
                },
            ).rename("AWEISH")
            return self.image.addBands(aweish)

    def calculate_awei(self):
        """Calculate AWEI (Automated Water Extraction Index)"""
        if self.is_local:
            index, transform, crs = self.calculate_index_from_local(self.image, "awei")
            return index
        else:
            awei = self.image.expression(
                "4 * (Green - SWIR1) - (0.25 * NIR + 2.75 * SWIR1)",
                {
                    "Green": self.image.select("Green"),
                    "SWIR1": self.image.select("SWIR1"),
                    "NIR": self.image.select("NIR"),
                },
            ).rename("AWEI")
            return self.image.addBands(awei)

    def calculate_all_indices(self):
        """Calculate all indices and return image with all bands"""
        image_with_indices = self.calculate_ndwi()
        image_with_indices = self.calculate_mndwi()
        image_with_indices = self.calculate_ndvi()
        image_with_indices = self.calculate_aweish()
        image_with_indices = self.calculate_awei()
        return image_with_indices

    def save_array_as_geotiff(
        self, array, output_path, transform=None, crs="EPSG:4326"
    ):
        """
        Save a numpy array as GeoTIFF

        Args:
            array: 2D numpy array
            output_path: Path to save the GeoTIFF
            transform: Affine transform (if None, creates simple one)
            crs: Coordinate reference system
        """
        # Convert to numpy array if needed
        if not isinstance(array, np.ndarray):
            try:
                array = np.array(array)
            except:
                raise TypeError(
                    f"Expected numpy array or array-like object, got {type(array)}"
                )

        # Ensure array is 2D
        if len(array.shape) != 2:
            raise ValueError(f"Expected 2D array, got {array.shape}")

        # Create simple transform if not provided (assumes pixel coordinates)
        if transform is None:
            transform = from_bounds(
                0, 0, array.shape[1], array.shape[0], array.shape[1], array.shape[0]
            )

        # Save as GeoTIFF
        with rasterio.open(
            output_path,
            "w",
            driver="GTiff",
            height=array.shape[0],
            width=array.shape[1],
            count=1,
            dtype=array.dtype,
            crs=crs,
            transform=transform,
            compress="lzw",
        ) as dst:
            dst.write(array, 1)

        print(f"  ✓ GeoTIFF saved: {output_path}")
        return output_path

    def save_indices_local(
        self, index_band
    ):
        """
        Save each index as both GeoTIFF image and numpy array locally

        Args:
            index_band: String specifying which index to calculate (e.g., "NDWI", "MNDWI")
            output_dir: Base directory for saving outputs
        """
        # Create output directory
        output_dir = f"./dataset/{self.region}/processed/indices/"
        os.makedirs(output_dir, exist_ok=True)

        # Handle index_band if it's passed as a list
        if isinstance(index_band, list):
            index_band = index_band[0] if index_band else "NDWI"

        print(f"Calculating {index_band}...")

        # Calculate the requested index
        if index_band.upper() == "NDWI":
            band_image = self.calculate_ndwi()
            index_name = "ndwi"
        elif index_band.upper() == "MNDWI":
            band_image = self.calculate_mndwi()
            index_name = "mndwi"
        elif index_band.upper() == "NDVI":
            band_image = self.calculate_ndvi()
            index_name = "ndvi"
        elif index_band.upper() == "AWEISH":
            band_image = self.calculate_aweish()
            index_name = "aweish"
        elif index_band.upper() == "AWEI":
            band_image = self.calculate_awei()
            index_name = "awei"
        else:
            raise ValueError(f"Unsupported index specified: {index_band}")

        # Create band-specific directory
        band_dir = Path(output_dir) / index_name.lower()
        os.makedirs(band_dir, exist_ok=True)

        # Get region and scale for Earth Engine export
        region = None
        scale = 100  # Adjust based on your image resolution

        if not self.is_local:
            region = self.image.geometry().bounds().getInfo()

        # 1. Save as GeoTIFF image
        tif_path = band_dir / f"{self.image_id}bar.tif"
        print(f"  Saving GeoTIFF: {tif_path}")

        if self.is_local:
            # For local files, we already have the array from calculation
            # But we need to recalculate to get transform and CRS
            array, transform, crs = self.calculate_index_from_local(
                self.image, index_name
            )
            self.save_array_as_geotiff(array, tif_path, transform, crs)
        else:
            # For Earth Engine images
            try:
                geemap.ee_export_image(
                    band_image,
                    filename=tif_path,
                    scale=scale,
                    region=region,
                    crs="EPSG:4326",
                )
                print(f"  ✓ GeoTIFF saved successfully")

                # 2. Save as numpy array for Earth Engine
                npy_path = os.path.join(band_dir, f"{index_name}_array.npy")
                print(f"  Saving numpy array: {npy_path}")

                # Convert to numpy array
                array = geemap.ee_to_numpy(band_image, region=region, scale=scale)

                # Save array
                np.save(npy_path, array)
                print(f"  ✓ Numpy array saved (shape: {array.shape})")

                # Save array metadata
                metadata = {
                    "band_name": index_band,
                    "shape": array.shape,
                    "dtype": str(array.dtype),
                    "scale": scale,
                    "crs": "EPSG:4326",
                    "min_value": float(np.nanmin(array)),
                    "max_value": float(np.nanmax(array)),
                    "mean_value": float(np.nanmean(array)),
                    "std_value": float(np.nanstd(array)),
                    "timestamp": datetime.now().isoformat(),
                }

                metadata_path = os.path.join(band_dir, f"{index_name}_metadata.json")
                with open(metadata_path, "w") as f:
                    json.dump(metadata, f, indent=2)
                print(f"  ✓ Metadata saved")

            except Exception as e:
                print(f"  ✗ Error saving: {e}")

        # Save summary metadata for this single index
        self._save_summary_metadata(output_dir, [index_band])

        print(f"\n✅ Index saved to: {band_dir}")

   

    def _save_summary_metadata(self, output_dir, index_bands):
        """
        Save summary metadata for all indices

        Args:
            output_dir: Output directory
            index_bands: List of index band names
        """
        summary_metadata = {
            "total_indices": len(index_bands),
            "indices": index_bands,
            "output_directory": output_dir,
            "creation_date": datetime.now().isoformat(),
            "file_structure": {
                f"{band.lower()}/": {
                    "geotiff": f"{band.lower()}.tif",
                    "numpy_array": f"{band.lower()}_array.npy",
                    "metadata": f"{band.lower()}_metadata.json",
                }
                for band in index_bands
            },
        }

        # Add image info for Earth Engine objects
        if not self.is_local and hasattr(self.image, "bandNames"):
            try:
                summary_metadata["image_info"] = {
                    "bands_available": self.image.bandNames().getInfo(),
                    "image_id": (
                        self.image.id().getInfo() if self.image.id() else "composite"
                    ),
                }
            except:
                pass

        summary_path = os.path.join(output_dir, "summary_metadata.json")
        with open(summary_path, "w") as f:
            json.dump(summary_metadata, f, indent=2)

        print(f"\n✓ Summary metadata saved to: {summary_path}")
        
        
    def batch_index_processing(self,images, index, output_dir="./datasets/processed/indices/"):
            """
            Process multiple indices in batch and save results

            Args:
                index_bands: List of index band names to calculate
                output_dir: Base directory for saving outputs
            """
            for image in images:
                self.save_indices_local(index_band=index, output_dir=output_dir)
