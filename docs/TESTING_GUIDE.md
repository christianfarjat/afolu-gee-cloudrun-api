# Guía de Pruebas - AFOLU GEE Cloud Run APIs

## 🔴 Estado Actual: BLOQUEADO

**Problema:** La política organizacional `iam.disableServiceAccountKeyCreation` impide crear claves JSON para la cuenta de servicio.

**Solución en progreso:** Ver `/docs/ADMIN_REQUEST.md` para la solicitud de excepción al administrador.

---

## 🧪 Opción 1: Pruebas Locales (Disponible Ahora)

Mientras se resuelve el bloqueo, puedes probar las APIs localmente.

### Prerrequisitos

1. **Python 3.9+**
2. **Google Earth Engine Account**
3. **Autenticación local de Earth Engine**

### Paso 1: Autenticación Local con Earth Engine

```bash
# Instalar Earth Engine Python API
pip install earthengine-api

# Autenticarse (usar tu cuenta personal de Google)
earthengine authenticate

# Inicializar Earth Engine
python -c "import ee; ee.Initialize(project='forestproject-copilot-ia')"
```

### Paso 2: Clonar el Repositorio

```bash
git clone https://github.com/christianfarjat/afolu-gee-cloudrun-api.git
cd afolu-gee-cloudrun-api
```

### Paso 3: Probar API de NDVI Localmente

```bash
# Navegar a la carpeta ndvi
cd ndvi

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar la API localmente
python main.py
```

En otra terminal, probar el endpoint:

```bash
curl -X POST http://localhost:8080/calculate-ndvi \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": -25.2968,
    "longitude": -57.6359,
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "scale": 30
  }'
```

### Paso 4: Probar API de Land Cover Localmente

```bash
# En el directorio raíz
cd landcover
pip install -r requirements.txt
python main.py
```

Probar:

```bash
curl -X POST http://localhost:8080/get-landcover \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": -25.2968,
    "longitude": -57.6359,
    "buffer_meters": 1000,
    "year": 2021
  }'
```

### Paso 5: Probar API de Biomass Localmente

```bash
cd ../biomass
pip install -r requirements.txt
python main.py
```

Probar:

```bash
curl -X POST http://localhost:8080/calculate-biomass \
  -H "Content-Type: application/json" \
  -d '{
    "latitude": -25.2968,
    "longitude": -57.6359,
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "buffer_meters": 1000
  }'
```

---

## 🚀 Opción 2: Despliegue a Cloud Run (Post-Resolución)

### Una vez obtenida la clave JSON:

### Paso 1: Crear Secret en Secret Manager

```bash
# Crear el secret con el contenido del archivo JSON
gcloud secrets create gee-service-account \
  --data-file=/path/to/service-account-key.json \
  --project=forestproject-copilot-ia

# Verificar
gcloud secrets describe gee-service-account --project=forestproject-copilot-ia
```

### Paso 2: Dar Permisos a Cloud Run

```bash
# Dar acceso al secret a las cuentas de servicio de Cloud Run
gcloud secrets add-iam-policy-binding gee-service-account \
  --member="serviceAccount:134126947227-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project=forestproject-copilot-ia
```

### Paso 3: Desplegar con el Script

```bash
# En el directorio raíz del repositorio
chmod +x deploy.sh
./deploy.sh
```

El script desplegará:
- ✅ NDVI API en Cloud Run
- ✅ Land Cover API en Cloud Run  
- ✅ Biomass API en Cloud Run

### Paso 4: Obtener URLs de los Servicios

```bash
# NDVI
gcloud run services describe afolu-ndvi-api \
  --region=us-central1 \
  --format="value(status.url)" \
  --project=forestproject-copilot-ia

# Land Cover
gcloud run services describe afolu-landcover-api \
  --region=us-central1 \
  --format="value(status.url)" \
  --project=forestproject-copilot-ia

# Biomass
gcloud run services describe afolu-biomass-api \
  --region=us-central1 \
  --format="value(status.url)" \
  --project=forestproject-copilot-ia
```

---

## 🤖 Opción 3: Integración con OpenAI Agent Builder

### Paso 1: Configurar MCP Servers

1. Ir a https://platform.openai.com/agent-builder
2. Abrir el workflow "AFOLU Carbon Analysis Workflow"
3. Añadir herramientas MCP:

