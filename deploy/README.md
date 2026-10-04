# Deployment

Two independent deployments:

- **Backend** — one Compute Engine VM running Docker Compose: **Caddy** (TLS +
  reverse proxy), **FastAPI**, the **Celery worker**, and **Postgres + Redis as
  containers** (persistent Docker volumes). Only Supabase Storage is external,
  because the audio objects live there.
- **Frontend** — Next.js on **Vercel**.

```
Browser ──HTTPS──> Vercel (Next.js)
   │                     │ XHR/SSE
   │                     ▼
   └───────────────> Caddy (VM, Let's Encrypt)
                           │
                       api:8000 ──> db  (Postgres container, volume pg_data)
                           │
                       worker ────> redis (container, volume redis_data)
                                       Gnani, Gemini, Supabase Storage
```

The worker is required: uploads are queued to Redis and only progress while the
Celery worker runs. Audio lives in Supabase Storage, so Postgres stores only
metadata (no large blobs).

Deployment files:

| File | Purpose |
| --- | --- |
| `backend/Dockerfile` | Image for both API and worker |
| `deploy/docker-compose.prod.yml` | Caddy + api + worker + db + redis (+ one-shot migrate) |
| `deploy/Caddyfile` | TLS + reverse proxy (SSE-aware) |
| `deploy/.env.example` | Production env template |
| `deploy/.env` | Your real values (gitignored) |
| `deploy/vm-setup.sh` | Installs Docker on the VM (idempotent) |
| `deploy/remote-deploy.sh` | Runs on the VM: pull, migrate, start the stack |
| `deploy/deploy.ps1` / `deploy.sh` | Build + deploy the backend |
| `deploy/deploy-frontend.ps1` | Configure Vercel env + deploy |
| `deploy/backup-db.sh` | `pg_dump` the database on the VM |
| `frontend/.vercelignore` | Keeps local `.env` files out of the Vercel upload |

---

## 0. Prerequisites (one-time)

Install and authenticate the CLIs (Windows):

```powershell
winget install --id Google.CloudSDK        # gcloud
winget install --id OpenJS.NodeJS.LTS      # node + npx (Vercel CLI runs via npx)
gcloud auth login
gcloud auth application-default login
```

A GCP project with **billing enabled**. Create one if needed:

```powershell
gcloud projects create MY_PROJECT_ID
gcloud config set project MY_PROJECT_ID
```

Nothing else is required up front: Postgres and Redis are created by Docker
Compose, and the Supabase Storage bucket is created automatically on API
startup. The Gnani, Gemini, Supabase Storage, and SMTP credentials already
filled into `deploy/.env` were taken from `backend/.env`.

---

## 1. Fill in `deploy/.env`

`deploy/.env` is pre-filled with the shared credentials and a generated
`POSTGRES_PASSWORD`. Replace the remaining `CHANGE_ME` values:

- `DOMAIN` — the backend hostname (see step 2).
- `FRONTEND_ORIGIN`, `BACKEND_PUBLIC_URL`, `FRONTEND_RESET_PASSWORD_URL`,
  `FRONTEND_VERIFY_EMAIL_URL` — fill after the frontend is deployed (step 5).

`IMAGE` is overwritten automatically by the deploy script. `POSTGRES_USER`,
`POSTGRES_PASSWORD`, and `POSTGRES_DB` define the database container; Compose
derives `DATABASE_URL` and `REDIS_URL` from them, so there is nothing else to
configure.

---

## 2. Static IP + DNS

Reserve a static IP so the address survives VM restarts:

```powershell
gcloud compute addresses create audionotes-vm-ip --region asia-south1
gcloud compute addresses describe audionotes-vm-ip --region asia-south1 --format "value(address)"
```

For `DOMAIN`, choose one:

- **You own a domain**: create an `A` record pointing it at that IP. Set
  `DOMAIN=api.yourdomain.com`.
- **No domain (quick demo)**: use `sslip.io`, which resolves any
  `<ip>.sslip.io` to that IP. Set `DOMAIN=<ip>.sslip.io`. Caddy will obtain a
  real Let's Encrypt certificate for it — no DNS setup required.

Set `BACKEND_PUBLIC_URL=https://<DOMAIN>` to match.

