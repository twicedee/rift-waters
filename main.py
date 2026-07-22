# main.py

import ee
import argparse
import pandas as pd

from config import (
    get_roi_by_name,
    get_roi_by_wards,
    configure_acquisition,
    configure_indices,
    configure_visualization,
    configure_sar,
    configure_batch_acquisition,
    configure_climate,
    configure_batch_sar_processing,
    configure_dem_acquisition,
)
from src.acquisition.image_aquisition import ImageAcquisition
from src.acquisition.era5 import ClimateAcquisition
from src.processing.indices import CalculateIndices
from src.processing.sar import SARProcessor
from src.visualisation.image_visualisation import visualize_image
from src.acquisition.dem_aquisition import DEMAcquisition


def gee_authenticate(project):
    try:
        ee.Authenticate()
        ee.Initialize(project=project)
        print("✅ GEE authentication successful")
        return True
    except Exception as e:
        print(f"❌ GEE authentication failed: {e}")
        return False


def check_authentication():
    try:
        ee.Initialize()
        print("✅ GEE is already authenticated and initialized")
        return True
    except Exception as e:
        print(f"❌ GEE is not authenticated: {e}")
        return False


gee_authenticate("riftwaters")


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

    indices_parser = subparsers.add_parser(
        "calculate_indices", help="Calculate spectral indices from acquired imagery"
    )
    indices_parser.add_argument(
        "--image", type=str, required=True, help="Directory containing acquired imagery"
    )
    indices_parser.add_argument(
        "--region",
        type=str,
        required=True,
        help="Name of the region of interest for index calculation",
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
        "--image_id", type=str, help="Unique identifier for the SAR image"
    )
    sar_parser.add_argument(
        "--method",
        type=str,
        default="threshold",
        help="Method for water detection (default: threshold)",
    )
    sar_parser.add_argument(
        "--threshold_value",
        type=float,
        default=-15,
        help="Threshold value for water detection (default: -15)",
    )

    dem_parser = subparsers.add_parser(
        "acquire_dem", help="Acquire Copernicus GLO-30 DEM for a region"
    )
    dem_parser.add_argument(
        "--region",
        type=str,
        required=True,
        help="Name of the region of interest for DEM acquisition",
    )
    dem_parser.add_argument(
        "--start_date",
        type=str,
        help="Coordinate reference system for DEM export (default: EPSG:4326)",
    )
    dem_parser.add_argument("--end_date", type=str, help="End date (YYYY-MM-DD)")

    climate_parser = subparsers.add_parser(
        "acquire_climate", help="Acquire climate data"
    )
    climate_parser.add_argument(
        "--region", type=str, required=True, help="Name of the region of interest"
    )
    climate_parser.add_argument(
        "--start_date", type=str, required=True, help="Start date (YYYY-MM-DD)"
    )
    climate_parser.add_argument(
        "--end_date", type=str, required=True, help="End date (YYYY-MM-DD)"
    )

    batch_acq_parser = subparsers.add_parser(
        "batch_acquisition", help="Batch acquire satellite imagery"
    )
    batch_acq_parser.add_argument(
        "--satellite", type=str, required=True, help="Satellite type"
    )
    batch_acq_parser.add_argument(
        "--start_year", type=int, required=True, help="Acquisition start year"
    )
    batch_acq_parser.add_argument(
        "--end_year", type=int, required=True, help="Acquisition end year"
    )
    batch_acq_parser.add_argument(
        "--region", type=str, required=True, help="Region of interest"
    )

    batch_sar_parser = subparsers.add_parser(
        "batch_process_sar", help="Batch processing of SAR images"
    )
    batch_sar_parser.add_argument("--csv_file", type=str, required=True)
    batch_sar_parser.add_argument("--region", type=str, required=True)

    visualise_parser = subparsers.add_parser(
        "visualize", help="Visualize acquired imagery"
    )
    visualise_parser.add_argument(
        "--image", type=str, required=True, help="Directory containing acquired imagery"
    )
    visualise_parser.add_argument(
        "--satellite", type=str, required=True, help="Satellite type for visualization"
    )
    visualise_parser.add_argument(
        "--title",
        type=str,
        default="Satellite Image",
        help="Title for the visualization",
    )

    args = parser.parse_args()

    if args.command == "acquire":
        acq_config = configure_acquisition(args)
        acquisition = ImageAcquisition(region=args.region)
        roi = get_roi_by_wards(args.region)

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

    elif args.command == "batch_acquisition":
        batch_config = configure_batch_acquisition(args)
        acquisition = ImageAcquisition(region=batch_config["region"])
        roi = get_roi_by_name(batch_config["region"])

        if roi is None:
            print(f"❌ Invalid region specified: {batch_config['region']}")
            exit(1)

        acquisition.batch_acquisition(
            satellite=batch_config["satellite"],
            start_year=batch_config["start_year"],
            end_year=batch_config["end_year"],
            roi=roi,
        )

    elif args.command == "acquire_climate":
        climate_config = configure_climate(args)
        climate_acquisition = ClimateAcquisition(region=climate_config["region"])
        roi = get_roi_by_name(climate_config["region"])

        if roi is None:
            print(f"❌ Invalid region specified: {climate_config['region']}")
            exit(1)

        climate_acquisition.acquire_era5(
            roi=roi,
            start_date=climate_config["start_date"],
            end_date=climate_config["end_date"],
        )

    elif args.command == "calculate_indices":
        indices_config = configure_indices(args)
        calculate_indices = CalculateIndices(
            image=indices_config["image"],
            region=indices_config["region"],
            index_band=indices_config["indices"],
        )
        calculate_indices.save_indices_local(indices_config["indices"])

    elif args.command == "process_sar":
        sar_config = configure_sar(args)
        sar_processor = SARProcessor(sar_config["region"], sar_config["image_id"])
        sar_processor.process_sentinel1_sar(
            sar_config["image"], sar_config["method"], sar_config["threshold_value"]
        )

    elif args.command == "batch_process_sar":
        batch_sar_config = configure_batch_sar_processing(args)
        df = pd.read_csv(batch_sar_config["csv_file"])
        print("reading csv")

        for idx, row in df.iterrows():
            image_id = row["image_id"]
            image_id = int(image_id.replace("-", ""))
            image_path = row["file_path"]
            print(image_path)
            print(f"🔄 Processing: {image_id}")

            sar_processor = SARProcessor(batch_sar_config["region"], image_id)
            sar_processor.process_sentinel1_sar(image_path)
            
    elif args.command == "acquire_dem":
        dem_config = configure_dem_acquisition(args)
        dem_acquisition = DEMAcquisition(
            region=dem_config["region"]
        )
        roi = get_roi_by_name(dem_config["region"])
        dem_path = dem_acquisition.acquire_dem(roi, dem_config["start_date"], dem_config["end_date"])  
        

    elif args.command == "visualize":
        vis_config = configure_visualization(args)
        visualize_image(
            vis_config["image"], vis_config["satellite"], vis_config["title"]
        )
