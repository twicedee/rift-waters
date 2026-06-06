import geemap
import ee


def visualize_image(image, satellite, title):
    """Visualize a single image using geemap"""

    # Create a geemap map centered on the image
    #image = ee.ImageCollection(img)
    #center = image.geometry().centroid().coordinates().getInfo()
    m = geemap.Map(zoom=10)

    # Add the image to the map with visualization parameters
    if satellite == "sentinel2":
        vis_params = {
            "bands": ["b3", "b2", "b1"],  # RGB bands for Sentinel-2
            "min": 0,
            "max": 3000,
            "gamma": 1.4,
        }
    elif satellite == "sentinel1":
        vis_params = {
            "bands": ["VV"],  # VV polarization for Sentinel-1
            "min": -20,
            "max": 0,
        }
    elif satellite == "landsat":
        vis_params = {
            "bands": ["b4", "b3", "b2"],  # RGB bands for Landsat 8
            "min": 0,
            "max": 3000,
            "gamma": 1.4,
        }
        
    else:
        print(f"❌ Unsupported satellite specified for visualization: {satellite}")
        return
    
    
    m.add_layer(image, vis_params, title)

    # Display the map
    m.add_layer_control()
    print(m)