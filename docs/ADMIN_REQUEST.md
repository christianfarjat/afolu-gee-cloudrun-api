# Solicitud de Excepción: Política iam.disableServiceAccountKeyCreation

**Para:** Administrador de Google Cloud - ForestProject Copilot IA  
**Proyecto:** forestproject-copilot-ia  
**Solicitante:** Christian Fernandez Farjat (christian.farjat@mjmenergia.com)  
**Fecha:** 09 de diciembre de 2025

---

## Resumen del Problema

Se requiere crear una clave JSON para la cuenta de servicio `forestblock-gge@forestproject-copilot-ia.iam.gserviceaccount.com` para desplegar las APIs de AFOLU Carbon Analysis en Cloud Run, pero la política de organización `iam.disableServiceAccountKeyCreation` está bloqueando su creación.

---

## Detalles Técnicos

**Política bloqueante:**
- ID: `iam.disableServiceAccountKeyCreation`
- Número de seguimiento: `c7871524375643643`

**Cuenta de servicio afectada:**
- Email: `forestblock-gge@forestproject-copilot-ia.iam.gserviceaccount.com`
- Nombre: Forestblock GGE
- Rol actual: Escritor de recursos de Earth Engine (Beta)
- Estado: Habilitada

---

## Justificación de la Solicitud

Estoy desarrollando APIs de Google Earth Engine para análisis de carbono AFOLU que deben desplegarse como servicios en Cloud Run. Estas APIs requieren:

1. **Acceso a Google Earth Engine** para cálculos de:
   - NDVI (Índice de vegetación)
   - Cobertura terrestre (Land Cover con ESA WorldCover)
   - Biomasa y carbono (MODIS NPP)

2. **Autenticación con Service Account**: Las APIs necesitan credenciales JSON almacenadas en Secret Manager para autenticarse con Earth Engine desde Cloud Run

3. **Integración con OpenAI Agent Builder**: Las APIs serán consumidas como herramientas MCP personalizadas para workflows de análisis de carbono

---

## Opciones Solicitadas

### Opción 1 (Recomendada)
Deshabilitar temporalmente la política `iam.disableServiceAccountKeyCreation` para el proyecto `forestproject-copilot-ia` para permitir la creación de la clave JSON.

### Opción 2
Si existe una clave JSON previamente creada para `forestblock-gge@forestproject-copilot-ia.iam.gserviceaccount.com`, proporcionármela de forma segura.

### Opción 3 (Alternativa de largo plazo)
Asesoría para configurar **Workload Identity Federation** como alternativa más segura (requiere mayor tiempo de implementación y modificaciones en la arquitectura).

---

## Repositorio y Arquitectura

- **GitHub:** https://github.com/christianfarjat/afolu-gee-cloudrun-api
- **Branch:** main

**Estructura del proyecto:**
```
afolu-gee-cloudrun-api/
├── ndvi/
│   ├── main.py          # API para cálculos de NDVI
│   ├── requirements.txt
│   └── Dockerfile
├── landcover/
│   ├── main.py          # API para cobertura terrestre (ESA WorldCover)
│   ├── requirements.txt
│   └── Dockerfile
├── biomass/
│   ├── main.py          # API para biomasa/carbono (MODIS NPP)
│   ├── requirements.txt
│   └── Dockerfile
├── shared/
│   └── gee_utils.py     # Utilidades compartidas de GEE
└── deploy.sh            # Script de despliegue a Cloud Run
```

---

## Medidas de Seguridad

Una vez creada, la clave JSON será:

- ✅ Almacenada de forma segura en **Google Secret Manager**
- ✅ Accedida únicamente por los servicios de Cloud Run mediante variables de entorno
- ✅ No expuesta en código fuente ni repositorios
- ✅ Con acceso restringido mediante IAM roles
- ✅ Rotada periódicamente según mejores prácticas de Google Cloud

**Secret Manager configuration:**
```bash
# La clave se almacenará como:
Secret Name: gee-service-account
Project: forestproject-copilot-ia
Access: Cloud Run service accounts only
```

---

## APIs y Servicios Habilitados

Los siguientes servicios ya están habilitados en el proyecto:

- ✅ Google Earth Engine API
- ✅ Cloud Run Admin API
- ✅ Secret Manager API

---

## Siguiente Paso Requerido

Por favor, confirmar cuál de las opciones anteriores es viable para proceder con el despliegue de las APIs de AFOLU Carbon Analysis.

**Contacto:**
- Email: christian.farjat@mjmenergia.com
- Proyecto: forestproject-copilot-ia

---

## Referencias

- [Service Account Best Practices](https://cloud.google.com/iam/docs/best-practices-service-accounts)
- [Secret Manager Documentation](https://cloud.google.com/secret-manager/docs)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Google Earth Engine Python API](https://developers.google.com/earth-engine/guides/python_install)
