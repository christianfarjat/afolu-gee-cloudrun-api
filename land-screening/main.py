"""ForestScan - Land Screening tier.

Initial screening of a parcel: quick land cover snapshot and a preliminary
deforestation/risk overview to decide whether a deeper analysis (EUDR, Land
Planning) is warranted.

This is a SKELETON: the GEE wiring and endpoints are in place; the analysis
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

SERVICE_NAME = "forestscan-land-screening"
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


@app.route('/land-screening', methods=['POST'])
def land_screening():
    """Run a preliminary land screening for a parcel.

    Request body:
    {
        "geometry": {"type": "Polygon", "coordinates": [...]},
        "year": 2023
    }

    Response (skeleton placeholder):
    {
        "status": "skeleton",
        "tier": "land_screening",
        "area_ha": 150.5,
        "summary": {...}
    }
    """
    try:
        data = request.get_json()
        if not data or 'geometry' not in data:
            return jsonify({'error': 'Missing required field: geometry'}), 400

        ee_geometry = ee.Geometry(data['geometry'])
        year = data.get('year', datetime.utcnow().year)

        area_ha = round(ee_geometry.area().divide(10000).getInfo(), 2)

        # TODO: implement screening logic, e.g.:
        #   - dominant land cover (ESA WorldCover)
        #   - tree-cover share and recent loss (Hansen GFC)
        #   - preliminary deforestation-risk flag
        response = {
            'status': 'skeleton',
            'tier': 'land_screening',
            'year': year,
            'area_ha': area_ha,
            'summary': {
                'message': 'Land Screening skeleton: analysis not yet implemented',
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
        'service': 'ForestScan - Land Screening',
        'version': VERSION,
        'endpoints': {
            '/land-screening': 'POST - Preliminary land screening for a parcel',
            '/health': 'GET - Health check',
        },
        'documentation': 'https://github.com/christianfarjat/afolu-gee-cloudrun-api',
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