#### NDVI API:
```json
{
  "name": "afolu_ndvi_calculator",
  "description": "Calculate NDVI (Normalized Difference Vegetation Index) for a specific location and time period using Landsat 8 satellite data",
  "url": "https://afolu-ndvi-api-XXXXX.run.app/calculate-ndvi",
  "method": "POST",
  "headers": {
    "Content-Type": "application/json"
  },
  "parameters": {
    "latitude": {"type": "number", "required": true},
    "longitude": {"type": "number", "required": true},
    "start_date": {"type": "string", "format": "date"},
    "end_date": {"type": "string", "format": "date"},
    "scale": {"type": "number", "default": 30}
  }
}
```

#### Land Cover API:
```json
{
  "name": "afolu_landcover_analyzer",
  "description": "Analyze land cover types using ESA WorldCover dataset for AFOLU carbon analysis",
  "url": "https://afolu-landcover-api-XXXXX.run.app/get-landcover",
  "method": "POST",
  "parameters": {
    "latitude": {"type": "number", "required": true},
    "longitude": {"type": "number", "required": true},
    "buffer_meters": {"type": "number", "default": 1000},
    "year": {"type": "number", "default": 2021}
  }
}
```

#### Biomass API:
```json
{
  "name": "afolu_biomass_calculator",
  "description": "Calculate biomass and carbon estimates using MODIS NPP data for AFOLU projects",
  "url": "https://afolu-biomass-api-XXXXX.run.app/calculate-biomass",
  "method": "POST",
  "parameters": {
    "latitude": {"type": "number", "required": true},
    "longitude": {"type": "number", "required": true},
    "start_date": {"type": "string", "format": "date"},
    "end_date": {"type": "string", "format": "date"},
    "buffer_meters": {"type": "number", "default": 1000}
  }
}
```

### Paso 2: Probar el Workflow Completo

En el Agent Builder, probar con:

```
Analiza el proyecto de reforestación en las coordenadas -25.2968, -57.6359 (Paraguay). 
Calcula el NDVI, analiza la cobertura terrestre y estima la biomasa para el período enero-diciembre 2024.
```

El agent debería:
1. ✅ Llamar a la API de NDVI
2. ✅ Llamar a la API de Land Cover
3. ✅ Llamar a la API de Biomass
4. ✅ Integrar los resultados en un análisis completo

---

## 🛠️ Troubleshooting

### Error: "Earth Engine not initialized"

```bash
# Verificar autenticación
earthengine authenticate

# Reinicializar con el proyecto
python -c "import ee; ee.Initialize(project='forestproject-copilot-ia')"
```

### Error: "Secret not found"

```bash
# Verificar que el secret existe
gcloud secrets list --project=forestproject-copilot-ia

# Verificar permisos
gcloud secrets get-iam-policy gee-service-account --project=forestproject-copilot-ia
```

### Error: "Cloud Run deployment failed"

```bash
# Ver logs
gcloud run services logs read afolu-ndvi-api \
  --region=us-central1 \
  --project=forestproject-copilot-ia
```

---

## 📊 Ejemplos de Respuestas Esperadas

### NDVI Response:
```json
{
  "ndvi_mean": 0.65,
  "ndvi_std": 0.12,
  "ndvi_min": 0.35,
  "ndvi_max": 0.85,
  "image_count": 45,
  "location": {
    "latitude": -25.2968,
    "longitude": -57.6359
  },
  "period": {
    "start": "2024-01-01",
    "end": "2024-12-31"
  }
}
```

### Land Cover Response:
```json
{
  "landcover_classes": {
    "10": {"name": "Tree cover", "area_ha": 75.5, "percentage": 75.5},
    "40": {"name": "Grassland", "area_ha": 15.2, "percentage": 15.2},
    "50": {"name": "Built-up", "area_ha": 9.3, "percentage": 9.3}
  },
  "total_area_ha": 100,
  "dominant_class": "Tree cover"
}
```

### Biomass Response:
```json
{
  "mean_npp_kg_c_m2": 0.45,
  "total_biomass_tons": 450.5,
  "carbon_stock_tons": 225.25,
  "period": "2024-01-01 to 2024-12-31",
  "data_quality": "high"
}
```

---

## 📅 Próximos Pasos

- [ ] Resolver bloqueo de política organizacional (ver `/docs/ADMIN_REQUEST.md`)
- [ ] Probar APIs localmente con autenticación personal
- [ ] Obtener clave JSON de service account
- [ ] Crear secret en Secret Manager
- [ ] Desplegar servicios a Cloud Run
- [ ] Configurar MCP servers en OpenAI Agent Builder
- [ ] Probar workflow completo end-to-end
- [ ] Documentar casos de uso y mejores prácticas

---

## 📞 Contacto y Soporte

**Proyecto:** forestproject-copilot-ia  
**Repositorio:** https://github.com/christianfarjat/afolu-gee-cloudrun-api  
**Administrador:** christian.farjat@mjmenergia.com
