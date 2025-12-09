#!/bin/bash

# AFOLU GEE Cloud Run APIs - Deployment Script
# Deploys all three services (NDVI, Land Cover, Biomass) to Google Cloud Run

set -e  # Exit on error

# Configuration
PROJECT_ID="forestproject-copilot-ia"
REGION="us-central1"

echo "🚀 Deploying AFOLU GEE APIs to Cloud Run..."
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Set project
gcloud config set project $PROJECT_ID

# Deploy NDVI Service
echo "📊 Deploying NDVI Calculator Service..."
cd ndvi
gcloud run deploy ndvi-service \
  --source . \
  --region $REGION \
  --platform managed \
  --allow-unauthenticated \
  --memory 1Gi \
  --timeout 300 \
  --min-instances 0 \
  --max-instances 10

NDVI_URL=$(gcloud run services describe ndvi-service --region $REGION --format 'value(status.url)')
echo "✅ NDVI Service deployed: $NDVI_URL"
cd ..

# Note: Land Cover and Biomass services need to be implemented
# Uncomment and add after creating those directories

# # Deploy Land Cover Service
# echo ""
# echo "🌍 Deploying Land Cover Analysis Service..."
# cd landcover
# gcloud run deploy landcover-service \
#   --source . \
#   --region $REGION \
#   --platform managed \
#   --allow-unauthenticated \
#   --memory 1Gi \
#   --timeout 300 \
#   --min-instances 0 \
#   --max-instances 10
# 
# LANDCOVER_URL=$(gcloud run services describe landcover-service --region $REGION --format 'value(status.url)')
# echo "✅ Land Cover Service deployed: $LANDCOVER_URL"
# cd ..

# # Deploy Biomass Service  
# echo ""
# echo "🌲 Deploying Biomass Calculator Service..."
# cd biomass
# gcloud run deploy biomass-service \
#   --source . \
#   --region $REGION \
#   --platform managed \
#   --allow-unauthenticated \
#   --memory 1Gi \
#   --timeout 300 \
#   --min-instances 0 \
#   --max-instances 10
#
# BIOMASS_URL=$(gcloud run services describe biomass-service --region $REGION --format 'value(status.url)')
# echo "✅ Biomass Service deployed: $BIOMASS_URL"
# cd ..

echo ""
echo "✨ Deployment Complete!"
echo ""
echo "Service URLs:"
echo "  NDVI Calculator: $NDVI_URL"
# echo "  Land Cover: $LANDCOVER_URL"
# echo "  Biomass: $BIOMASS_URL"
echo ""
echo "Next steps:"
echo "1. Test the endpoints with sample data"
echo "2. Configure these URLs as MCP custom tools in OpenAI Agent Builder"
echo "3. Monitor logs: gcloud run services logs read ndvi-service --region $REGION"
echo ""
echo "📝 Remember to uncomment landcover and biomass deployment after creating those services!"
