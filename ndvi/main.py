"""NDVI Calculation Endpoint for AFOLU Carbon Analysis.

This Cloud Run service calculates NDVI (Normalized Difference Vegetation Index)
from Sentinel-2 satellite imagery using Google Earth Engine.
"""

from flask import Flask, request, jsonify
import ee
import os
from datetime import datetime

app = Flask(__name__)

# Initialize Earth Engine
try:
    ee.Initialize()
    print("Earth Engine initialized successfully")
except Exception as e:
    print(f"Error initializing Earth Engine: {e}")
    # Try authenticating with service account
    try:
        credentials = ee.ServiceAccountCredentials(
            email=os.environ.get('GEE_SERVICE_ACCOUNT'),
            key_file=os.environ.get('GEE_KEY_FILE')
        )
        ee.Initialize(credentials)
        print("Earth Engine initialized with service account")
    except Exception as e2:
        print(f"Service account auth also failed: {e2}")


@app.route('/calculate-ndvi', methods=['POST'])
def calculate_ndvi():
    """Calculate NDVI for a given area and time period.
    
    Request body:
    {
        "geometry": {"type": "Polygon", "coordinates": [...]},
        "start_date": "2023-01-01",
        "end_date": "2023-12-31"
    }
    
    Response:
    {
        "ndvi_mean": 0.65,
        "ndvi_std": 0.12,
        "ndvi_time_series": [{"date": "2023-01-15", "ndvi": 0.63}],
        "cloud_coverage_pct": 15.2,
        "image_count": 45
    }
    """
    try:
        # Get request data
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        # Validate required fields
        required_fields = ['geometry', 'start_date', 'end_date']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        # Extract parameters
        geometry = ee.Geometry(data['geometry'])
        start_date = data['start_date']
        end_date = data['end_date']
        
        # Optional parameters
        cloud_threshold = data.get('cloud_threshold', 20)
        scale = data.get('scale', 10)  # meters
        
        # Get Sentinel-2 Surface Reflectance imagery
        collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                     .filterBounds(geometry)
                     .filterDate(start_date, end_date)
                     .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', cloud_threshold)))
        
        # Check if collection has images
        count = collection.size().getInfo()
        if count == 0:
            return jsonify({
                'error': 'No images found for the specified criteria',
                'image_count': 0
            }), 404
        
        # Function to calculate NDVI
        def add_ndvi(image):
            ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
            return image.addBands(ndvi)
        
        # Apply NDVI calculation to collection
        ndvi_collection = collection.map(add_ndvi)
        
        # Calculate mean NDVI over the area
        ndvi_image = ndvi_collection.select('NDVI').mean()
        
        # Get statistics
        stats = ndvi_image.reduceRegion(
            reducer=ee.Reducer.mean().combine(
                reducer2=ee.Reducer.stdDev(),
                sharedInputs=True
            ),
            geometry=geometry,
            scale=scale,
            maxPixels=1e9
        ).getInfo()
        
        # Get time series data
        def get_ndvi_value(image):
            value = image.select('NDVI').reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geometry,
                scale=scale,
                maxPixels=1e9
            ).get('NDVI')
            
            return ee.Feature(None, {
                'date': image.date().format('YYYY-MM-dd'),
                'ndvi': value,
                'cloud_pct': image.get('CLOUDY_PIXEL_PERCENTAGE')
            })
        
        time_series_collection = ndvi_collection.map(get_ndvi_value)
        time_series = time_series_collection.getInfo()
        
        # Extract time series features
        time_series_data = [
            f['properties'] for f in time_series['features']
            if f['properties'].get('ndvi') is not None
        ]
        
        # Sort by date
        time_series_data.sort(key=lambda x: x['date'])
        
        # Calculate average cloud coverage
        avg_cloud = collection.aggregate_mean('CLOUDY_PIXEL_PERCENTAGE').getInfo()
        
        # Prepare response
        response = {
            'ndvi_mean': round(stats.get('NDVI_mean', 0), 4),
            'ndvi_std': round(stats.get('NDVI_stdDev', 0), 4),
            'ndvi_time_series': time_series_data,
            'cloud_coverage_pct': round(avg_cloud, 2) if avg_cloud else 0,
            'image_count': count,
            'period': {
                'start': start_date,
                'end': end_date
            },
            'area_ha': round(geometry.area().divide(10000).getInfo(), 2)
        }
        
        return jsonify(response), 200
        
    except ee.EEException as e:
        return jsonify({
            'error': 'Earth Engine error',
            'message': str(e)
        }), 500
    except Exception as e:
        return jsonify({
            'error': 'Internal server error',
            'message': str(e)
        }), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'ndvi-calculator',
        'timestamp': datetime.utcnow().isoformat()
    }), 200


@app.route('/', methods=['GET'])
def root():
    """Root endpoint with API information."""
    return jsonify({
        'service': 'NDVI Calculator',
        'version': '1.0.0',
        'endpoints': {
            '/calculate-ndvi': 'POST - Calculate NDVI for an area',
            '/health': 'GET - Health check'
        },
        'documentation': 'https://github.com/christianfarjat/afolu-gee-cloudrun-api'
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
