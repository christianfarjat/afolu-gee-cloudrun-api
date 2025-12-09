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

@app.route('/calculate-biomass', methods=['POST'])
def calculate_biomass():
    """Calculate above-ground biomass and carbon stock for a given geometry."""
    try:
        data = request.get_json()
        
        # Validate input
        if not data or 'geometry' not in data:
            return jsonify({'error': 'Missing geometry in request'}), 400
        
        geometry_data = data['geometry']
        project_type = data.get('project_type', 'Silvopastoreo')  # Default project type
        year = data.get('year', 2023)
        
        # Convert GeoJSON to Earth Engine geometry
        ee_geometry = ee.Geometry(geometry_data)
        
        # Get area in hectares
        area_m2 = ee_geometry.area().getInfo()
        area_ha = area_m2 / 10000
        
        # Use MODIS NPP (Net Primary Production) as a proxy for biomass
        # MODIS/006/MOD17A3HGF provides annual NPP
        npp_dataset = ee.ImageCollection('MODIS/006/MOD17A3HGF') \
            .filterDate(f'{year}-01-01', f'{year}-12-31') \
            .select('Npp')
        
        # Get mean NPP for the area
        npp_image = npp_dataset.mean()
        
        # Calculate mean NPP (kg C/m²/year) - note: MODIS NPP is in kg C/m²/year * 0.0001
        npp_stats = npp_image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=ee_geometry,
            scale=500,  # MODIS resolution
            maxPixels=1e9
        ).getInfo()
        
        # Get NPP value and convert
        npp_value = npp_stats.get('Npp', 0) * 0.0001  # Convert to kg C/m²/year
        
        # Convert NPP to biomass estimate
        # Rough conversion: NPP to total biomass using a factor
        # This is a simplified approach - actual conversion depends on ecosystem type
        biomass_conversion_factor = 2.5  # Typical factor to convert NPP to standing biomass
        biomass_kg_m2 = npp_value * biomass_conversion_factor
        biomass_kg_ha = biomass_kg_m2 * 10000  # Convert to per hectare
        
        # Calculate total biomass for the area
        total_biomass_kg = biomass_kg_ha * area_ha
        
        # Convert biomass to carbon stock
        # Carbon content is typically ~50% of dry biomass
        carbon_content_factor = 0.5
        carbon_stock_kg = total_biomass_kg * carbon_content_factor
        
        # Convert carbon to CO2 equivalent
        # CO2 = C * (44/12) where 44 is molecular weight of CO2, 12 is atomic weight of C
        co2_factor = 44/12
        carbon_tco2e = (carbon_stock_kg / 1000) * co2_factor  # Convert kg to tonnes and to CO2e
        
        response = {
            'biomass_kg_ha': round(biomass_kg_ha, 2),
            'total_biomass_kg': round(total_biomass_kg, 2),
            'carbon_stock_kg': round(carbon_stock_kg, 2),
            'carbon_tco2e': round(carbon_tco2e, 2),
            'area_ha': round(area_ha, 2),
            'npp_kg_c_m2_year': round(npp_value, 4),
            'project_type': project_type,
            'year': year,
            'methodology': 'MODIS_NPP_converted',
            'data_source': 'MODIS/006/MOD17A3HGF',
            'notes': 'Biomass estimated from MODIS NPP using standard conversion factors'
        }
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Error in calculate_biomass: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'healthy', 'service': 'biomass'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
