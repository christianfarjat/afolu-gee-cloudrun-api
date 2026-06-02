#!/bin/bash

# ForestScan - Cloud IAP Setup Script
# Configura Identity-Aware Proxy (IAP) sobre los servicios Cloud Run de cada
# tier de ForestScan, restringiendo el acceso al dominio de Google Workspace.
#
# Login: los usuarios acceden con su email de Google Workspace. IAP valida la
# identidad ANTES de que la request llegue al contenedor Cloud Run, sin tocar
# el codigo de las APIs.
#
# Tiers de ForestScan -> servicios Cloud Run:
#   - Land Screening  -> forestscan-land-screening
#   - EUDR            -> forestscan-eudr
#   - Land Planning   -> forestscan-land-planning
#
# Referencias:
#   https://cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run
#   https://cloud.google.com/iap/docs/enabling-cloud-run

set -e

# ----------------------------------------------------------------------------
# Configuracion (ajustar segun el entorno)
# ----------------------------------------------------------------------------
PROJECT_ID="${PROJECT_ID:-forestproject-copilot-ia}"
REGION="${REGION:-us-central1}"

# Dominio de Google Workspace autorizado a loguearse en TODOS los tiers.
# Usar "domain:<dominio>" para todo el dominio, o sobreescribir ALLOWED_MEMBERS
# con usuarios/grupos especificos (ver abajo).
WORKSPACE_DOMAIN="${WORKSPACE_DOMAIN:-mjmenergia.com}"

# Miembros con acceso. Por defecto todo el dominio Workspace.
# Ejemplos alternativos:
#   ALLOWED_MEMBERS=("user:christian.farjat@mjmenergia.com")
#   ALLOWED_MEMBERS=("group:forestscan@mjmenergia.com")
#   ALLOWED_MEMBERS=("domain:mjmenergia.com" "user:externo@gmail.com")
ALLOWED_MEMBERS=("domain:${WORKSPACE_DOMAIN}")

# Email de soporte para la pantalla de consentimiento OAuth (IAP brand).
SUPPORT_EMAIL="${SUPPORT_EMAIL:-christian.farjat@mjmenergia.com}"

# Tiers de ForestScan = nombres de servicio Cloud Run.
TIERS=(
  "forestscan-land-screening"
  "forestscan-eudr"
  "forestscan-land-planning"
)

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "${BLUE}================================================${NC}"
echo "${BLUE} ForestScan - Configuracion Cloud IAP por tier ${NC}"
echo "${BLUE}================================================${NC}"
echo "Proyecto:           $PROJECT_ID"
echo "Region:             $REGION"
echo "Dominio Workspace:  $WORKSPACE_DOMAIN"
echo "Miembros con acceso:${ALLOWED_MEMBERS[*]}"
echo "Tiers:              ${TIERS[*]}"
echo ""

# ----------------------------------------------------------------------------
# Prerequisitos
# ----------------------------------------------------------------------------
if ! command -v gcloud >/dev/null 2>&1; then
  echo "${RED}Error: gcloud CLI no esta instalado.${NC}"
  echo "Instalar desde: https://cloud.google.com/sdk/docs/install"
  exit 1
fi

gcloud config set project "$PROJECT_ID" >/dev/null

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
if [ -z "$PROJECT_NUMBER" ]; then
  echo "${RED}Error: no se pudo obtener el numero del proyecto $PROJECT_ID.${NC}"
  exit 1
fi
IAP_SA="service-${PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com"

# ----------------------------------------------------------------------------
# Paso 1: Habilitar APIs necesarias
# ----------------------------------------------------------------------------
echo "${YELLOW}[1/5] Habilitando APIs (IAP, Cloud Run)...${NC}"
gcloud services enable iap.googleapis.com run.googleapis.com --project="$PROJECT_ID"
echo "${GREEN}OK${NC}"
echo ""

# ----------------------------------------------------------------------------
# Paso 2: Crear el service agent de IAP
# ----------------------------------------------------------------------------
echo "${YELLOW}[2/5] Creando service agent de IAP...${NC}"
gcloud beta services identity create --service=iap.googleapis.com --project="$PROJECT_ID" >/dev/null
echo "${GREEN}OK -> ${IAP_SA}${NC}"
echo ""

# ----------------------------------------------------------------------------
# Paso 3 a 5: por cada tier
# ----------------------------------------------------------------------------
for SERVICE in "${TIERS[@]}"; do
  echo "${BLUE}------------------------------------------------${NC}"
  echo "${BLUE} Tier: ${SERVICE}${NC}"
  echo "${BLUE}------------------------------------------------${NC}"

  # Verificar que el servicio Cloud Run exista
  if ! gcloud run services describe "$SERVICE" --region="$REGION" >/dev/null 2>&1; then
    echo "${RED}  ! El servicio Cloud Run '$SERVICE' no existe en $REGION.${NC}"
    echo "${YELLOW}    Desplegalo primero (ej: bash deploy.sh) y volve a correr este script.${NC}"
    echo ""
    continue
  fi

  # Paso 3: permitir que el service agent de IAP invoque el servicio
  echo "${YELLOW}  [3/5] Otorgando run.invoker al service agent de IAP...${NC}"
  gcloud run services add-iam-policy-binding "$SERVICE" \
    --region="$REGION" \
    --member="serviceAccount:${IAP_SA}" \
    --role="roles/run.invoker" >/dev/null
  echo "${GREEN}  OK${NC}"

  # Paso 4: habilitar IAP y bloquear acceso anonimo en el servicio
  echo "${YELLOW}  [4/5] Activando IAP y desactivando acceso anonimo...${NC}"
  gcloud beta run services update "$SERVICE" \
    --region="$REGION" \
    --iap \
    --no-allow-unauthenticated >/dev/null
  echo "${GREEN}  OK${NC}"

  # Paso 5: otorgar acceso de login a los miembros del Workspace
  echo "${YELLOW}  [5/5] Autorizando login a: ${ALLOWED_MEMBERS[*]}${NC}"
  for MEMBER in "${ALLOWED_MEMBERS[@]}"; do
    gcloud beta iap web add-iam-policy-binding \
      --resource-type=cloud-run \
      --region="$REGION" \
      --service="$SERVICE" \
      --member="$MEMBER" \
      --role="roles/iap.httpsResourceAccessor" >/dev/null
    echo "${GREEN}  + ${MEMBER}${NC}"
  done

  URL=$(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')
  echo "${GREEN}  IAP activo en: ${URL}${NC}"
  echo ""
done

echo "${GREEN}================================================${NC}"
echo "${GREEN} Configuracion IAP completada${NC}"
echo "${GREEN}================================================${NC}"
echo ""
echo "Notas:"
echo "  - Solo usuarios con email del dominio '${WORKSPACE_DOMAIN}' podran loguearse."
echo "  - La primera vez puede pedir configurar la pantalla de consentimiento OAuth"
echo "    (IAP brand). Email de soporte sugerido: ${SUPPORT_EMAIL}."
echo "  - Para revocar acceso a un miembro:"
echo "      gcloud beta iap web remove-iam-policy-binding \\"
echo "        --resource-type=cloud-run --region=${REGION} --service=<TIER> \\"
echo "        --member=<MIEMBRO> --role=roles/iap.httpsResourceAccessor"
echo "  - Para desactivar IAP en un tier:"
echo "      gcloud beta run services update <TIER> --region=${REGION} --no-iap"
echo ""
