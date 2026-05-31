"""ForestScan - EUDR tier.

EU Deforestation Regulation (EUDR) compliance check: determines whether a
production plot shows forest loss AFTER the regulation cutoff date
(2020-12-31). Plots with deforestation after the cutoff are non-compliant.

This is a SKELETON: the GEE wiring and endpoints are in place; the compliance
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

SERVICE_NAME = "forestscan-eudr"
VERSION = "0.1.0"

# EUDR deforestation cutoff date.
EUDR_CUTOFF_DATE = "2020-12-31"


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


@app.route('/eudr-check', methods=['POST'])
def eudr_check():
    """Check EUDR compliance for a production plot.

    Request body:
    {
        "geometry": {"type": "Polygon", "coordinates": [...]},
        "commodity": "cattle",
        "cutoff_date": "2020-12-31"   // optional, defaults to EUDR cutoff
    }

    Response (skeleton placeholder):
    {
        "status": "skeleton",
        "tier": "eudr",
        "compliant": null,
        "cutoff_date": "2020-12-31",
        "deforestation_after_cutoff_ha": null
    }
    """
    try:
        data = request.get_json()
        if not data or 'geometry' not in data:
            return jsonify({'error': 'Missing required field: geometry'}), 400

        ee_geometry = ee.Geometry(data['geometry'])
        commodity = data.get('commodity')
        cutoff_date = data.get('cutoff_date', EUDR_CUTOFF_DATE)

        area_ha = round(ee_geometry.area().divide(10000).getInfo(), 2)

        # TODO: implement EUDR compliance logic, e.g.:
        #   - forest baseline at cutoff date
        #   - forest loss after cutoff (Hansen GFC / JRC TMF / RADD alerts)
        #   - compliant = (deforestation_after_cutoff_ha == 0)
        response = {
            'status': 'skeleton',
            'tier': 'eudr',
            'commodity': commodity,
            'cutoff_date': cutoff_date,
            'area_ha': area_ha,
            'compliant': None,
            'deforestation_after_cutoff_ha': None,
            'summary': {
                'message': 'EUDR skeleton: compliance analysis not yet implemented',
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
        'service': 'ForestScan - EUDR',
        'version': VERSION,
        'endpoints': {
            '/eudr-check': 'POST - EUDR deforestation compliance check',
            '/health': 'GET - Health check',
        },
        'documentation': 'https://github.com/christianfarjat/afolu-gee-cloudrun-api',
    }), 200


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
