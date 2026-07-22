# src/config.py

import ee

def get_roi_by_name(lake_name):
    lakes = {
        "baringo": ee.Geometry.Polygon([
            [35.98391292157122, 0.5153611370519164],
            [36.16518733563372, 0.5153611370519164],
            [36.16518733563372, 0.7446867187538047],
            [35.98391292157122, 0.7446867187538047],
        ]),
        "bogoria": ee.Geometry.Polygon([
            [36.021644575238554, 0.15353594768753728],
            [36.18025968754324, 0.15353594768753728],
            [36.18025968754324, 0.36364721537653627],
            [36.021644575238554, 0.36364721537653627],
            [36.021644575238554, 0.15353594768753728],
        ]),
        "naivasha": ee.Geometry.Polygon([
            [34.0, -15.0], [36.0, -15.0], [36.0, -9.0], [34.0, -9.0]
        ]),
        "nakuru": ee.Geometry.Polygon([
            [35.5, 2.5], [37.0, 2.5], [37.0, 5.0], [35.5, 5.0]
        ]),
        "magadi": ee.Geometry.Polygon([
            [35.5, 2.5], [37.0, 2.5], [37.0, 5.0], [35.5, 5.0]
        ]),
        "turukana": ee.Geometry.Polygon([
            [35.5, 2.5], [37.0, 2.5], [37.0, 5.0], [35.5, 5.0]
        ]),
        "nairobi_demo": ee.Geometry.Polygon([
            [36.7, -1.35], [36.9, -1.35], [36.9, -1.15], [36.7, -1.15]
        ]),
    }
    return lakes.get(lake_name.lower())

def get_roi_by_coordinates(coordinates):
    """
    Returns an ee.Geometry.Polygon object for the given coordinates.
    Coordinates should be a list of [longitude, latitude] pairs.
    """
    return ee.Geometry.Polygon(coordinates)

def get_roi_by_wards( ward:str):
    
    ward = ee.FeatureCollection("projects/riftwaters/assets/kenya_wards") \
        .filter(ee.Filter.inList("ward", ward))
        
    return ward.geometry()




\
def configure_acquisition(args):
    return {
        "region": args.region,
        "output_dir": args.output_dir,
        "start_date": args.start_date,
        "end_date": args.end_date,
        "max_cloud": args.max_cloud,
        "resolution": args.resolution,
        "satellites": args.satellites,
    }


def configure_indices(args):
    return {
        "region": args.region,
        "image": args.image,
        "indices": args.indices,
    }


def configure_visualization(args):
    return {
        "image": args.image,
        "satellite": args.satellite,
        "title": args.title,
    }


def configure_sar(args):
    return {
        "image": args.image,
        "region": args.region,
        "method": args.method,
        "image_id": args.image_id,
        "threshold_value": args.threshold_value,
    }


def configure_batch_acquisition(args):
    return {
        "satellite": args.satellite,
        "start_year": args.start_year,
        "end_year": args.end_year,
        "region": args.region,
    }


def configure_climate(args):
    return {
        "region": args.region,
        "start_date": args.start_date,
        "end_date": args.end_date,
    }


def configure_batch_sar_processing(args):
    return {
        "csv_file": args.csv_file,
        "region": args.region,
    }
    
    
    
def configure_batch_indices(args):
    return {
        "csv_file": args.csv_file,
        "region": args.region,
        "indices": args.indices,
    }
    
def configure_dem_acquisition(args):
    return {
        "region": args.region,
        "start_date": args.start_date,
        "end_date": args.end_date,
    }