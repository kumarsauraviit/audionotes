#!/usr/bin/env bash
# Runs on the VM after the deploy files are uploaded to /tmp/audionotes-deploy.
# Kept as a file (not an inline `gcloud compute ssh --command`) because a
# multi-line --command is split on newlines by the Windows/gcloud CLI chain.
#
# Usage on the VM:  sudo bash remote-deploy.sh <region>
set -euo pipefail

REGION="${1:?usage: remote-deploy.sh <region>}"

sudo mkdir -p /opt/audionotes
sudo install -m 644 /tmp/audionotes-deploy/docker-compose.yml /opt/audionotes/docker-compose.yml
sudo install -m 644 /tmp/audionotes-deploy/Caddyfile /opt/audionotes/Caddyfile
sudo install -m 600 /tmp/audionotes-deploy/.env /opt/audionotes/.env

echo ">> Authenticating Docker to Artifact Registry"
if [ -s /tmp/audionotes-deploy/.docker-token ]; then
  echo "   using the deploying user's access token"
  sudo docker login -u oauth2accesstoken --password-stdin "https://${REGION}-docker.pkg.dev" \
    < /tmp/audionotes-deploy/.docker-token
else
  echo "   using the VM service-account metadata token"
  TOKEN=$(curl -fsS -H 'Metadata-Flavor: Google' \
    'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token' \
    | sed -E 's/.*"access_token":"([^"]+)".*/\1/')
  echo "$TOKEN" | sudo docker login -u oauth2accesstoken --password-stdin "https://${REGION}-docker.pkg.dev"
fi
rm -f /tmp/audionotes-deploy/.docker-token

cd /opt/audionotes
echo ">> Pulling image"
sudo docker compose pull
echo ">> Applying database migrations (starts db first)"
sudo docker compose run --rm migrate
echo ">> Starting services"
sudo docker compose up -d --remove-orphans
sudo docker compose ps
