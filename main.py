import ee
from pathlib import Path
from typing import Optional
import argparse
import json
import geemap
import datetime

from src.acquisition.image_aquisition import ImageAcquisition
from src.acquisition.climate import ClimateAcquisition
from src.processing.indices import CalculateIndices
from src.processing.sar import SARProcessor
from src.visualisation.image_visualisation import visualize_image


def gee_authenticate(project):
    """Authenticate with Google Earth Engine using service account credentials"""
    try:
        ee.Authenticate()  # This will prompt for authentication if not already authenticated
        ee.Initialize(project=project)
        print("✅ GEE authentication successful")
        return True
    except Exception as e:
        print(f"❌ GEE authentication failed: {e}")
        return False


def check_authentication():
    """Check if GEE is authenticated and initialized"""
    try:
        ee.Initialize()
        print("✅ GEE is already authenticated and initialized")
        return True
    except Exception as e:
        print(f"❌ GEE is not authenticated: {e}")
        return False


gee_authenticate("riftwaters")


def get_roi_by_name(lake_name: str) -> Optional[ee.Geometry]:
    """
    Get predefined ROI for known lakes

    Common lakes in East Africa and their approximate boundaries
    """

    lakes = {
        "baringo": ee.Geometry.Polygon(
            [
                [35.98391292157122, 0.5153611370519164],
                [36.16518733563372, 0.5153611370519164],
                [36.16518733563372, 0.7446867187538047],
                [35.98391292157122, 0.7446867187538047],
            ]
        ),
        "bogoria": ee.Geometry.Polygon(
            [
                [36.021644575238554, 0.15353594768753728],
                [36.18025968754324, 0.15353594768753728],
                [36.18025968754324, 0.36364721537653627],
                [36.021644575238554, 0.36364721537653627],
                [36.021644575238554, 0.15353594768753728],
            ]
        ),
        "naivasha": ee.Geometry.Polygon(
            [[34.0, -15.0], [36.0, -15.0], [36.0, -9.0], [34.0, -9.0]]
        ),
        "nakuru": ee.Geometry.Polygon(
            [[35.5, 2.5], [37.0, 2.5], [37.0, 5.0], [35.5, 5.0]]
        ),
        "magadi": ee.Geometry.Polygon(
            [[35.5, 2.5], [37.0, 2.5], [37.0, 5.0], [35.5, 5.0]]
        ),
        "turukana": ee.Geometry.Polygon(
            [[35.5, 2.5], [37.0, 2.5], [37.0, 5.0], [35.5, 5.0]]
        ),
        "nairobi_demo": ee.Geometry.Polygon(
            [[36.7, -1.35], [36.9, -1.35], [36.9, -1.15], [36.7, -1.15]]
        ),
    }

    return lakes.get(lake_name.lower())


def configure_acquisition(args) -> dict:
    """Configure acquisition parameters based on command line arguments"""

    config = {
        "region": args.region,
        "output_dir": args.output_dir,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "max_cloud": args.max_cloud,
        "resolution": args.resolution,
        "satellites": args.satellites,
        # "calculate_indices": args.indices,
        # "use_sar": args.use_sar,
    }

    return config


def configure_indices(args) -> dict:
    """Configure index calculation parameters based on command line arguments"""

    config = {
        "region": args.region,
        "image": args.image,
        "indices": args.indices,
    }

    return config


def configure_visualization(args) -> dict:
    """Configure visualization parameters based on command line arguments"""

    config = {
        "image": args.image,
        "satellite": args.satellite,
        "title": args.title,
    }

    return config


def configure_sar(args) -> dict:
    """Configure SAR processing parameters based on command line arguments"""

    config = {
        "image": args.image,
        "region": args.region,
        "method": args.method,
        "image_id": args.image_id,
        "threshold_value": args.threshold_value,
    }

    return config


def configure_batch_acquisition(args):
    config = {
        "satellite": args.satellite,
        "start_year": args.start_year,
        "end_year": args.end_year,
        "region": args.region,
    }

    return config


