# Guía de Despliegue — ForestScan / AFOLU GEE Cloud Run

Runbook para desplegar los servicios a **Google Cloud Run** y proteger los
tiers de ForestScan con **Cloud IAP** (login con email de Google Workspace).

> El despliegue se ejecuta con **tu** sesión de `gcloud` autenticada contra el
> proyecto real. No se puede correr desde el entorno remoto de Claude (no tiene
> `gcloud` ni credenciales del proyecto).

## Configuración del proyecto

| Parámetro | Valor |
|---|---|
| Project ID | `forestproject-copilot-ia` |
| Región | `us-central1` |
| Dominio Workspace | `mjmenergia.com` |
| Service Account GEE | `forestblock-gge@forestproject-copilot-ia.iam.gserviceaccount.com` |
| Secreto credenciales GEE | `gee-service-account` (Secret Manager) |

## Servicios desplegados

| Servicio Cloud Run | Tier / Función | Acceso anónimo | Endpoint |
|---|---|:---:|---|
| `ndvi-service` | API NDVI (GEE) | sí | `POST /calculate-ndvi` |
| `forestscan-land-screening` | Land Screening | no (IAP) | `POST /land-screening` |
| `forestscan-eudr` | EUDR compliance | no (IAP) | `POST /eudr-check` |
| `forestscan-land-planning` | Land Planning | no (IAP) | `POST /land-planning` |

> `landcover-service` y `biomass-service` están comentados en `deploy.sh`;
> descomentar cuando se quieran desplegar.

## Prerrequisitos

1. **gcloud** autenticado: `gcloud auth login` (o usar [Cloud Shell](https://shell.cloud.google.com), ya viene listo).
2. Permisos en el proyecto: Owner, o bien Cloud Run Admin + IAP Admin + Service Account User + Secret Manager Admin.
3. **APIs habilitadas** (Run, Cloud Build, Secret Manager, IAP, Earth Engine):
   ```bash
   gcloud services enable \
     run.googleapis.com cloudbuild.googleapis.com \
     secretmanager.googleapis.com iap.googleapis.com \
     earthengine.googleapis.com \
     --project=forestproject-copilot-ia
   ```
4. **Secreto de GEE** creado en Secret Manager (`gee-service-account`) con el JSON
   del service account. Ver `docs/ADMIN_REQUEST.md`.

## Paso 0 — Acceso de runtime al secreto de GEE

Los servicios leen las credenciales de GEE desde Secret Manager. La cuenta de
servicio con la que corre Cloud Run debe poder acceder al secreto.

**Opción A (recomendada): desplegar con el SA de GEE.** Editar `deploy.sh` y
agregar a cada `gcloud run deploy` la línea:

```bash
  --service-account forestblock-gge@forestproject-copilot-ia.iam.gserviceaccount.com \
```

**Opción B: dar acceso al secreto a la SA por defecto de Compute:**

```bash
PROJECT_ID=forestproject-copilot-ia
PNUM=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
gcloud secrets add-iam-policy-binding gee-service-account \
  --project=$PROJECT_ID \
  --member="serviceAccount:${PNUM}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## Paso 1 — Clonar la rama

```bash
git clone -b claude/forestscan-gstack-auth0-google-Mvpvz \
  https://github.com/christianfarjat/afolu-gee-cloudrun-api.git
cd afolu-gee-cloudrun-api
```

## Paso 2 — Desplegar a Cloud Run

```bash
bash deploy.sh
```

Esto buildea cada servicio con Cloud Build (desde su `Dockerfile`) y despliega
`ndvi-service` + los 3 tiers de ForestScan. Los tiers se despliegan **sin**
`--allow-unauthenticated` (acceso controlado por IAP en el paso siguiente).

## Paso 3 — Proteger los tiers con Cloud IAP

```bash
bash tools/setup_iap.sh
```

Por cada tier: habilita IAP, crea el service agent de IAP, otorga `run.invoker`,
activa IAP + desactiva acceso anónimo y autoriza el login del dominio
`mjmenergia.com`. Ver detalle en [`docs/IAP_AUTH.md`](IAP_AUTH.md).

> La primera vez puede pedir configurar la pantalla de consentimiento OAuth
> (IAP brand). App interna, support email `christian.farjat@mjmenergia.com`.

## Paso 4 — Verificar

```bash
REGION=us-central1
TOKEN=$(gcloud auth print-identity-token)

for SVC in forestscan-land-screening forestscan-eudr forestscan-land-planning; do
  URL=$(gcloud run services describe $SVC --region $REGION --format='value(status.url)')
  echo "== $SVC =="
  curl -s -H "Authorization: Bearer $TOKEN" "$URL/health"; echo
done
```

Prueba funcional de EUDR con una geometría:

```bash
URL=$(gcloud run services describe forestscan-eudr --region us-central1 --format='value(status.url)')
curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -X POST "$URL/eudr-check" \
  -d '{
    "geometry": {"type":"Polygon","coordinates":[[[-60.0,-3.0],[-59.9,-3.0],[-59.9,-2.9],[-60.0,-2.9],[-60.0,-3.0]]]},
    "commodity": "soy"
  }'; echo
```

## Verificación local previa (sin GEE)

Para validar la lógica de los handlers antes de desplegar (usa un `ee`
mockeado, no requiere credenciales):

```bash
python3 -m venv .verifyvenv && .verifyvenv/bin/pip install flask
.verifyvenv/bin/python tools/verify_tiers.py
```

## Troubleshooting

| Síntoma | Causa probable | Acción |
|---|---|---|
| El servicio no arranca / 500 al iniciar | No puede leer el secreto de GEE | Aplicar Paso 0 (acceso a Secret Manager) |
| `403` al invocar un tier | IAP activo, falta autorización | Confirmar binding `roles/iap.httpsResourceAccessor` para tu usuario/dominio |
| `Earth Engine error` en la respuesta | SA sin permiso en GEE / dataset | Verificar que el SA esté registrado en Earth Engine |
| Build falla | API de Cloud Build deshabilitada | `gcloud services enable cloudbuild.googleapis.com` |

Ver logs de un servicio:

```bash
gcloud run services logs read <servicio> --region us-central1 --limit 50
```

## Referencias

- [`README.md`](../README.md) — visión general y endpoints
- [`docs/IAP_AUTH.md`](IAP_AUTH.md) — autenticación con Cloud IAP
- [`docs/ADMIN_REQUEST.md`](ADMIN_REQUEST.md) — secreto y service account de GEE
