"""ForestScan - Land Screening tier.

Initial screening of a parcel: a quick land-cover snapshot plus a preliminary
deforestation-risk overview to decide whether a deeper analysis (EUDR, Land
Planning) is warranted.

Methodology:
  - Land cover distribution from ESA WorldCover (10 m).
  - Tree-cover share and recent forest loss from Hansen Global Forest Change.
  - Preliminary deforestation-risk flag based on recent loss vs parcel area.

Protected by Cloud IAP (login with Google Workspace email). See docs/IAP_AUTH.md.
"""

import os
import json
import ee
from datetime import datetime
from flask import Flask, request, jsonify
from google.cloud import secretmanager

from auth import require_google_auth, get_current_user

app = Flask(__name__)

SERVICE_NAME = "forestscan-land-screening"
VERSION = "1.0.0"

ESA_WORLDCOVER = os.environ.get("ESA_WORLDCOVER", "ESA/WorldCover/v200")
HANSEN_DATASET = os.environ.get(
    "HANSEN_DATASET", "UMD/hansen/global_forest_change_2023_v1_11"
)

# ESA WorldCover class codes -> readable names.
WORLDCOVER_CLASSES = {
    10: "tree_cover",
    20: "shrubland",
    30: "grassland",
    40: "cropland",
    50: "built_up",
    60: "bare_sparse_vegetation",
    70: "snow_ice",
    80: "water",
    90: "herbaceous_wetland",
    95: "mangroves",
    100: "moss_lichen",
}

# Years counted as "recent" for the deforestation-risk flag.
RECENT_LOSS_YEARS = 5

# Risk thresholds: recent forest loss as a share of parcel area.
RISK_HIGH_PCT = 5.0
RISK_MEDIUM_PCT = 1.0


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


def _risk_level(recent_loss_pct):
    """Map recent-loss share to a qualitative risk flag."""
    if recent_loss_pct >= RISK_HIGH_PCT:
        return "high"
    if recent_loss_pct >= RISK_MEDIUM_PCT:
        return "medium"
    return "low"


@app.route('/land-screening', methods=['POST'])
@require_google_auth
def land_screening():
    """Run a preliminary land screening for a parcel.

    Request body:
    {
        "geometry": {"type": "Polygon", "coordinates": [...]},
        "year": 2023,            // optional, reference year for recent loss
        "scale": 10              // optional, analysis scale in meters
    }
    """
    try:
        data = request.get_json()
        if not data or 'geometry' not in data:
            return jsonify({'error': 'Missing required field: geometry'}), 400

        ee_geometry = ee.Geometry(data['geometry'])
        year = int(data.get('year', 2023))
        scale = data.get('scale', 10)

        area_ha = round(ee_geometry.area().divide(10000).getInfo(), 2)

        # --- Land cover distribution (ESA WorldCover) -----------------------
        worldcover = ee.ImageCollection(ESA_WORLDCOVER).first().select('Map')
        histogram = worldcover.reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=ee_geometry,
            scale=scale,
            maxPixels=1e13,
            bestEffort=True,
        ).getInfo().get('Map', {}) or {}

        total_px = sum(float(v) for v in histogram.values()) or 1.0
        land_cover_pct = {}
        for code, count in histogram.items():
            name = WORLDCOVER_CLASSES.get(int(code), f"class_{code}")
            land_cover_pct[name] = round(float(count) / total_px * 100, 2)

        dominant_class = (
            max(land_cover_pct, key=land_cover_pct.get) if land_cover_pct else None
        )
        tree_cover_pct = land_cover_pct.get('tree_cover', 0.0)

        # --- Recent forest loss (Hansen GFC) --------------------------------
        gfc = ee.Image(HANSEN_DATASET)
        lossyear = gfc.select('lossyear')
        recent_threshold = (year - 2000) - RECENT_LOSS_YEARS
        recent_loss = lossyear.gt(recent_threshold)

        area_img = ee.Image.pixelArea().divide(10000)
        recent_loss_ha = (
            area_img.updateMask(recent_loss).rename('recent_loss_ha')
            .reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=ee_geometry,
                scale=30,
                maxPixels=1e13,
                bestEffort=True,
            ).getInfo().get('recent_loss_ha') or 0.0
        )
        recent_loss_ha = round(recent_loss_ha, 2)
        recent_loss_pct = round(recent_loss_ha / area_ha * 100, 2) if area_ha else 0.0

        response = {
            'status': 'ok',
            'tier': 'land_screening',
            'authenticated_user': get_current_user(),
            'year': year,
            'area_ha': area_ha,
            'land_cover_pct': land_cover_pct,
            'dominant_class': dominant_class,
            'tree_cover_pct': tree_cover_pct,
            'recent_forest_loss_ha': recent_loss_ha,
            'recent_forest_loss_pct': recent_loss_pct,
            'recent_loss_window_years': RECENT_LOSS_YEARS,
            'deforestation_risk': _risk_level(recent_loss_pct),
            'methodology': (
                f'ESA WorldCover ({ESA_WORLDCOVER}) + '
                f'Hansen GFC ({HANSEN_DATASET})'
            ),
        }
        return jsonify(response), 200

    except ee.EEException as e:
        return jsonify({'error': 'Earth Engine error', 'message': str(e)}), 500
    except Exception as e:
        return jsonify({'error': 'Internal server error', 'message': str(e)}), 500


@app.route('/whoami', methods=['GET'])
@require_google_auth
def whoami():
    """Return the Google Workspace identity authenticated by Cloud IAP."""
    return jsonify({'authenticated_user': get_current_user()}), 200


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