def configure_climate(args) -> dict:
    """Configure climate data acquisition parameters based on command line arguments"""

    config = {
        "region": args.region,
        "start_date": args.start_date,
        "end_date": args.end_date,
        # "era5_variables": args.era5_variables,
    }

    return config


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Satellite Image Acquisition System")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    acquire_parser = subparsers.add_parser("acquire", help="Acquire satellite imagery")
    acquire_parser.add_argument(
        "--start_date", type=str, required=True, help="Start date (YYYY-MM-DD)"
    )
    acquire_parser.add_argument(
        "--end_date", type=str, required=True, help="End date (YYYY-MM-DD)"
    )
    acquire_parser.add_argument(
        "--max_cloud",
        type=int,
        default=30,
        help="Maximum cloud cover percentage (default: 30)",
    )
    acquire_parser.add_argument(
        "--resolution",
        type=int,
        default=10,
        help="Export resolution in meters (default: 10)",
    )
    acquire_parser.add_argument(
        "--satellites",
        nargs="+",
        default=["sentinel2"],
        help="Satellites to acquire (default: sentinel2)",
    )
    acquire_parser.add_argument(
        "--region", type=str, required=True, help="Name of the region of interest"
    )
    acquire_parser.add_argument(
        "--project", type=str, help="Google Cloud project ID for GEE"
    )
    acquire_parser.add_argument(
        "--output_dir",
        type=str,
        default="./datasets",
        help="Directory to save acquired imagery (default: ./data)",
    )
    # acquire_parser.add_argument("--use_sar", action="store_true", help="Whether to acquire SAR data (default: False)")

    indices_parser = subparsers.add_parser(
        "calculate_indices", help="Calculate spectral indices from acquired imagery"
    )
    indices_parser.add_argument(
        "--image", type=str, required=True, help="Directory containing acquired imagery"
    )
    indices_parser.add_argument(
        "--region", type=str, required=True, help="Name of the region of interest for index calculation"
        
    )
    indices_parser.add_argument(
        "--indices",
        nargs="+",
        default=["NDVI"],
        help="Spectral indices to calculate (default: NDVI)",
    )

    sar_parser = subparsers.add_parser(
        "process_sar", help="Process Sentinel-1 SAR imagery for water detection"
    )
    sar_parser.add_argument(
        "--image",
        type=str,
        required=True,
        help="Directory containing acquired SAR imagery",
    )
    sar_parser.add_argument(
        "--region",
        type=str,
        required=True,
        help="Name of the region of interest for SAR processing",
    )
    sar_parser.add_argument(
        "--image_id",
        required=True,
        type=str,
        help="Unique identifier for the SAR image (optional, will be derived from filename if not provided)",
    )
    sar_parser.add_argument(
        "--method",
        type=str,
        default="threshold",
        help="Method for water detection (default: threshold, options: threshold, adaptive_threshold, local_threshold, kmeans)",
    )
    sar_parser.add_argument(
        "--threshold_value",
        type=float,
        default=-15,
        help="Threshold value for water detection (only used if method=threshold, default: 10)",
    )

    climate_aquisition_parser = subparsers.add_parser(
        "acquire_climate",
        help="Acquire climate data for the specified region and time period",
    )
    climate_aquisition_parser.add_argument(
        "--region",
        type=str,
        required=True,
        help="Name of the region of interest for climate data acquisition",
    )
    climate_aquisition_parser.add_argument(
        "--start_date",
        type=str,
        required=True,
        help="Start date for climate data acquisition (YYYY-MM-DD)",
    )
    climate_aquisition_parser.add_argument(
        "--end_date",
        type=str,
        required=True,
        help="End date for climate data acquisition (YYYY-MM-DD)",
    )

    batch_acquisition_parser = subparsers.add_parser(
        "batch_acquisition",
        help="Batch acquire satellite imagery for multiple regions and time periods",
    )

    batch_acquisition_parser.add_argument(
        "--satellite",
        type=str,
        required=True,
        help="Path to JSON file containing list of images to acquire with parameters ",
    )
    batch_acquisition_parser.add_argument(
        "--start_year", type=int, required=True, help="Acquisition start year"
    )
    batch_acquisition_parser.add_argument(
        "--end_year", type=int, required=True, help="Acquisition end year"
    )
    batch_acquisition_parser.add_argument(
        "--region",
        type=str,
        required=True,
        help="Directory to save acquired imagery (default: ./datasets)",
    )
    visualise_parser = subparsers.add_parser(
        "visualize", help="Visualize acquired imagery"
    )
    visualise_parser.add_argument(
        "--image", type=str, required=True, help="Directory containing acquired imagery"
    )
    visualise_parser.add_argument(
        "--satellite",
        type=str,
        required=True,
        help="Satellite type for visualization (e.g., sentinel2, sentinel1, landsat)",
    )
    visualise_parser.add_argument(
        "--title",
        type=str,
        default="Satellite Image",
        help="Title for the visualization",
    )

    args = parser.parse_args()

    # Aquire a single image
    if args.command == "acquire":
        acq_config = configure_acquisition(args)
        acquisition = ImageAcquisition(
            region=args.region,
        )
        roi = get_roi_by_name(args.region)

        try:
            if roi is None:
                print(f"❌ Invalid region specified: {args.region}")
                exit(1)

            if "sentinel2" in acq_config["satellites"]:
                acquisition.acquire_sentinel2(
                    roi=roi,
                    start_date=acq_config["start_date"],
                    end_date=acq_config["end_date"],
                    max_cloud=acq_config["max_cloud"],
                    export_resolution=acq_config["resolution"],
                )
            elif "sentinel1" in acq_config["satellites"]:
                acquisition.acquire_sentinel1(
                    roi=roi,
                    start_date=acq_config["start_date"],
                    end_date=acq_config["end_date"],
                    polarization="VV",
                    # export_resolution=acq_config["resolution"],
                    # apply_mask=True,
                )
            elif "landsat" in acq_config["satellites"]:
                acquisition.acquire_landsat(
                    roi=roi,
                    start_date=acq_config["start_date"],
                    end_date=acq_config["end_date"],
                    satellite="landsat8",
                    max_cloud=acq_config["max_cloud"],
                )
            else:
                print(f"❌ Unsupported satellite specified: {acq_config['satellites']}")
                exit(1)

        except Exception as e:
            print(f"❌ Error occurred while authenticating with GEE: {e}")
    if args.command == "batch_acquisition":
        batch_config = configure_batch_acquisition(args)
        acquisition = ImageAcquisition(region=batch_config["region"])
        roi = get_roi_by_name(batch_config["region"])

        try:
            if roi is None:
                print(f"❌ Invalid region specified: {batch_config['region']}")
                exit(1)

            acquisition.batch_acquisition(
                satellite=batch_config["satellite"],
                start_year=batch_config["start_year"],
                end_year=batch_config["end_year"],
                roi=roi,
            )
        except Exception as e:
            print(f"❌ Error occurred during batch acquisition: {e}")

    if args.command == "acquire_climate":
        climate_config = configure_climate(args)
        climate_acquisition = ClimateAcquisition(
            region=climate_config["region"],
        )
        roi = get_roi_by_name(climate_config["region"])

        try:
            if roi is None:
                print(f"❌ Invalid region specified: {climate_config['region']}")
                exit(1)

            climate_acquisition.acquire_era5(
                roi=roi,
                start_date=climate_config["start_date"],
                end_date=climate_config["end_date"],
            )
        except Exception as e:
            print(f"❌ Error occurred while acquiring climate data: {e}")

    if args.command == "calculate_indices":
        indices_config = configure_indices(args)
        # image = geemap.load_GeoTIFF(indices_config["image"])
        calculate_indices = CalculateIndices(
            image=indices_config["image"],
            region=indices_config["region"],
            index_band=indices_config["indices"],
        )
        try:
            # calculate_indices.save_indices_local(indices_config["indices"])
            calculate_indices.save_indices_local(indices_config["indices"])
        except Exception as e:
            print(f"❌ Error occurred while calculating indices: {e}")

    if args.command == "process_sar":
        sar_config = configure_sar(args)
        SAR_processor = SARProcessor(
            sar_config["image"], sar_config["image_id"], sar_config["region"]
        )

        try:
            SAR_processor.process_sentinel1_sar(
                sar_config["image"], sar_config["method"], sar_config["threshold_value"]
            )
            # process_sar.save_water_mask()

        except Exception as e:
            print(f"❌ Error occurred while processing SAR data: {e}")

    if args.command == "visualize":
        vis_config = configure_visualization(args)
        try:
            # image = ee.Image(vis_config["image"])
            visualize_image(
                vis_config["image"], vis_config["satellite"], vis_config["title"]
            )
        except Exception as e:
            print(f"❌ Error occurred while visualizing image: {e}")

    """
    _summary_

python main.py acquire --region "bogoria" --start_date "2023-01-01" --end_date "2023-01-31" --max_cloud 20 --resolution 10 --satellites sentinel2 
python main.py calculate_indices --image /home/desy/rift-waters/dataset/bogoria/raw/landsat8/landsat8_2020-02-01_to_2020-02-29.tif --indices "NDWI" 
python main.py visualize --image /home/desy/rift-waters/dataset/bogoria/raw/landsat8/landsat8_2025-01-01_to_2025-01-31.tif --satellite landsat --title "NDWI Visualization"
python main.py process_sar --image /home/desy/rift-waters/dataset/bogoria/raw/sentinel1/sentinel1_2025-01-01_to_2025-01-31.tif --region "bogoria" --method "threshold" --threshold_value -15
python main.py batch_acquisition --satellite "sentinel2" --start_year 2020 --end_year 2021 --region "bogoria"
python main.py acquire_climate --region "bogoria" --start_date "2023-01-01" --end_date "2023-01-31"
    """
