# Autenticación de ForestScan con Cloud IAP (Google Workspace)

Esta guía describe cómo proteger cada **tier de ForestScan** con **Identity-Aware
Proxy (IAP)** de Google Cloud, de modo que el login se haga con el **email de
Google Workspace** (`@mjmenergia.com`).

IAP es 100% del stack de Google. Valida la identidad del usuario **antes** de que
la request llegue al contenedor de Cloud Run, sin necesidad de modificar el código
de las APIs, sin balanceador de carga y sin costo adicional.

## Tiers de ForestScan

| Tier (producto)  | Servicio Cloud Run            |
|------------------|-------------------------------|
| Land Screening   | `forestscan-land-screening`   |
| EUDR             | `forestscan-eudr`             |
| Land Planning    | `forestscan-land-planning`    |

> Cada tier es un servicio Cloud Run independiente. Si todavía no existen, hay que
> desplegarlos primero (ver `deploy.sh`) y luego correr el setup de IAP.

## Cómo funciona el login

```
Usuario (browser)
    │  abre https://<tier>.run.app
    ▼
Cloud IAP  ──► pantalla de login de Google
    │          (acepta solo cuentas del dominio mjmenergia.com)
    ▼  request firmada con identidad verificada
Cloud Run (tier de ForestScan)
```

- Solo cuentas cuyo email pertenece al dominio Workspace autorizado pueden entrar.
- El acceso anónimo queda deshabilitado (`--no-allow-unauthenticated`).
- La autorización se controla con IAM (`roles/iap.httpsResourceAccessor`).

## Validación a nivel de aplicación (defensa en profundidad)

Además del IAP a nivel de plataforma, **cada tier valida la identidad dentro del
código** (`auth.py` en cada servicio):

- Lee la identidad que IAP inyecta y **exige el dominio Workspace** (`@mjmenergia.com`).
- Resolución de identidad:
  1. Si está seteada la env `IAP_AUDIENCE`, **verifica criptográficamente** el JWT
     firmado de IAP (header `X-Goog-IAP-JWT-Assertion`): firma, emisor
     (`https://cloud.google.com/iap`) y audiencia.
  2. Si no, usa el header `X-Goog-Authenticated-User-Email` que setea IAP.
- Los endpoints de análisis y `/whoami` están protegidos con el decorador
  `@require_google_auth`. `/health` y `/` quedan públicos (para health checks).

Respuestas de error: `401` sin identidad válida, `403` si el email no pertenece
al dominio autorizado. Las respuestas exitosas incluyen `authenticated_user`.

### Variables de entorno (runtime de cada tier)

| Variable | Default | Descripción |
|---|---|---|
| `WORKSPACE_DOMAIN` | `mjmenergia.com` | Dominio Workspace autorizado |
| `IAP_AUDIENCE` | _(vacío)_ | Audiencia esperada del JWT de IAP; si se setea, activa la verificación de firma |
| `AUTH_REQUIRED` | `true` | `false` desactiva la validación (solo desarrollo local) |

> Obtener la audiencia para Cloud Run + IAP:
> `gcloud iap web get-iam-policy` / consola IAP. Mientras no esté seteada,
> la app confía en el header de IAP (válido porque IAP descarta copias
> provenientes del cliente).

### `/whoami`

```bash
curl -H "Authorization: Bearer $TOKEN" "$URL/whoami"
# -> {"authenticated_user": "usuario@mjmenergia.com"}
```

## Prerrequisitos

1. `gcloud` CLI instalado y autenticado (`gcloud auth login`).
2. Permisos de Owner / IAP Admin en el proyecto `forestproject-copilot-ia`.
3. Los servicios Cloud Run de cada tier ya desplegados.

## Configuración automática

Ejecutar el script incluido:

```bash
bash tools/setup_iap.sh
```

El script, para cada tier:

