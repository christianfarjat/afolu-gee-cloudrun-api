"""ForestScan - EUDR tier.

EU Deforestation Regulation (EUDR) compliance check: determines whether a
production plot shows forest loss AFTER the regulation cutoff date
(2020-12-31). Plots with deforestation after the cutoff are non-compliant.

Methodology (Hansen Global Forest Change):
  - Forest baseline = pixels with tree canopy cover >= threshold that were
    still forest at the end of the cutoff year (no loss before/at cutoff).
  - Deforestation after cutoff = baseline forest pixels whose `lossyear` is
    later than the cutoff year.
  - compliant = (deforestation_after_cutoff_ha ~= 0).

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

SERVICE_NAME = "forestscan-eudr"
VERSION = "1.0.0"

# EUDR deforestation cutoff date.
EUDR_CUTOFF_DATE = "2020-12-31"

# Hansen Global Forest Change dataset (year of loss encoded in `lossyear`).
HANSEN_DATASET = os.environ.get(
    "HANSEN_DATASET", "UMD/hansen/global_forest_change_2023_v1_11"
)

# Default minimum tree canopy cover (%) to consider a pixel as forest.
DEFAULT_CANOPY_THRESHOLD = 10

# Tolerance in hectares below which deforestation is treated as zero (noise).
COMPLIANCE_TOLERANCE_HA = 0.01


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
@require_google_auth
def eudr_check():
    """Check EUDR compliance for a production plot.

    Request body:
    {
        "geometry": {"type": "Polygon", "coordinates": [...]},
        "commodity": "cattle",            // optional, metadata only
        "cutoff_date": "2020-12-31",      // optional, defaults to EUDR cutoff
        "canopy_threshold": 10,           // optional, % canopy cover for forest
        "scale": 30                       // optional, analysis scale in meters
    }

    Response:
    {
        "status": "ok",
        "tier": "eudr",
        "compliant": false,
        "cutoff_date": "2020-12-31",
        "area_ha": 150.5,
        "forest_baseline_ha": 120.3,
        "deforestation_after_cutoff_ha": 5.0,
        "deforestation_by_year_ha": {"2021": 3.5, "2022": 1.5},
        "methodology": "Hansen GFC ...",
        ...
    }
    """
    try:
        data = request.get_json()
        if not data or 'geometry' not in data:
            return jsonify({'error': 'Missing required field: geometry'}), 400

        ee_geometry = ee.Geometry(data['geometry'])
        commodity = data.get('commodity')
        cutoff_date = data.get('cutoff_date', EUDR_CUTOFF_DATE)
        canopy_threshold = data.get('canopy_threshold', DEFAULT_CANOPY_THRESHOLD)
        scale = data.get('scale', 30)  # Hansen native resolution is ~30 m

        # Cutoff year -> Hansen `lossyear` code (years since 2000).
        cutoff_year = int(str(cutoff_date)[:4])
        cutoff_code = cutoff_year - 2000

        area_ha = round(ee_geometry.area().divide(10000).getInfo(), 2)

        # --- Hansen Global Forest Change layers -----------------------------
        gfc = ee.Image(HANSEN_DATASET)
        treecover = gfc.select('treecover2000')
        loss = gfc.select('loss')
        lossyear = gfc.select('lossyear')

        # Forest still standing at the end of the cutoff year:
        #   canopy >= threshold AND (never lost OR lost after the cutoff year).
        forest_at_cutoff = treecover.gte(canopy_threshold).And(
            loss.eq(0).Or(lossyear.gt(cutoff_code))
        )

        # Deforestation after the cutoff within that baseline forest.
        defor_after = forest_at_cutoff.And(lossyear.gt(cutoff_code))

        # Per-pixel area in hectares.
        area_img = ee.Image.pixelArea().divide(10000)

        # Single reduceRegion for baseline + deforestation areas.
        bands = (
            area_img.updateMask(forest_at_cutoff).rename('forest_baseline_ha')
            .addBands(area_img.updateMask(defor_after).rename('deforestation_after_cutoff_ha'))
        )
        stats = bands.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=ee_geometry,
            scale=scale,
            maxPixels=1e13,
            bestEffort=True,
        ).getInfo()

        forest_baseline_ha = round(stats.get('forest_baseline_ha') or 0.0, 2)
        defor_after_ha = round(stats.get('deforestation_after_cutoff_ha') or 0.0, 2)

        # Per-year breakdown of deforestation after the cutoff.
        year_img = area_img.updateMask(defor_after).addBands(lossyear)
        grouped = year_img.reduceRegion(
            reducer=ee.Reducer.sum().group(groupField=1, groupName='year_code'),
            geometry=ee_geometry,
            scale=scale,
            maxPixels=1e13,
            bestEffort=True,
        ).getInfo()

        defor_by_year = {}
        for group in grouped.get('groups', []):
            year_code = group.get('year_code')
            if year_code is None:
                continue
            year = 2000 + int(year_code)
            defor_by_year[str(year)] = round(group.get('sum') or 0.0, 2)

        compliant = defor_after_ha <= COMPLIANCE_TOLERANCE_HA

        response = {
            'status': 'ok',
            'tier': 'eudr',
            'authenticated_user': get_current_user(),
            'commodity': commodity,
            'cutoff_date': cutoff_date,
            'area_ha': area_ha,
            'canopy_threshold_pct': canopy_threshold,
            'forest_baseline_ha': forest_baseline_ha,
            'deforestation_after_cutoff_ha': defor_after_ha,
            'deforestation_by_year_ha': defor_by_year,
            'compliant': compliant,
            'methodology': f'Hansen Global Forest Change ({HANSEN_DATASET})',
            'summary': {
                'message': (
                    'EUDR compliant: no forest loss detected after cutoff'
                    if compliant else
                    f'NOT EUDR compliant: {defor_after_ha} ha of forest loss '
                    f'detected after {cutoff_date}'
                ),
            },
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
