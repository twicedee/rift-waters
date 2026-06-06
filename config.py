import ee
from pathlib import Path
from typing import Optional
import argparse

from src.acquisition.image_aquisition import ImageAcquisition
from src.acquisition.climate import ClimateAcquisition
from src.processing.indices import CalculateIndices

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



def create_output_dir(region, action, output_dir="./dataset") -> Path:
    """Create output directory if it doesn't exist"""
    output_path = Path(output_dir) / region 
    if action=="acquisition":
        output_path = output_path / "raw"
    else:
        output_path = output_path / "processed"
    
    output_path.mkdir(parents=True, exist_ok=True)
    print(f"✅ Output directory created: {output_path.resolve()}")
    return output_path


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
            [[29.0, -9.0], [31.5, -9.0], [31.5, -4.0], [29.0, -4.0]]
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
        "project_name": args.project,
        "region": args.region,
        "output_dir": args.output_dir,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "max_cloud": args.max_cloud,
        "resolution": args.resolution,
        "satellites": args.satellites,
        "use_sar": args.use_sar,
    }

    return config
    
def configure_indices(args) -> dict:
    """Configure index calculation parameters based on command line arguments"""

    config = {
        "image": args.image,
        "output_dir": args.output_dir,
        "indices": args.indices,
    }

    return config
    



