#!/bin/bash

# AFOLU GEE Cloud Run APIs - Local Environment Setup Script
# This script automates the local testing environment configuration

set -e

echo "========================================"
echo "AFOLU GEE Cloud Run APIs - Setup Local"
echo "========================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Project configuration
PROJECT_ID="forestproject-copilot-ia"
SERVICE_ACCOUNT="forestblock-gge@forestproject-copilot-ia.iam.gserviceaccount.com"
SECRET_NAME="gee-service-account"

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Step 1: Check prerequisites
echo "${YELLOW}[1/6] Verificando prerequisitos...${NC}"

if ! command_exists python3; then
    echo "${RED}Error: Python 3 no está instalado${NC}"
    exit 1
fi

if ! command_exists gcloud; then
    echo "${RED}Error: Google Cloud SDK no está instalado${NC}"
    echo "Instalar desde: https://cloud.google.com/sdk/docs/install"
    exit 1
fi

echo "${GREEN}✓ Python 3 y gcloud CLI disponibles${NC}"
echo ""

# Step 2: Authenticate with Google Cloud
echo "${YELLOW}[2/6] Configurando autenticación Google Cloud...${NC}"

# Check if already authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo "Iniciando autenticación..."
    gcloud auth login
else
    echo "${GREEN}✓ Ya autenticado con Google Cloud${NC}"
fi

# Set project
gcloud config set project $PROJECT_ID
echo "${GREEN}✓ Proyecto configurado: $PROJECT_ID${NC}"
echo ""

# Step 3: Setup Earth Engine authentication
echo "${YELLOW}[3/6] Configurando Google Earth Engine...${NC}"

# Install earthengine-api if not present
if ! python3 -c "import ee" 2>/dev/null; then
    echo "Instalando earthengine-api..."
    pip3 install earthengine-api
fi

# Authenticate with Earth Engine
if [ ! -f "$HOME/.config/earthengine/credentials" ]; then
    echo "Iniciando autenticación Earth Engine..."
    earthengine authenticate
else
    echo "${GREEN}✓ Earth Engine ya autenticado${NC}"
fi

echo ""

# Step 4: Create virtual environment and install dependencies
echo "${YELLOW}[4/6] Configurando entorno virtual Python...${NC}"

if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "${GREEN}✓ Entorno virtual creado${NC}"
else
    echo "${GREEN}✓ Entorno virtual ya existe${NC}"
fi

source venv/bin/activate

echo "Instalando dependencias para todos los servicios..."
pip install --upgrade pip

# Install common dependencies
pip install earthengine-api flask google-cloud-secret-manager requests

echo "${GREEN}✓ Dependencias instaladas${NC}"
echo ""

# Step 5: Retrieve service account credentials from Secret Manager
echo "${YELLOW}[5/6] Recuperando credenciales desde Secret Manager...${NC}"

CREDS_FILE="service-account-key.json"

if [ -f "$CREDS_FILE" ]; then
    echo "${YELLOW}⚠ Archivo de credenciales ya existe: $CREDS_FILE${NC}"
    read -p "¿Descargar nuevamente? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Usando archivo existente"
    else
        gcloud secrets versions access latest --secret="$SECRET_NAME" --project="$PROJECT_ID" > "$CREDS_FILE"
        echo "${GREEN}✓ Credenciales actualizadas${NC}"
    fi
else
    echo "Descargando credenciales..."
    gcloud secrets versions access latest --secret="$SECRET_NAME" --project="$PROJECT_ID" > "$CREDS_FILE"
    echo "${GREEN}✓ Credenciales descargadas${NC}"
fi

# Set environment variable
export GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/$CREDS_FILE"
echo "${GREEN}✓ Variable GOOGLE_APPLICATION_CREDENTIALS configurada${NC}"
echo ""

# Step 6: Create test script
echo "${YELLOW}[6/6] Creando script de pruebas...${NC}"

cat > test_apis_local.py << 'EOF'
#!/usr/bin/env python3
"""Script de pruebas para las APIs de AFOLU GEE localmente"""

import os
import sys
import json
import ee
from google.cloud import secretmanager

def test_gee_authentication():
    """Prueba la autenticación con Google Earth Engine"""
    print("\n[TEST] Autenticación Google Earth Engine...")
    try:
        # Try to use service account from credentials file
        credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if credentials_path:
            with open(credentials_path, 'r') as f:
                credentials = json.load(f)
            service_account = credentials['client_email']
            ee.Initialize(ee.ServiceAccountCredentials(service_account, credentials_path))
            print("✓ Autenticado con Service Account:", service_account)
        else:
            # Fallback to user authentication
            ee.Initialize()
            print("✓ Autenticado con credenciales de usuario")
        
        # Test basic GEE operation
        image = ee.Image('COPERNICUS/S2/20210401T100031_20210401T100037_T33UUP')
        info = image.getInfo()
        print("✓ Operación básica GEE exitosa")
        return True
    except Exception as e:
        print("✗ Error:", str(e))
        return False

