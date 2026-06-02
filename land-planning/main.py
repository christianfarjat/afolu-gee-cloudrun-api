"""ForestScan - Land Planning tier.

Land-use planning support: suitability and zoning analysis for a parcel based
on current land cover (ESA WorldCover) and terrain slope (SRTM DEM), driven by
a planning objective (restoration, conservation or production).

Each parcel is split into three zones — suitable / restricted / excluded —
whose rules depend on the objective.

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

SERVICE_NAME = "forestscan-land-planning"
VERSION = "1.0.0"

ESA_WORLDCOVER = os.environ.get("ESA_WORLDCOVER", "ESA/WorldCover/v200")
DEM_DATASET = os.environ.get("DEM_DATASET", "USGS/SRTMGL1_003")

VALID_OBJECTIVES = ("restoration", "conservation", "production")

# Slope thresholds in degrees.
SLOPE_MODERATE = 15
SLOPE_STEEP = 30

# ESA WorldCover class codes.
CLS_TREE, CLS_SHRUB, CLS_GRASS, CLS_CROP, CLS_BUILT = 10, 20, 30, 40, 50
CLS_BARE, CLS_SNOW, CLS_WATER, CLS_WETLAND, CLS_MANGROVE, CLS_MOSS = (
    60, 70, 80, 90, 95, 100,
)


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


def _zone_masks(landcover, slope, objective):
    """Build (suitable, restricted, excluded) boolean masks for an objective.

    - restoration: restore degraded/open land; exclude built-up & water,
      keep steep slopes as restricted, suitable = open non-forest land.
    - conservation: protect existing natural vegetation; exclude
      built/cropland/water, suitable = forest/wetland/mangrove.
    - production: favor arable land on gentle slopes; exclude forest, water,
      built and wetlands, restricted = moderate-to-steep slopes.
    """
    is_built = landcover.eq(CLS_BUILT)
    is_water = landcover.eq(CLS_WATER)
    is_forest = landcover.eq(CLS_TREE).Or(landcover.eq(CLS_MANGROVE))
    is_wetland = landcover.eq(CLS_WETLAND)
    is_crop = landcover.eq(CLS_CROP)
    is_open = (
        landcover.eq(CLS_SHRUB)
        .Or(landcover.eq(CLS_GRASS))
        .Or(landcover.eq(CLS_BARE))
    )

    steep = slope.gt(SLOPE_STEEP)
    moderate_or_steep = slope.gt(SLOPE_MODERATE)

    if objective == "conservation":
        excluded = is_built.Or(is_water).Or(is_crop)
        suitable = is_forest.Or(is_wetland)
        restricted = excluded.Not().And(suitable.Not())
    elif objective == "production":
        excluded = is_forest.Or(is_water).Or(is_built).Or(is_wetland)
        restricted = excluded.Not().And(moderate_or_steep)
        suitable = excluded.Not().And(moderate_or_steep.Not())
    else:  # restoration (default)
        excluded = is_built.Or(is_water)
        restricted = excluded.Not().And(steep)
        suitable = excluded.Not().And(steep.Not()).And(is_open.Or(is_crop))

    return suitable, restricted, excluded


@app.route('/land-planning', methods=['POST'])
@require_google_auth
def land_planning():
    """Produce a land-use planning / suitability assessment for a parcel.

    Request body:
    {
        "geometry": {"type": "Polygon", "coordinates": [...]},
        "objective": "restoration",   // restoration | conservation | production
        "scale": 30                   // optional, analysis scale in meters
    }
    """
    try:
        data = request.get_json()
        if not data or 'geometry' not in data:
            return jsonify({'error': 'Missing required field: geometry'}), 400

        ee_geometry = ee.Geometry(data['geometry'])
        objective = (data.get('objective') or 'restoration').lower()
        if objective not in VALID_OBJECTIVES:
            return jsonify({
                'error': f"Invalid objective '{objective}'. "
                         f"Valid: {', '.join(VALID_OBJECTIVES)}"
            }), 400
        scale = data.get('scale', 30)

        area_ha = round(ee_geometry.area().divide(10000).getInfo(), 2)

        landcover = ee.ImageCollection(ESA_WORLDCOVER).first().select('Map')
        slope = ee.Terrain.slope(ee.Image(DEM_DATASET))

        mean_slope = slope.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=ee_geometry,
            scale=scale,
            maxPixels=1e13,
            bestEffort=True,
        ).getInfo().get('slope')
        mean_slope_deg = round(mean_slope, 2) if mean_slope is not None else None

        suitable, restricted, excluded = _zone_masks(landcover, slope, objective)

        area_img = ee.Image.pixelArea().divide(10000)
        zones_img = (
            area_img.updateMask(suitable).rename('suitable_ha')
            .addBands(area_img.updateMask(restricted).rename('restricted_ha'))
            .addBands(area_img.updateMask(excluded).rename('excluded_ha'))
        )
        stats = zones_img.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=ee_geometry,
            scale=scale,
            maxPixels=1e13,
            bestEffort=True,
        ).getInfo()

        def _pct(ha):
            return round(ha / area_ha * 100, 2) if area_ha else 0.0

        zones = []
        for name in ('suitable', 'restricted', 'excluded'):
            ha = round(stats.get(f'{name}_ha') or 0.0, 2)
            zones.append({'zone': name, 'area_ha': ha, 'area_pct': _pct(ha)})

        response = {
            'status': 'ok',
            'tier': 'land_planning',
            'authenticated_user': get_current_user(),
            'objective': objective,
            'area_ha': area_ha,
            'mean_slope_deg': mean_slope_deg,
            'zones': zones,
            'methodology': (
                f'ESA WorldCover ({ESA_WORLDCOVER}) + slope from {DEM_DATASET}'
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
