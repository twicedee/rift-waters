import ee
import os



class ClimateAcquisition:
    def __init__(self, region, output_dir="dataset"):
        self.base_dir = output_dir
        self.region = region
    
    
      
                
    def acquire_era5(
        self,
        roi: ee.Geometry,
        start_date: str,
        end_date: str,
    ):
        """Acquire ERA5 climate data for the specified region and time period."""
        
        era5 = (
            ee.ImageCollection("ECMWF/ERA5/DAILY")
            .filterBounds(roi)
            .filterDate(start_date, end_date)
            )
        roi_climate = era5.reduceRegions(roi, ee.Reducer.first())

        roi_climates_dataframe = ee.data.computeFeatures(
            {'expression': roi_climate, 'fileFormat': 'PANDAS_DATAFRAME'}
        )
        roi_climates_dataframe
        # Save metadata
        output_dir = f"{self.base_dir}/{self.region}/raw/climate/{roi_climates_dataframe}"
        os.makedirs(output_dir, exist_ok=True)
        
        
        return era5
    
    
    