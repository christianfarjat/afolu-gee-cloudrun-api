# AFOLU GEE Cloud Run APIs

Google Earth Engine APIs for AFOLU Carbon Analysis deployed on Google Cloud Run. These serverless webhooks provide geospatial analysis capabilities for the AFOLU Carbon Analysis Workflow.

## 🌍 Overview

This project provides three main endpoints for satellite-based carbon analysis:

1. **NDVI Calculation** - Normalized Difference Vegetation Index from Sentinel-2
2. **Land Cover Analysis** - ESA WorldCover and MODIS land cover classification
3. **Biomass Estimation** - Above-ground biomass and carbon stock calculations

## 📐 Architecture

```
OpenAI Agent (AFOLU_Geospatial)
    ↓ HTTP POST
Cloud Run Endpoints
    ↓ GEE Python API  
Google Earth Engine
    ↓ Satellite Processing
JSON Results → Agent
```

## 🚀 Endpoints

### 1. Calculate NDVI
**POST** `/calculate-ndvi`

**Input:**
```json
{
  "geometry": {"type": "Polygon", "coordinates": [...]},
  "start_date": "2023-01-01",
  "end_date": "2023-12-31"
}
```

**Output:**
```json
{
  "ndvi_mean": 0.65,
  "ndvi_time_series": [...],
  "cloud_coverage_pct": 15.2
}
```

### 2. Get Land Cover
**POST** `/get-landcover`

**Input:**
```json
{
  "geometry": {"type": "Polygon", "coordinates": [...]},
  "year": 2023
}
```

**Output:**
```json
{
  "land_cover": {
    "forest": 45.2,
    "grassland": 35.8,
    "cropland": 19.0
  },
  "total_area_ha": 150.5
}
```

### 3. Calculate Biomass
**POST** `/calculate-biomass`

**Input:**
```json
{
  "geometry": {"type": "Polygon", "coordinates": [...]},
  "project_type": "Silvopastoreo",
  "year": 2023
}
```

**Output:**
```json
{
  "biomass_kg_ha": 12500,
  "carbon_tco2e": 23.1,
  "methodology": "MODIS_NPP_converted"
}
```

## 📁 Project Structure

```
afolu-gee-cloudrun-api/
├── ndvi/
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── landcover/
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── biomass/
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── shared/
│   └── gee_utils.py
└── deploy.sh
```

## 🛠️ Setup

### Prerequisites

1. Google Cloud Project with:
   - Earth Engine API enabled
   - Cloud Run API enabled
   - Secret Manager API enabled

2. Local dependencies:
```bash
# Install gcloud CLI
curl https://sdk.cloud.google.com | bash

# Authenticate
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Authenticate Earth Engine
earthengine authenticate
```

### Deployment

1. Clone repository:
```bash
git clone https://github.com/christianfarjat/afolu-gee-cloudrun-api.git
cd afolu-gee-cloudrun-api
```

2. Deploy all services:
```bash
bash deploy.sh
```

Or deploy individually:
```bash
# NDVI service
cd ndvi
gcloud run deploy ndvi-service \
  --source . \
  --region us-central1 \
  --allow-unauthenticated

# Repeat for landcover and biomass
```

## 🔐 Authentication

There are two independent layers of authentication:

**1. GEE backend auth** — The services use Google Application Default Credentials (ADC) for GEE authentication. In Cloud Run, this is automatically handled by the service account.

For local development:
```bash
gcloud auth application-default login
```

**2. User access (ForestScan tiers)** — Each ForestScan tier (Land Screening, EUDR, Land Planning) is protected with **Cloud IAP**, so users log in with their **Google Workspace email** (`@mjmenergia.com`). IAP validates identity before the request reaches Cloud Run, with no code changes and no load balancer.

```bash
bash tools/setup_iap.sh
```

See [`docs/IAP_AUTH.md`](docs/IAP_AUTH.md) for the full setup and operations guide.

## 💰 Costs

- **Cloud Run**: ~$0.001/request (2M free requests/month)
- **Earth Engine**: Free for research and non-commercial use
- **Estimated**: <$5/month for development/testing

## 🧪 Testing

```bash
# Test NDVI endpoint locally
curl -X POST http://localhost:8080/calculate-ndvi \
  -H "Content-Type: application/json" \
  -d '{"geometry": {...}, "start_date": "2023-01-01", "end_date": "2023-12-31"}'
```

## 📊 Integration with OpenAI Agent Builder

These endpoints are designed to be used as MCP custom tools in the AFOLU_Geospatial agent:

1. Get the Cloud Run URLs after deployment
2. In OpenAI Agent Builder, add MCP custom tools
3. Configure each endpoint with its Cloud Run URL
4. The agent can now call these APIs for geospatial analysis

## 📝 License

MIT License - see LICENSE file for details

## 🤝 Contributing

Contributions welcome! Please open an issue or PR.

## 📧 Contact

For questions about this project, please open an issue on GitHub.
