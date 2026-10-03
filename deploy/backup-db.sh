#!/usr/bin/env bash
# Dump the Audio Notes Postgres database to a timestamped gzip on the VM.
# Run on the VM from /opt/audionotes:  sudo bash backup-db.sh
set -euo pipefail

cd "$(dirname "$0")"

# Load POSTGRES_USER / POSTGRES_DB from .env (ignore comments/blank lines).
set -a
# shellcheck disable=SC1091
. ./.env
set +a

STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p backups

docker compose exec -T db pg_dump \
  -U "${POSTGRES_USER:-audionotes}" \
  -d "${POSTGRES_DB:-audionotes}" \
  | gzip > "backups/audionotes-${STAMP}.sql.gz"

echo "Wrote backups/audionotes-${STAMP}.sql.gz"