---

## 3. Deploy the backend

The script enables APIs, creates the Artifact Registry repo and (optionally) the
VM, builds the image with Cloud Build, then pulls and starts the stack.

```powershell
cd deploy
./deploy.ps1 -ProjectId MY_PROJECT_ID -CreateVm
```

What it does:

1. Enables `compute`, `artifactregistry`, `cloudbuild`.
2. Creates Artifact Registry repo `audionotes`.
3. `gcloud builds submit backend --tag <region>-docker.pkg.dev/.../audionotes:<git-sha>`.
4. Creates VM `audionotes-vm` (`e2-medium`, Debian 12, 30 GB, static IP) and a
   firewall rule for `tcp:80,443` (skipped if the VM already exists).
5. Installs Docker on the VM (`vm-setup.sh`).
6. Copies `docker-compose.yml`, `Caddyfile`, `.env` to `/opt/audionotes`.
7. Starts `db` + `redis`, waits for their healthchecks, runs
   `alembic upgrade head`, then `docker compose up -d` for the rest.

Options: `-Region`, `-Zone`, `-VmName`, `-Tag`, `-Domain`, `-MachineType`,
`-SkipBuild`, `-SkipSetup`. Pass `-SkipBuild` when only `.env` changed.

On macOS/Linux use `./deploy.sh MY_PROJECT_ID --create-vm` (same flags, kebab-case).

`e2-medium` (2 shared vCPU / 4 GB) is fine for light use. For steadier load bump
to `-MachineType e2-standard-2` (2 dedicated vCPU / 8 GB).

Verify:

```powershell
curl https://<DOMAIN>/health
```

Expect `"database": true` (plus `supabase_storage` / `gnani_configured` flags).
TLS may take a minute on first run while Caddy issues the certificate.

---

## 4. Deploy the frontend

The frontend proxies `/api/*` (and `/health`) to the backend through Vercel, so
the browser only ever talks to the Vercel domain. This removes CORS and keeps
working on networks that block the backend's own hostname (e.g. `*.sslip.io`).
`BACKEND_ORIGIN` (build-time, server-side) is the backend URL; `NEXT_PUBLIC_API_URL`
is the public site URL so the browser calls same-origin.

```powershell
cd deploy
./deploy-frontend.ps1 `
  -ApiUrl https://audionotes.vercel.app `
  -BackendOrigin https://<DOMAIN> `
  -Alias audionotes.vercel.app
```

The first run prompts you to log in to Vercel and link/create the project
(thereafter it is non-interactive). It sets the env vars, deploys with `--prod`,
then points `-Alias` at the new deployment. Pass `-GithubRepo` to populate the
architecture page link, or `-Preview` for a preview deployment.

**Vercel project-root gotcha:** this project is configured with `frontend` as
its Vercel Root Directory. The repository-root `.vercel/project.json` must be
linked to the `audio-notes` project. Do not deploy from `frontend/` if that
directory has its own `.vercel/project.json`: Vercel may select that nested
project link, then look for a second `frontend/` directory and fail with
`The specified Root Directory "frontend" does not exist.` If that happens,
from the repository root relink to the intended project and deploy there:

```powershell
vercel link --yes --team ksauravjet --project audio-notes
vercel --prod --yes
vercel alias set <deployment-url> audionotes.vercel.app
```

Confirm the production and preview environment variables belong to `audio-notes`
before deploying. Keep the Vercel Root Directory set to `frontend`.

> Uploads and SSE answers are proxied by Vercel: large uploads (tens of MB) and
> long agent streams may hit Vercel's proxy limits. For unrestricted uploads and
> streaming, point a custom domain at the VM and set `NEXT_PUBLIC_API_URL` to it
> directly instead of using the proxy.

> **One-time:** Vercel enables Deployment Protection on new projects
> (`all_except_custom_domains`), which returns "Protected by Vercel Authentication"
> for the `*.vercel.app` alias. Disable it once with:
>
> ```powershell
> vercel project protection disable audio-notes --sso
> ```

---

## 5. Wire CORS back to the frontend

CORS is an allowlist read at API startup, so point it at the Vercel URL and
redeploy (no rebuild needed):

```powershell
# edit deploy/.env:
#   FRONTEND_ORIGIN=https://your-app.vercel.app
#   BACKEND_PUBLIC_URL=https://<DOMAIN>
#   FRONTEND_RESET_PASSWORD_URL=https://your-app.vercel.app/reset-password
#   FRONTEND_VERIFY_EMAIL_URL=https://your-app.vercel.app/verify-email
cd deploy
./deploy.ps1 -ProjectId MY_PROJECT_ID -SkipBuild
```

---

## Data and backups

- Postgres data lives in the Docker volume `pg_data`; Redis (including queued
  Celery tasks) in `redis_data`. Both sit on the VM's boot disk.
- **Deleting the VM deletes the database.** Take a disk snapshot or dump before
  teardown.
- Dump the database (gzipped SQL on the VM):

  ```powershell
  gcloud compute ssh audionotes-vm --zone asia-south1-a `
    --command "cd /opt/audionotes && sudo bash backup-db.sh"
  ```

  Then copy it down:

  ```powershell
  gcloud compute scp audionotes-vm:/opt/audionotes/backups/audionotes-YYYYMMDD-HHMMSS.sql.gz . --zone asia-south1-a
  ```

