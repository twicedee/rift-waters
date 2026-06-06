import ee
import os



class ClimateAcquisition:
    def __init__(self, config):
        self.config = config
        self.base_dir = Path(config["base_dir"])
        self._make_dirs()
    
    
    def _make_dirs(self):

        directories = [
            self.base_dir / "raw" / "climate",
            self.base_dir / "processed" / "climate",
            self.base_dir / "logs",
            self.base_dir / "metadata",
        ]

        for dir in directories:
            try:
                if not os.path.exists(dir):
                    dir.mkdir(parents=True, exist_ok=True)
                print(f"Directories created: {dir}")
            except Exception as e:
                print(f"Error creating directory {dir}: {e}")    
                
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
            .select(self.config["era5_variables"])
        )
        
        # Save metadata
        metadata = {
            "source": "ERA5",
            "variables": self.config["era5_variables"],
            "start_date": start_date,
            "end_date": end_date,
            "region": roi.getInfo(),
        }
        self._save_metadata(metadata)
        
        return era5
    
    
    