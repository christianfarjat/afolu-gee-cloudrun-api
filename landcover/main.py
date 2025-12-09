import os
import json
import ee
from flask import Flask, request, jsonify
from google.cloud import secretmanager

app = Flask(__name__)

# Initialize Earth Engine
def initialize_ee():
    """Initialize Earth Engine with service account credentials."""
    try:
        # Try to initialize with default credentials first
        ee.Initialize()
        print("Earth Engine initialized with default credentials")
    except Exception as e:
        print(f"Failed to initialize with default credentials: {e}")
        # Fallback to service account from Secret Manager
        try:
            project_id = os.environ.get('GCP_PROJECT', 'forestproject-copilot-ia')
            client = secretmanager.SecretManagerServiceClient()
            secret_name = f"projects/{project_id}/secrets/gee-service-account/versions/latest"
            response = client.access_secret_version(request={"name": secret_name})
            credentials_json = response.payload.data.decode('UTF-8')
            credentials = json.loads(credentials_json)
            ee_credentials = ee.ServiceAccountCredentials(credentials['client_email'], key_data=credentials_json)
            ee.Initialize(ee_credentials)
            print("Earth Engine initialized with service account")
        except Exception as init_error:
            print(f"Failed to initialize Earth Engine: {init_error}")
            raise

initialize_ee()

@app.route('/get-landcover', methods=['POST'])
def get_landcover():
    """Calculate land cover distribution for a given geometry and year."""
    try:
        data = request.get_json()
        
        # Validate input
        if not data or 'geometry' not in data:
            return jsonify({'error': 'Missing geometry in request'}), 400
        
        geometry_data = data['geometry']
        year = data.get('year', 2021)  # Default to 2021 if not specified
        
        # Convert GeoJSON to Earth Engine geometry
        ee_geometry = ee.Geometry(geometry_data)
        
        # Get ESA WorldCover (10m resolution)
        worldcover = ee.ImageCollection('ESA/WorldCover/v200').first()
        
        # Clip to area of interest
        landcover_image = worldcover.clip(ee_geometry)
        
        # Define land cover classes for ESA WorldCover
        # 10: Tree cover, 20: Shrubland, 30: Grassland, 40: Cropland
        # 50: Built-up, 60: Bare/sparse vegetation, 70: Snow and ice
        # 80: Permanent water bodies, 90: Herbaceous wetland, 95: Mangroves, 100: Moss and lichen
        
        # Calculate area for each class (in hectares)
        area_image = ee.Image.pixelArea().divide(10000)  # Convert to hectares
        
        # Calculate areas by class
        areas = landcover_image.addBands(area_image).reduceRegion(
            reducer=ee.Reducer.sum().group(
                groupField=0,
                groupName='class'
            ),
            geometry=ee_geometry,
            scale=10,
            maxPixels=1e9
        )
        
        # Process results
        groups = areas.getInfo()['groups']
        
        # Map class codes to names
        class_names = {
            10: 'forest',
            20: 'shrubland',
            30: 'grassland',
            40: 'cropland',
            50: 'built_up',
            60: 'bare_sparse',
            70: 'snow_ice',
            80: 'water',
            90: 'herbaceous_wetland',
            95: 'mangroves',
            100: 'moss_lichen'
        }
        
        # Organize results
        land_cover = {}
        total_area = 0
        
        for group in groups:
            class_code = group['class']
            area_ha = group['sum']
            class_name = class_names.get(class_code, f'unknown_{class_code}')
            land_cover[class_name] = round(area_ha, 2)
            total_area += area_ha
        
        response = {
            'land_cover': land_cover,
            'total_area_ha': round(total_area, 2),
            'year': year,
            'data_source': 'ESA WorldCover v200',
            'resolution_m': 10
        }
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Error in get_landcover: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'service': 'landcover'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
