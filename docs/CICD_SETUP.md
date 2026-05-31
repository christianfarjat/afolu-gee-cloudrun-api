# CI/CD — Despliegue automático con GitHub Actions + Workload Identity Federation

El workflow [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml)
despliega los 3 tiers de ForestScan a Cloud Run y aplica Cloud IAP, autenticando
con **Workload Identity Federation (WIF)** — sin claves JSON de service account.

Esta configuración se hace **una sola vez**. Después, el deploy corre solo en
cada push a `main` (o manualmente desde la pestaña **Actions**).

## Cómo funciona

```
GitHub Actions (OIDC token)
        │  id-token
        ▼
Workload Identity Pool/Provider (GCP)
        │  impersona
        ▼
Service Account "deployer"  ──►  gcloud run deploy + setup_iap.sh
```

## Paso 1 — Variables que vas a necesitar

```bash
export PROJECT_ID=forestproject-copilot-ia
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
export REPO=christianfarjat/afolu-gee-cloudrun-api
export POOL=github-pool
export PROVIDER=github-provider
export DEPLOY_SA=github-deployer
export DEPLOY_SA_EMAIL=$DEPLOY_SA@$PROJECT_ID.iam.gserviceaccount.com
# Service account de runtime (acceso a GEE / Secret Manager):
export RUNTIME_SA_EMAIL=forestblock-gge@$PROJECT_ID.iam.gserviceaccount.com
```

## Paso 2 — Habilitar APIs

```bash
gcloud services enable \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com iap.googleapis.com iamcredentials.googleapis.com \
  sts.googleapis.com earthengine.googleapis.com \
  --project=$PROJECT_ID
```

## Paso 3 — Service account "deployer" y permisos

```bash
gcloud iam service-accounts create $DEPLOY_SA \
  --project=$PROJECT_ID --display-name="GitHub Actions deployer"

for role in \
  roles/run.admin \
  roles/cloudbuild.builds.editor \
  roles/artifactregistry.admin \
  roles/storage.admin \
  roles/iam.serviceAccountUser \
  roles/iap.admin \
  roles/serviceusage.serviceUsageAdmin \
  roles/iap.settingsAdmin ; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$DEPLOY_SA_EMAIL" --role="$role"
done

# Permitir que el deployer despliegue servicios "actuando como" el SA de runtime.
gcloud iam service-accounts add-iam-policy-binding $RUNTIME_SA_EMAIL \
  --project=$PROJECT_ID \
  --member="serviceAccount:$DEPLOY_SA_EMAIL" \
  --role="roles/iam.serviceAccountUser"
```

## Paso 4 — Workload Identity Pool + Provider

```bash
gcloud iam workload-identity-pools create $POOL \
  --project=$PROJECT_ID --location=global \
  --display-name="GitHub Actions pool"

gcloud iam workload-identity-pools providers create-oidc $PROVIDER \
  --project=$PROJECT_ID --location=global \
  --workload-identity-pool=$POOL \
  --display-name="GitHub provider" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition="assertion.repository_owner == 'christianfarjat'"
```

## Paso 5 — Vincular el repo de GitHub al SA deployer

```bash
gcloud iam service-accounts add-iam-policy-binding $DEPLOY_SA_EMAIL \
  --project=$PROJECT_ID \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.repository/$REPO"

# Nombre completo del provider (lo vas a pegar en la variable GCP_WIF_PROVIDER):
echo "projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/providers/$PROVIDER"
```

## Paso 6 — Variables del repositorio en GitHub

En GitHub: **Settings → Secrets and variables → Actions → pestaña _Variables_** →
*New repository variable*. Crear estas **Variables** (no son secretos):

| Variable | Valor de ejemplo |
|---|---|
| `GCP_PROJECT_ID` | `forestproject-copilot-ia` |
| `GCP_REGION` | `us-central1` |
| `GCP_WIF_PROVIDER` | `projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github-pool/providers/github-provider` |
| `GCP_DEPLOY_SA` | `github-deployer@forestproject-copilot-ia.iam.gserviceaccount.com` |
| `GCP_RUNTIME_SA` | `forestblock-gge@forestproject-copilot-ia.iam.gserviceaccount.com` |
| `WORKSPACE_DOMAIN` | `mjmenergia.com` |

## Paso 7 — Pantalla de consentimiento OAuth (prerrequisito de IAP)

El job `setup-iap` falla si el proyecto no tiene configurada la pantalla de
consentimiento OAuth. Configurala una vez (app **interna** de Workspace):

- Consola: *APIs & Services → OAuth consent screen* → User type **Internal**,
  app name `ForestScan`, support email `christian.farjat@mjmenergia.com`.

Ver detalle en [`docs/IAP_AUTH.md`](IAP_AUTH.md).

## Paso 8 — Ejecutar el deploy

- **Automático:** push a `main` que toque `land-screening/`, `eudr/`,
  `land-planning/`, `tools/setup_iap.sh` o el propio workflow.
- **Manual:** pestaña **Actions → Deploy ForestScan tiers → Run workflow**
  (podés elegir la rama, ej. la del PR).

El workflow:
1. **deploy** (matriz, en paralelo) — buildea y despliega cada tier a Cloud Run
   con `--no-allow-unauthenticated` y el SA de runtime.
2. **setup-iap** — corre `tools/setup_iap.sh` para activar IAP y autorizar el
   dominio Workspace en cada tier.

## Verificación post-deploy

Ver [`docs/DEPLOY.md`](DEPLOY.md#paso-4--verificar).

## Seguridad (WIF vs claves)

WIF no usa claves JSON de larga vida: GitHub presenta un token OIDC efímero que
GCP intercambia por credenciales temporales del SA deployer, restringido por
`attribute-condition` al owner del repo. Es la práctica recomendada por Google
para CI/CD desde GitHub.
