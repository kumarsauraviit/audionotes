#!/usr/bin/env bash
# Build the Audio Notes backend image with Cloud Build and deploy it to a
# Compute Engine VM running Docker Compose (Caddy + API + Celery worker).
# POSIX counterpart of deploy.ps1. Run from anywhere.
#
# Usage:
#   ./deploy.sh PROJECT_ID [-r region] [-z zone] [-n vm-name] [--create-vm]
#                [-t tag] [--domain example.com] [--skip-build] [--skip-setup]
#
# Postgres and Redis run as containers on the VM (persistent volumes), configured
# via POSTGRES_* in .env. Only Supabase Storage is external.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROJECT_ID="${1:-}"; shift || true
REGION="asia-south1"
ZONE="asia-south1-a"
VM_NAME="audionotes-vm"
REPOSITORY="audionotes"
IMAGE_NAME="audionotes"
TAG=""
DOMAIN=""
IP_NAME=""
MACHINE_TYPE="e2-medium"
ENV_FILE="${SCRIPT_DIR}/.env"
BACKEND_DIR="${REPO_ROOT}/backend"
CREATE_VM=0
SKIP_BUILD=0
SKIP_SETUP=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -r|--region) REGION="$2"; shift 2 ;;
    -z|--zone) ZONE="$2"; shift 2 ;;
    -n|--vm-name) VM_NAME="$2"; shift 2 ;;
    --repository) REPOSITORY="$2"; shift 2 ;;
    -t|--tag) TAG="$2"; shift 2 ;;
    --domain) DOMAIN="$2"; shift 2 ;;
    --ip-name) IP_NAME="$2"; shift 2 ;;
    --machine-type) MACHINE_TYPE="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --backend-dir) BACKEND_DIR="$2"; shift 2 ;;
    --create-vm) CREATE_VM=1; shift ;;
    --skip-build) SKIP_BUILD=1; shift ;;
    --skip-setup) SKIP_SETUP=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "${PROJECT_ID}" ]]; then
  echo "Usage: $0 PROJECT_ID [options]" >&2
  exit 1
fi
[[ -n "${IP_NAME}" ]] || IP_NAME="${VM_NAME}-ip"

command -v gcloud >/dev/null 2>&1 || { echo "gcloud not found on PATH." >&2; exit 1; }

echo "==> Project ${PROJECT_ID} (${REGION} / ${ZONE})"
gcloud config set project "${PROJECT_ID}" >/dev/null

echo "==> Enabling APIs (compute, artifactregistry, cloudbuild)"
gcloud services enable compute.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com --project="${PROJECT_ID}"

if ! gcloud artifacts repositories describe "${REPOSITORY}" --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "==> Creating Artifact Registry repository '${REPOSITORY}'"
  gcloud artifacts repositories create "${REPOSITORY}" \
    --repository-format=docker --location="${REGION}" \
    --description="Audio Notes backend images" --project="${PROJECT_ID}"
fi

# Cloud Build and the VM run as the Compute Engine default service account.
# Some projects do not auto-grant it roles; this makes builds able to read their
# source and the VM able to pull the image. Idempotent.
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
echo "==> Ensuring IAM for ${COMPUTE_SA}"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${COMPUTE_SA}" --role="roles/cloudbuild.builds.builder" \
  --condition=None --quiet >/dev/null
gcloud artifacts repositories add-iam-policy-binding "${REPOSITORY}" \
  --location="${REGION}" --member="serviceAccount:${COMPUTE_SA}" \
  --role="roles/artifactregistry.reader" --quiet >/dev/null

if [[ -z "${TAG}" ]]; then
  TAG="$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo latest)"
fi
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${TAG}"

if [[ "${SKIP_BUILD}" -eq 0 ]]; then
  echo "==> Building + pushing ${IMAGE} via Cloud Build"
  gcloud builds submit "${BACKEND_DIR}" --tag="${IMAGE}" --project="${PROJECT_ID}"
else
  echo "==> Skipping build; deploying existing ${IMAGE}"
fi

[[ -f "${ENV_FILE}" ]] || { echo "Env file '${ENV_FILE}' not found. Copy deploy/.env.example to deploy/.env." >&2; exit 1; }

STAGE_DIR="${SCRIPT_DIR}/.deploy-stage"
mkdir -p "${STAGE_DIR}"
cp "${SCRIPT_DIR}/docker-compose.prod.yml" "${STAGE_DIR}/docker-compose.yml"
cp "${SCRIPT_DIR}/Caddyfile" "${STAGE_DIR}/Caddyfile"
cp "${SCRIPT_DIR}/vm-setup.sh" "${STAGE_DIR}/vm-setup.sh"
cp "${SCRIPT_DIR}/remote-deploy.sh" "${STAGE_DIR}/remote-deploy.sh"