- Restore into the running stack:

  ```powershell
  gcloud compute ssh audionotes-vm --zone asia-south1-a `
    --command "cd /opt/audionotes && gunzip -c backups/<file>.sql.gz | sudo docker compose exec -T db psql -U audionotes -d audionotes"
  ```

For durable backups, schedule a disk snapshot with a resource policy or copy the
dump to a GCS bucket.

---

## Redeploying after code changes

```powershell
cd deploy
./deploy.ps1 -ProjectId MY_PROJECT_ID          # rebuild (git-sha tag) + migrate + restart
./deploy.ps1 -ProjectId MY_PROJECT_ID -SkipBuild   # only .env changed
```

Frontend: re-run `deploy-frontend.ps1`, or connect the GitHub repo in Vercel so
pushes deploy automatically.

> **Reminder:** the Celery worker does not hot-reload. Every backend change needs
> the container recreated (the script does this).

---

## Logs and troubleshooting

```powershell
# container status
gcloud compute ssh audionotes-vm --zone asia-south1-a `
  --command "cd /opt/audionotes && sudo docker compose ps"

# follow logs (api / worker / caddy / db)
gcloud compute ssh audionotes-vm --zone asia-south1-a `
  --command "cd /opt/audionotes && sudo docker compose logs -f --tail=200 api"

gcloud compute ssh audionotes-vm --zone asia-south1-a `
  --command "cd /opt/audionotes && sudo docker compose logs -f --tail=200 worker"
```

Common issues:

- **`/health` shows `"database": false`** — the `db` container is unhealthy.
  Check `docker compose logs db`; a wrong `POSTGRES_PASSWORD` or a corrupted
  `pg_data` volume are the usual causes (change the password before first start,
  or remove the volume with `sudo docker compose down -v` to reset).
- **Uploads stuck at "queued"** — the worker or `redis` is down. Check
  `docker compose logs worker`.
- **Out of memory / OOM kills** — use a larger VM (`-MachineType e2-standard-2`)
  and re-create/resize the instance.
- **CORS errors in the browser** — `FRONTEND_ORIGIN` does not exactly match the
  Vercel origin (scheme + host, no trailing slash). Redeploy with step 5.
- **Certificate not issued** — confirm `DOMAIN` resolves to the static IP and
  the firewall allows 80/443. Caddy needs port 80 for the ACME challenge.
- **`docker login`/pull denied** — the VM service account lacks Artifact
  Registry read access. Grant `roles/artifactregistry.reader` to the compute
  service account, or keep `--scopes=cloud-platform` (the default here).

---

## Teardown

```powershell
gcloud compute instances delete audionotes-vm --zone asia-south1-a
gcloud compute addresses delete audionotes-vm-ip --region asia-south1
gcloud compute firewall-rules delete audionotes-allow-web
gcloud artifacts repositories delete audionotes --location asia-south1
```

Deleting the VM also deletes the Postgres and Redis volumes. Dump the database
first if you need it. Remove the Vercel project from the Vercel dashboard if it
is no longer needed; Supabase Storage objects are deleted from the Supabase
console.
