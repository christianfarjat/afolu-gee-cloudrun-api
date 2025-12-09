# Herramientas de Configuración Local

## Descripción

Esta carpeta contiene scripts y herramientas para configurar y probar el ambiente local de desarrollo de las AFOLU GEE Cloud Run APIs.

## Contenido

### `setup_local.sh`

Script automatizado que configura el ambiente local completo para pruebas.

**Funcionalidades:**
- ✅ Verificación de prerequisitos (Python 3, gcloud CLI)
- ✅ Autenticación con Google Cloud
- ✅ Configuración de Google Earth Engine
- ✅ Creación de entorno virtual Python
- ✅ Instalación de dependencias
- ✅ Recuperación de credenciales desde Secret Manager
- ✅ Creación de script de pruebas automatizado

## Uso Rápido

### 1. Clonar el Repositorio

```bash
git clone https://github.com/christianfarjat/afolu-gee-cloudrun-api.git
cd afolu-gee-cloudrun-api
```

### 2. Ejecutar el Script de Configuración

```bash
chmod +x tools/setup_local.sh
./tools/setup_local.sh
```

El script realizará las siguientes acciones:
1. Verificar que Python 3 y gcloud CLI estén instalados
2. Iniciar sesión en Google Cloud (si es necesario)
3. Configurar el proyecto: `forestproject-copilot-ia`
4. Autenticar con Google Earth Engine
5. Crear y configurar un entorno virtual Python
6. Instalar todas las dependencias necesarias
7. Descargar las credenciales del service account desde Secret Manager
8. Crear un script de pruebas automatizado

### 3. Activar el Entorno Virtual

```bash
source venv/bin/activate
```

### 4. Ejecutar las Pruebas

```bash
python3 test_apis_local.py
```

Este script probará:
- ✅ Autenticación con Google Earth Engine
- ✅ Acceso a Secret Manager
- ✅ Cálculo de NDVI con Sentinel-2
- ✅ Acceso a datos de cobertura terrestre (ESA WorldCover)
- ✅ Acceso a datos de biomasa (MODIS NPP)

## Pruebas de Servicios Individuales

Después de ejecutar el script de configuración, puedes probar cada servicio individualmente:

### NDVI Service
```bash
cd ndvi
python main.py
```

El servicio estará disponible en: `http://localhost:8080`

Prueba el endpoint:
```bash
curl -X POST http://localhost:8080/calculate-ndvi \
  -H "Content-Type: application/json" \
  -d '{
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[-84.0, 10.0], [-84.0, 10.5], [-83.5, 10.5], [-83.5, 10.0], [-84.0, 10.0]]]
    },
    "start_date": "2023-01-01",
    "end_date": "2023-12-31"
  }'
```

### Land Cover Service
```bash
cd landcover
python main.py
```

El servicio estará disponible en: `http://localhost:8080`

Prueba el endpoint:
```bash
curl -X POST http://localhost:8080/get-landcover \
  -H "Content-Type: application/json" \
  -d '{
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[-84.0, 10.0], [-84.0, 10.5], [-83.5, 10.5], [-83.5, 10.0], [-84.0, 10.0]]]
    },
    "year": 2021
  }'
```

### Biomass Service
```bash
cd biomass
python main.py
```

El servicio estará disponible en: `http://localhost:8080`

Prueba el endpoint:
```bash
curl -X POST http://localhost:8080/calculate-biomass \
  -H "Content-Type: application/json" \
  -d '{
    "geometry": {
      "type": "Polygon",
      "coordinates": [[[-84.0, 10.0], [-84.0, 10.5], [-83.5, 10.5], [-83.5, 10.0], [-84.0, 10.0]]]
    },
    "start_date": "2023-01-01",
    "end_date": "2023-12-31"
  }'
```

## Prerequisitos

Antes de ejecutar el script de configuración, asegúrate de tener:

1. **Python 3.7+** instalado
   ```bash
   python3 --version
   ```

2. **Google Cloud SDK** instalado
   ```bash
   gcloud --version
   ```
   
   Si no está instalado: https://cloud.google.com/sdk/docs/install

3. **Permisos en Google Cloud**
   - Acceso al proyecto: `forestproject-copilot-ia`
   - Permisos para acceder al Secret Manager
   - Service Account: `forestblock-gge@forestproject-copilot-ia.iam.gserviceaccount.com`

## Resolución de Problemas

### Error: No se puede acceder a Secret Manager

**Causa:** No tienes permisos para acceder al secreto `gee-service-account`

**Solución:** 
- Contacta al administrador (christian.farjat@mjmenergia.com)
- Solicita el rol `Secret Manager Secret Accessor`
- Ver: `docs/ADMIN_REQUEST.md`

### Error: Earth Engine no se puede autenticar

**Causa:** No has autenticado Earth Engine o las credenciales están corruptas

**Solución:**
```bash
earthengine authenticate
```

### Error: gcloud no está autenticado

**Causa:** No has iniciado sesión en Google Cloud

**Solución:**
```bash
gcloud auth login
gcloud config set project forestproject-copilot-ia
```

## Variables de Entorno

Después de ejecutar el script, las siguientes variables estarán configuradas:

- `GOOGLE_APPLICATION_CREDENTIALS`: Ruta al archivo JSON con las credenciales del service account

## Documentación Adicional

- **Guía de Pruebas Completa:** `docs/TESTING_GUIDE.md`
- **Solicitud de Excepción al Administrador:** `docs/ADMIN_REQUEST.md`
- **README Principal:** `README.md`

## Próximos Pasos

Después de configurar el ambiente local:

1. ✅ Ejecutar pruebas locales
2. ⏳ Desplegar servicios a Cloud Run (requiere clave JSON del service account)
3. ⏳ Integrar como herramientas MCP en OpenAI Agent Builder
4. ⏳ Probar el flujo completo de AFOLU Carbon Analysis

## Soporte

Para problemas o preguntas:
- Revisar: `docs/TESTING_GUIDE.md`
- Contactar: christian.farjat@mjmenergia.com