sed -e "s|^IMAGE=.*$|IMAGE=${IMAGE}|" "${ENV_FILE}" > "${STAGE_DIR}/.env"
ACCESS_TOKEN="$(gcloud auth print-access-token 2>/dev/null || true)"
printf '%s' "${ACCESS_TOKEN}" > "${STAGE_DIR}/.docker-token"
if [[ -n "${DOMAIN}" ]]; then
  sed -i.bak -e "s|^DOMAIN=.*$|DOMAIN=${DOMAIN}|" "${STAGE_DIR}/.env" && rm -f "${STAGE_DIR}/.env.bak"
else
  DOMAIN="$(sed -n 's/^DOMAIN=//p' "${STAGE_DIR}/.env" | head -n1)"
fi
if [[ -z "${DOMAIN}" || "${DOMAIN}" == "CHANGE_ME" ]]; then
  echo "Set DOMAIN in ${ENV_FILE} (or pass --domain), e.g. <VM_STATIC_IP>.sslip.io." >&2
  exit 1
fi

if ! grep -qE '^POSTGRES_PASSWORD=.+' "${STAGE_DIR}/.env" || grep -qE '^POSTGRES_PASSWORD=CHANGE_ME$' "${STAGE_DIR}/.env"; then
  echo "Set POSTGRES_PASSWORD in ${ENV_FILE} (python -c \"import secrets; print(secrets.token_urlsafe(32))\")." >&2
  exit 1
fi

if ! gcloud compute instances describe "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  if [[ "${CREATE_VM}" -eq 0 ]]; then
    echo "VM '${VM_NAME}' not found. Re-run with --create-vm or create it manually." >&2
    exit 1
  fi
  echo "==> Reserving static IP '${IP_NAME}'"
  if ! gcloud compute addresses describe "${IP_NAME}" --region="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    gcloud compute addresses create "${IP_NAME}" --region="${REGION}" --project="${PROJECT_ID}"
  fi
  IP="$(gcloud compute addresses describe "${IP_NAME}" --region="${REGION}" --project="${PROJECT_ID}" --format='value(address)')"

  if ! gcloud compute firewall-rules describe audionotes-allow-web --project="${PROJECT_ID}" >/dev/null 2>&1; then
    gcloud compute firewall-rules create audionotes-allow-web \
      --allow=tcp:80,tcp:443 --target-tags=audionotes-backend --direction=INGRESS --project="${PROJECT_ID}"
  fi

  echo "==> Creating VM '${VM_NAME}' (${MACHINE_TYPE}) at ${IP}"
  gcloud compute instances create "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" \
    --machine-type="${MACHINE_TYPE}" --image-family=debian-12 --image-project=debian-cloud \
    --boot-disk-size=30GB --address="${IP_NAME}" --tags=audionotes-backend --scopes=cloud-platform
  echo "    Backend public IP: ${IP}"
  echo "    If you use .sslip.io, set DOMAIN=${IP}.sslip.io in ${ENV_FILE} and re-run."
fi

echo "==> Waiting for SSH on ${VM_NAME}"
for attempt in $(seq 1 30); do
  if gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" --quiet --command="echo ready" >/dev/null 2>&1; then
    echo "    SSH is ready"
    break
  fi
  echo "    waiting for SSH (${attempt}/30)..."
  sleep 10
  if [[ "${attempt}" -eq 30 ]]; then
    echo "VM '${VM_NAME}' did not become reachable over SSH." >&2
    exit 1
  fi
done

if [[ "${SKIP_SETUP}" -eq 0 ]]; then
  echo "==> Bootstrapping Docker on ${VM_NAME}"
  gcloud compute scp "${STAGE_DIR}/vm-setup.sh" "${VM_NAME}:/tmp/audionotes-vm-setup.sh" --zone="${ZONE}" --project="${PROJECT_ID}" --quiet
  gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" --quiet --command="sudo bash /tmp/audionotes-vm-setup.sh"
fi

echo "==> Uploading compose files to ${VM_NAME}"
gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" --quiet --command="mkdir -p /tmp/audionotes-deploy"
gcloud compute scp "${STAGE_DIR}/docker-compose.yml" "${STAGE_DIR}/Caddyfile" "${STAGE_DIR}/remote-deploy.sh" \
  "${STAGE_DIR}/.env" "${STAGE_DIR}/.docker-token" \
  "${VM_NAME}:/tmp/audionotes-deploy/" --zone="${ZONE}" --project="${PROJECT_ID}" --quiet

echo "==> Deploying stack on ${VM_NAME}"
# A multi-line --command can be split by the CLI chain; run the uploaded script.
gcloud compute ssh "${VM_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" --quiet \
  --command="sudo bash /tmp/audionotes-deploy/remote-deploy.sh ${REGION}"

echo "==> Verifying https://${DOMAIN}/health"
sleep 5
curl -fsS --max-time 30 "https://${DOMAIN}/health" || echo "WARN: health check failed; DNS or the TLS certificate may still be propagating."

echo
echo "Backend deployed."
echo "  API base:  https://${DOMAIN}"
echo "  Image:     ${IMAGE}"
echo "  Next: deploy the frontend, then set FRONTEND_ORIGIN in ${ENV_FILE} and re-run."