def test_secret_manager():
    """Prueba el acceso a Secret Manager"""
    print("\n[TEST] Acceso a Secret Manager...")
    try:
        client = secretmanager.SecretManagerServiceClient()
        project_id = 'forestproject-copilot-ia'
        secret_name = f"projects/{project_id}/secrets/gee-service-account/versions/latest"
        
        response = client.access_secret_version(request={"name": secret_name})
        credentials = json.loads(response.payload.data.decode('UTF-8'))
        
        print("✓ Secret Manager accesible")
        print("✓ Service Account Email:", credentials.get('client_email'))
        return True
    except Exception as e:
        print("✗ Error:", str(e))
        return False

def test_ndvi_calculation():
    """Prueba el cálculo de NDVI"""
    print("\n[TEST] Cálculo NDVI...")
    try:
        # Sample coordinates (Costa Rica)
        coords = [-84.0, 10.0, -83.5, 10.5]
        start_date = '2023-01-01'
        end_date = '2023-12-31'
        
        # Get Sentinel-2 collection
        collection = ee.ImageCollection('COPERNICUS/S2_SR') \
            .filterBounds(ee.Geometry.Rectangle(coords)) \
            .filterDate(start_date, end_date) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
        
        count = collection.size().getInfo()
        print(f"✓ Encontradas {count} imágenes Sentinel-2")
        
        if count > 0:
            # Calculate NDVI for first image
            image = ee.Image(collection.first())
            ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
            stats = ndvi.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=ee.Geometry.Rectangle(coords),
                scale=10,
                maxPixels=1e9
            ).getInfo()
            print("✓ NDVI medio calculado:", stats.get('NDVI'))
        
        return True
    except Exception as e:
        print("✗ Error:", str(e))
        return False

def test_landcover():
    """Prueba el acceso a datos de cobertura terrestre"""
    print("\n[TEST] Cobertura Terrestre (ESA WorldCover)...")
    try:
        coords = [-84.0, 10.0, -83.5, 10.5]
        
        # Get ESA WorldCover
        landcover = ee.ImageCollection('ESA/WorldCover/v200').first()
        
        # Calculate land cover statistics
        stats = landcover.reduceRegion(
            reducer=ee.Reducer.frequencyHistogram(),
            geometry=ee.Geometry.Rectangle(coords),
            scale=10,
            maxPixels=1e9
        ).getInfo()
        
        print("✓ Datos de cobertura terrestre obtenidos")
        print("✓ Clases encontradas:", len(stats.get('Map', {})))
        return True
    except Exception as e:
        print("✗ Error:", str(e))
        return False

def test_biomass():
    """Prueba el acceso a datos de biomasa"""
    print("\n[TEST] Biomasa (MODIS NPP)...")
    try:
        coords = [-84.0, 10.0, -83.5, 10.5]
        start_date = '2023-01-01'
        end_date = '2023-12-31'
        
        # Get MODIS NPP data
        collection = ee.ImageCollection('MODIS/006/MOD17A2H') \
            .filterBounds(ee.Geometry.Rectangle(coords)) \
            .filterDate(start_date, end_date)
        
        count = collection.size().getInfo()
        print(f"✓ Encontradas {count} imágenes MODIS NPP")
        
        if count > 0:
            # Calculate mean NPP
            image = collection.select('Npp').mean()
            stats = image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=ee.Geometry.Rectangle(coords),
                scale=500,
                maxPixels=1e9
            ).getInfo()
            print("✓ NPP medio calculado:", stats.get('Npp'))
        
        return True
    except Exception as e:
        print("✗ Error:", str(e))
        return False

if __name__ == '__main__':
    print("="*50)
    print("AFOLU GEE APIs - Suite de Pruebas Local")
    print("="*50)
    
    results = {
        'GEE Authentication': test_gee_authentication(),
        'Secret Manager': test_secret_manager(),
        'NDVI Calculation': test_ndvi_calculation(),
        'Land Cover': test_landcover(),
        'Biomass': test_biomass()
    }
    
    print("\n" + "="*50)
    print("RESUMEN DE PRUEBAS")
    print("="*50)
    
    passed = sum(results.values())
    total = len(results)
    
    for test, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{test:25} {status}")
    
    print("\n" + "="*50)
    print(f"Total: {passed}/{total} pruebas exitosas")
    print("="*50)
    
    sys.exit(0 if passed == total else 1)
EOF

chmod +x test_apis_local.py
echo "${GREEN}✓ Script de pruebas creado: test_apis_local.py${NC}"
echo ""

# Summary
echo "${GREEN}========================================${NC}"
echo "${GREEN}✓ CONFIGURACIÓN COMPLETADA${NC}"
echo "${GREEN}========================================${NC}"
echo ""
echo "Próximos pasos:"
echo "  1. Activar entorno virtual: source venv/bin/activate"
echo "  2. Ejecutar pruebas: python3 test_apis_local.py"
echo "  3. Para servicios individuales:"
echo "     - NDVI: cd ndvi && python main.py"
echo "     - Land Cover: cd landcover && python main.py"
echo "     - Biomass: cd biomass && python main.py"
echo ""
echo "Variables de entorno configuradas:"
echo "  GOOGLE_APPLICATION_CREDENTIALS=$GOOGLE_APPLICATION_CREDENTIALS"
echo ""
echo "${YELLOW}Nota: Asegúrate de que el administrador haya configurado el secreto${NC}"
echo "${YELLOW}      'gee-service-account' en Secret Manager con las credenciales.${NC}"
echo ""
