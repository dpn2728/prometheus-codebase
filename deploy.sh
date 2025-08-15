#!/bin/bash
set -e
# This is the FINAL version of the deploy script for Project Prometheus.
# It separates deployment and the CPU allocation update for maximum compatibility.

if [ "$#" -ne 3 ]; then
    echo "Usage: ./deploy.sh <PROJECT_ID> <REGION> <SERVICE_NAME>"
    exit 1
fi

PROJECT_ID=$1
REGION=$2
SERVICE_NAME=$3

echo "--- 1/5: Enabling APIs for Project Prometheus ---"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com --project=$PROJECT_ID

echo "--- 2/5: Verifying and uploading secrets from 'secrets.env' ---"
if [ ! -f secrets.env ]; then
    echo "FATAL ERROR: 'secrets.env' file not found."
    exit 1
fi
# (Secret handling code remains the same as it's working perfectly)
upsert_secret() {
    SECRET_ID=$1; SECRET_VALUE=$2
    if ! gcloud secrets describe "$SECRET_ID" --project="$PROJECT_ID" &>/dev/null; then
        echo "Creating new secret: $SECRET_ID"
        gcloud secrets create "$SECRET_ID" --replication-policy="automatic" --project="$PROJECT_ID"
    fi
    printf "%s" "$SECRET_VALUE" | gcloud secrets versions add "$SECRET_ID" --data-file=- --project="$PROJECT_ID" > /dev/null
}
while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ -n "$line" && ! "$line" =~ ^# ]]; then
        SECRET_ID=$(echo "$line" | cut -d '=' -f 1); SECRET_VALUE=$(echo "$line" | cut -d '=' -f 2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'); upsert_secret "$SECRET_ID" "$SECRET_VALUE"
    fi
done < secrets.env
echo "Secrets processed."

echo "--- 3/5: Building the Prometheus container image ---"
gcloud builds submit --tag "gcr.io/$PROJECT_ID/$SERVICE_NAME" . --project=$PROJECT_ID

echo "--- 4/5: Deploying Prometheus Service to Cloud Run ---"
# We first deploy with min-instances=1 to ensure it's always running.
gcloud run deploy "$SERVICE_NAME" \
  --image "gcr.io/$PROJECT_ID/$SERVICE_NAME" \
  --platform managed \
  --region "$REGION" \
  --update-secrets="EMAIL_SENDER=EMAIL_SENDER:latest,EMAIL_PASSWORD=EMAIL_PASSWORD:latest,EMAIL_RECEIVER=EMAIL_RECEIVER:latest,TIMEZONE=TIMEZONE:latest" \
  --allow-unauthenticated \
  --min-instances=1 \
  --project=$PROJECT_ID

echo "--- 5/5: Updating service to 'Always-On' CPU mode ---"
# We apply the CPU allocation as a separate update command. This is more robust.
gcloud run services update "$SERVICE_NAME" \
  --region "$REGION" \
  --cpu-always-allocated \
  --project=$PROJECT_ID

echo "--- DEPLOYMENT COMPLETE. Project Prometheus is fully operational. ---"
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --platform managed --region $REGION --format 'value(status.url)' --project=$PROJECT_ID)
echo "Prometheus Health Check URL: $SERVICE_URL"
