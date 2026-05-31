"""ForestScan - Land Planning tier.

Land-use planning support: suitability and zoning analysis for a parcel
(e.g. areas suitable for restoration, conservation or production) based on
land cover, slope and other constraints.

This is a SKELETON: the GEE wiring and endpoints are in place; the planning
logic is marked with TODO and currently returns a structured placeholder.

Protected by Cloud IAP (login with Google Workspace email). See docs/IAP_AUTH.md.
"""

import os
import json
import ee
from datetime import datetime
from flask import Flask, request, jsonify
from google.cloud import secretmanager

app = Flask(__name__)

SERVICE_NAME = "forestscan-land-planning"
VERSION = "0.1.0"


def initialize_ee():
    """Initialize Earth Engine with default credentials or a service account."""
    try:
        ee.Initialize()
        print("Earth Engine initialized with default credentials")
    except Exception as e:
        print(f"Failed to initialize with default credentials: {e}")
        try:
            project_id = os.environ.get('GCP_PROJECT', 'forestproject-copilot-ia')
            client = secretmanager.SecretManagerServiceClient()
            secret_name = f"projects/{project_id}/secrets/gee-service-account/versions/latest"
            response = client.access_secret_version(request={"name": secret_name})
            credentials_json = response.payload.data.decode('UTF-8')
            credentials = json.loads(credentials_json)
            ee_credentials = ee.ServiceAccountCredentials(
                credentials['client_email'], key_data=credentials_json
            )
            ee.Initialize(ee_credentials)
            print("Earth Engine initialized with service account")
        except Exception as init_error:
            print(f"Failed to initialize Earth Engine: {init_error}")
            raise


initialize_ee()


@app.route('/land-planning', methods=['POST'])
def land_planning():
    """Produce a land-use planning / suitability assessment for a parcel.

    Request body:
    {
        "geometry": {"type": "Polygon", "coordinates": [...]},
        "objective": "restoration",   // restoration | conservation | production
        "year": 2023
    }

    Response (skeleton placeholder):
    {
        "status": "skeleton",
        "tier": "land_planning",
        "objective": "restoration",
        "zones": []
    }
    """
    try:
        data = request.get_json()
        if not data or 'geometry' not in data:
            return jsonify({'error': 'Missing required field: geometry'}), 400

        ee_geometry = ee.Geometry(data['geometry'])
        objective = data.get('objective', 'restoration')
        year = data.get('year', datetime.utcnow().year)

        area_ha = round(ee_geometry.area().divide(10000).getInfo(), 2)

        # TODO: implement planning logic, e.g.:
        #   - land cover (ESA WorldCover) + slope (SRTM/Copernicus DEM)
        #   - suitability scoring per objective
        #   - zoning into suitable / restricted / excluded areas
        response = {
            'status': 'skeleton',
            'tier': 'land_planning',
            'objective': objective,
            'year': year,
            'area_ha': area_ha,
            'zones': [],
            'summary': {
                'message': 'Land Planning skeleton: analysis not yet implemented',
            },
        }
        return jsonify(response), 200

    except ee.EEException as e:
        return jsonify({'error': 'Earth Engine error', 'message': str(e)}), 500
    except Exception as e:
        return jsonify({'error': 'Internal server error', 'message': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': SERVICE_NAME,
        'timestamp': datetime.utcnow().isoformat(),
    }), 200


@app.route('/', methods=['GET'])
def root():
    """Root endpoint with service information."""
    return jsonify({
        'service': 'ForestScan - Land Planning',
        'version': VERSION,
        'endpoints': {
            '/land-planning': 'POST - Land-use planning / suitability assessment',
            '/health': 'GET - Health check',
        },
        'documentation': 'https://github.com/christianfarjat/afolu-gee-cloudrun-api',
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