1. Habilita las APIs `iap.googleapis.com` y `run.googleapis.com`.
2. Crea el *service agent* de IAP.
3. Otorga `roles/run.invoker` al service agent de IAP sobre el servicio.
4. Activa IAP y desactiva el acceso anónimo (`--iap --no-allow-unauthenticated`).
5. Autoriza el login del dominio Workspace (`roles/iap.httpsResourceAccessor`).

### Variables configurables

```bash
PROJECT_ID=forestproject-copilot-ia \
REGION=us-central1 \
WORKSPACE_DOMAIN=mjmenergia.com \
bash tools/setup_iap.sh
```

Para limitar el acceso a usuarios o grupos en vez de todo el dominio, editar
`ALLOWED_MEMBERS` en el script:

```bash
# Todo el dominio (por defecto)
ALLOWED_MEMBERS=("domain:mjmenergia.com")

# Solo un usuario
ALLOWED_MEMBERS=("user:christian.farjat@mjmenergia.com")

# Un grupo de Workspace
ALLOWED_MEMBERS=("group:forestscan@mjmenergia.com")
```

## Configuración manual (paso a paso)

Si preferís hacerlo a mano para un tier (`SERVICE`):

```bash
PROJECT_ID=forestproject-copilot-ia
REGION=us-central1
SERVICE=forestscan-land-screening
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')

# 1. Habilitar APIs
gcloud services enable iap.googleapis.com run.googleapis.com --project=$PROJECT_ID

# 2. Crear el service agent de IAP
gcloud beta services identity create --service=iap.googleapis.com --project=$PROJECT_ID

# 3. Permitir que IAP invoque el servicio
gcloud run services add-iam-policy-binding $SERVICE \
  --region=$REGION \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

# 4. Activar IAP y bloquear acceso anónimo
gcloud beta run services update $SERVICE \
  --region=$REGION --iap --no-allow-unauthenticated

# 5. Autorizar login del dominio Workspace
gcloud beta iap web add-iam-policy-binding \
  --resource-type=cloud-run --region=$REGION --service=$SERVICE \
  --member="domain:mjmenergia.com" \
  --role="roles/iap.httpsResourceAccessor"
```

## Pantalla de consentimiento OAuth (IAP brand)

La primera vez que se habilita IAP en el proyecto, Google pide configurar la
pantalla de consentimiento OAuth. Para una app **interna** de Workspace alcanza con:

- **Application title:** `ForestScan`
- **Support email:** `christian.farjat@mjmenergia.com`
- **User type:** Internal (solo la organización)

Se configura en la consola: *APIs & Services → OAuth consent screen*, o se crea con:

```bash
gcloud iap oauth-brands create \
  --application_title="ForestScan" \
  --support_email=christian.farjat@mjmenergia.com \
  --project=forestproject-copilot-ia
```

> Solo puede existir **un** brand por proyecto. Si ya existe, este paso se omite.

## Operaciones comunes

**Revocar acceso a un miembro:**

```bash
gcloud beta iap web remove-iam-policy-binding \
  --resource-type=cloud-run --region=us-central1 --service=<TIER> \
  --member="user:persona@mjmenergia.com" \
  --role="roles/iap.httpsResourceAccessor"
```

**Desactivar IAP en un tier:**

```bash
gcloud beta run services update <TIER> --region=us-central1 --no-iap
```

**Acceso programático (service-to-service o el agente de OpenAI):**

Las llamadas no interactivas deben enviar un **ID token** de IAP en el header
`Authorization: Bearer <ID_TOKEN>`, generado por una cuenta de servicio con
`roles/iap.httpsResourceAccessor`. Ver:
https://cloud.google.com/iap/docs/authentication-howto

## Referencias

- [Configure IAP for Cloud Run](https://cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run)
- [Enable IAP for Cloud Run](https://cloud.google.com/iap/docs/enabling-cloud-run)
- [IAP programmatic authentication](https://cloud.google.com/iap/docs/authentication-howto)
