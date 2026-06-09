import json
import os
import ee
import geemap
import datetime
import pandas as pd
import datetime
from calendar import monthrange
from pathlib import Path
from typing import Optional
from importlib.resources import path


class ImageAcquisition:
    def __init__(self, region):
        self.region = region
        # Set base_dir as an attribute based on project_name
        self.base_dir = Path(f"./dataset/{region}")

    def checkdir(path):
        if not os.path.exists(path):
            os.makedirs(os.path.abspath(path))

    def _ensure_directories(self, satellite_type):
        """Create directories for a specific satellite type if they don't exist"""
        dir_path = self.base_dir / "raw" / satellite_type
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"Directories created/verified: {dir_path}")
            return dir_path
        except Exception as e:
            print(f"Error creating directory {dir_path}: {e}")
            return None

    def _save_metadata(self, metadata: dict):
        metadata_dir = self.base_dir / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        
        # Single JSON file for each satellite
        json_path = metadata_dir / f"{self.region}_{metadata['satellite']}.json"
        
        # Prepare new entry
        json_entry = {
            "satellite": metadata["satellite"],
            "start_date": metadata["start_date"],
            "end_date": metadata["end_date"],
            "bands": metadata.get("bands", []),
            "resolution": metadata.get("resolution", ""),
            "max_cloud": metadata.get("max_cloud", 0),
            "acquisition_time": datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        }
        
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
        
        
        # Also update CSV similarly (if needed)
        csv_path = metadata_dir / f"{self.region}_{metadata['satellite']}.csv"
        df_entry = pd.DataFrame([{
            "image_id": metadata["end_date"],
            "file_path": metadata["file_path"],
            "no_images": metadata.get("num_images", 0)
        }])
        
        if csv_path.exists():
            existing_df = pd.read_csv(csv_path)
            updated_df = pd.concat([existing_df, df_entry], ignore_index=True)
            updated_df.to_csv(csv_path, index=False)
        else:
            df_entry.to_csv(csv_path, index=False)
    
        print(f"  📝 Metadata appended to {json_path}")
        
    
    def acquire_sentinel2(
        self,
        roi: ee.Geometry,
        start_date: str,
        end_date: str,
        max_cloud: int = 30,
        export_resolution: int = 1000,
        apply_mask: bool = True,
    ) -> Optional[str]:
        # Ensure directories exist
        sentinel2_dir = self._ensure_directories("sentinel2")
        if sentinel2_dir is None:
            print("Error: Could not create sentinel2 directory")
            return None

        # Load Sentinel-2 image collection
        try:
            s2_collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(roi)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", max_cloud))
            )
            count = s2_collection.size().getInfo()
            print(f"Found {count} Sentinel-2 images")
            if count == 0:
                print("No Sentinel-2 images found for the specified parameters")
                return None
            if apply_mask:

                def mask_s2_clouds(image):
                    qa = image.select("QA60")
                    cloud_mask = (
                        qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
                    )
                    return image.updateMask(cloud_mask)

                s2_collection = s2_collection.map(mask_s2_clouds)
            image = s2_collection.median().clip(
                roi
            )  ##############################################################################################################################

            bands = ["B2", "B3", "B4", "B8", "B11", "B12"]  # Blue, Green, Red, NIR
            band_names = ["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2"]
            image = image.select(bands, band_names)
            output_filename = (
                f"{end_date}_cloud{max_cloud}.tif"
            )
            output_path = sentinel2_dir / output_filename
            print(f"Exporting Sentinel-2 image to {output_path}")
            
            
            geemap.ee_export_image(
                image, filename=str(output_path), scale=100, region=roi
            )
            print(f"Sentinel-2 image saved to {output_path}")
            geemap.ee_export_image_to_drive(
                image, description=output_filename, scale=100, region=roi
            )
            self._save_metadata(
                {
                    "satellite": "sentinel2",
                    "start_date": start_date,
                    "end_date": end_date,
                    "max_cloud": max_cloud,
                    "resolution": export_resolution,
                    "num_images": count,
                    "file_path": str(output_path),
                    "bands": band_names,
                }
            )
            print("Sentinel-2 image saved successfully")
            return str(output_path)

        except Exception as e:
            print(f"Error acquiring Sentinel-2 data: {e}")
            return None

    def acquire_sentinel1(
        self,
        roi: ee.Geometry,
        start_date: str,
        end_date: str,
        polarization: str = "VV",
        orbit: str = "ASCENDING",
    ) -> Optional[str]:
        """
        Acquire Sentinel-1 SAR imagery for water detection in cloudy conditions

        Args:
            roi: Region of interest
            start_date: Start date
            end_date: End date
            polarization: 'VV', 'VH', or 'both'
            orbit: 'ASCENDING' or 'DESCENDING'
        """
        # Ensure directories exist
        sentinel1_dir = self._ensure_directories("sentinel1")
        if sentinel1_dir is None:
            print("Error: Could not create sentinel1 directory")
            return None

        try:
            print(
                f"\n📡 Acquiring Sentinel-1 SAR imagery from {start_date} to {end_date}"
            )

            # Load Sentinel-1 collection
            sentinel1 = (
                ee.ImageCollection("COPERNICUS/S1_GRD")
                .filterBounds(roi)
                .filterDate(start_date, end_date)
                .filter(
                    ee.Filter.listContains(
                        "transmitterReceiverPolarisation", polarization
                    )
                )
                .filter(ee.Filter.eq("orbitProperties_pass", orbit))
                .filter(ee.Filter.eq("instrumentMode", "IW"))
            )

            count = sentinel1.size().getInfo()
            print(f"  Found {count} images")

            if count == 0:
                return None

            # Apply preprocessing
            def preprocess_sar(image):
                # Apply thermal noise removal, radiometric calibration, and terrain correction
                image = image.select(polarization)
                image = image.focal_median(radius=50, units="meters")
                return image.clip(roi)

            processed = sentinel1.map(preprocess_sar)

            # Create median composite
            composite = processed.median()

            # Export
            output_filename = f"{end_date}_{polarization}_{orbit}.tif"
            output_path = sentinel1_dir / output_filename

            geemap.ee_export_image(
                composite, filename=str(output_path), scale=10, region=roi
            )
            geemap.ee_export_image_to_drive(
                composite, description=output_filename, scale=10, region=roi
            )

            self._save_metadata(
                {
                    "satellite": "Sentinel-1",
                    "start_date": start_date,
                    "end_date": end_date,
                    "polarization": polarization,
                    "orbit": orbit,
                    "num_images": count,
                    "bands": "SAR",
                    "file_path": str(output_path),
                }
            )

            print(f"  ✓ Sentinel-1 image saved")
            return str(output_path)

        except Exception as e:
            print(f"  ✗ Error acquiring Sentinel-1 data: {e}")
            return None

    def acquire_landsat(
        self,
        roi: ee.Geometry,
        start_date: str,
        end_date: str,
        satellite: str = "landsat8",
        max_cloud: int = 30,
    ) -> Optional[str]:
        """
        Acquire Landsat imagery

        Args:
            roi: Region of interest
            start_date: Start date
            end_date: End date
            satellite: 'landsat8' or 'landsat9'
            max_cloud: Maximum cloud cover
        """
        # Ensure directories exist
        landsat_dir = self._ensure_directories(satellite)
        if landsat_dir is None:
            print(f"Error: Could not create {satellite} directory")
            return None

        try:
            print(f"\n🛰️  Acquiring {satellite.upper()} imagery for dates {start_date} to {end_date} with max cloud cover {max_cloud}%")

            # Select appropriate Landsat collection
            collections = {
                "landsat8": "LANDSAT/LC08/C02/T1_L2",
                "landsat9": "LANDSAT/LC09/C02/T1_L2",
            }

            if satellite not in collections:
                print(f"  ✗ Satellite {satellite} not supported")
                return None

            # Load collection
            landsat = (
                ee.ImageCollection(collections[satellite])
                .filterBounds(roi)
                .filterDate(start_date, end_date)
                .filter(ee.Filter.lt("CLOUD_COVER", max_cloud))
            )

            count = landsat.size().getInfo()
            print(f"  Found {count} images")

            if count == 0:
                return None

            # Apply scale factors
            def scale_landsat(image):
                optical_bands = ["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"]
                optical_names = ["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2"]
                thermal_bands = ["ST_B10"]
                thermal_names = ["Thermal"]

                # Scale optical bands
                for i, band in enumerate(optical_bands):
                    image = image.updateMask(image.select(band).gt(0))
                    scaled = image.select(band).multiply(0.0000275).add(-0.2)
                    image = image.addBands(scaled.rename(optical_names[i]))

                # Scale thermal band
                for i, band in enumerate(thermal_bands):
                    scaled = image.select(band).multiply(0.00341802).add(149.0)
                    image = image.addBands(scaled.rename(thermal_names[i]))

                return image.select(optical_names + thermal_names)

            landsat_scaled = landsat.map(scale_landsat)
            composite = landsat_scaled.median().clip(roi)

            # Export
            output_filename = f"{end_date}.tif"
            output_path = landsat_dir / output_filename

            geemap.ee_export_image(
                composite, filename=str(output_path), scale=30, region=roi
            )

            self._save_metadata(
                {
                    "satellite": satellite,
                    "start_date": start_date,
                    "end_date": end_date,
                    "max_cloud": max_cloud,
                    "num_images": count,
                    "bands": ["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2", "Thermal"],
                    "file_path": str(output_path),
                }
            )

            print(f"  ✓ {satellite.upper()} image saved")
            return str(output_path)

        except Exception as e:
            print(f"  ✗ Error acquiring Landsat data: {e}")
            return None


    #Monthly batch image acquisition 
    def batch_acquisition(self, satellite, roi, start_year, end_year, max_cloud=30):
        month_ranges = []
        for year in range(start_year, end_year + 1):
            for month in range(1, 13):
                # First day of the month
                start_date = datetime.datetime(year, month, 1).strftime("%Y-%m-%d")

                # Last day of the month
                last_day = monthrange(year, month)[1]
                end_date = datetime.datetime(year, month, last_day).strftime("%Y-%m-%d")
                month_ranges.append((start_date, end_date))
                

        print(f"Month ranges to acquire: {month_ranges}")
        for start_date, end_date in month_ranges:
            if satellite == "sentinel2":
                self.acquire_sentinel2(roi, start_date, end_date, max_cloud)
            elif satellite == "sentinel1":
                self.acquire_sentinel1(roi, start_date, end_date)
            elif satellite in ["landsat8", "landsat9"]:
                self.acquire_landsat(roi, start_date, end_date, satellite, max_cloud)
