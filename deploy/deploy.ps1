<#
.SYNOPSIS
  Build the Audio Notes backend image with Cloud Build and deploy it to a
  Compute Engine VM running Docker Compose (Caddy + API + Celery worker).

.DESCRIPTION
  Steps:
    1. Enable the needed Google Cloud APIs.
    2. Ensure an Artifact Registry repository exists.
    3. Build + push backend/Dockerfile to Artifact Registry (Cloud Build).
    4. Optionally create the VM (static IP + firewall for 80/443).
    5. Bootstrap Docker on the VM (deploy/vm-setup.sh).
    6. Copy docker-compose.yml, Caddyfile and .env to /opt/audionotes.
    7. Pull, run migrations, and start the stack.

  Postgres and Redis run as containers on the VM (persistent volumes) and are
  configured via POSTGRES_* in deploy/.env. Only Supabase Storage is external.

.EXAMPLE
  ./deploy.ps1 -ProjectId my-project -CreateVm
.EXAMPLE
  ./deploy.ps1 -ProjectId my-project -Tag v1 -SkipBuild
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$ProjectId,
  [string]$Region = "asia-south1",
  [string]$Zone = "asia-south1-a",
  [string]$VmName = "audionotes-vm",
  [string]$Repository = "audionotes",
  [string]$ImageName = "audionotes",
  [string]$Tag = "",
  [string]$EnvFile = "",
  [string]$BackendDir = "",
  [string]$Domain = "",
  [switch]$CreateVm,
  [string]$IpName = "",
  [string]$MachineType = "e2-medium",
  [switch]$SkipBuild,
  [switch]$SkipSetup
)

# Keep this at "Continue": native tools (gcloud/git) write progress and
# non-fatal warnings to stderr, and converting those to terminating errors
# would abort on healthy output. Failures are detected via $LASTEXITCODE below.
$ErrorActionPreference = "Continue"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $BackendDir) { $BackendDir = Join-Path $RepoRoot "backend" }
if (-not $EnvFile) { $EnvFile = Join-Path $PSScriptRoot ".env" }
if (-not $IpName) { $IpName = "$VmName-ip" }

function Require-Command([string]$Name) {
  if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
    throw "Required command '$Name' was not found on PATH."
  }
}

function Invoke-Gcloud {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
  & gcloud @Arguments
  if ($LASTEXITCODE -ne 0) { throw "gcloud $($Arguments -join ' ') failed (exit $LASTEXITCODE)." }
}

function Test-Gcloud {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
  & gcloud @Arguments *> $null
  return ($LASTEXITCODE -eq 0)
}

# A just-created VM refuses SSH for the first ~30-60s. Poll before scp/ssh.
function Wait-ForVmSsh {
  param([string]$Name, [string]$ZoneName, [string]$Proj)
  for ($attempt = 1; $attempt -le 30; $attempt++) {
    & gcloud compute ssh $Name "--zone=$ZoneName" "--project=$Proj" "--quiet" "--command=echo ready" *> $null
    if ($LASTEXITCODE -eq 0) {
      Write-Host "    SSH is ready on $Name" -ForegroundColor DarkGray
      return
    }
    Write-Host "    Waiting for SSH on $Name ($attempt/30)..." -ForegroundColor DarkGray
    Start-Sleep -Seconds 10
  }
  throw "VM '$Name' did not become reachable over SSH."
}

Require-Command "gcloud"

Write-Host "==> Project $ProjectId ($Region / $Zone)" -ForegroundColor Cyan
Invoke-Gcloud config set project $ProjectId | Out-Null

Write-Host "==> Enabling APIs (compute, artifactregistry, cloudbuild)" -ForegroundColor Cyan
Invoke-Gcloud services enable compute.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com "--project=$ProjectId"

if (-not (Test-Gcloud artifacts repositories describe $Repository "--location=$Region" "--project=$ProjectId" "--format=value(name)")) {
  Write-Host "==> Creating Artifact Registry repository '$Repository'" -ForegroundColor Cyan
  Invoke-Gcloud artifacts repositories create $Repository "--repository-format=docker" "--location=$Region" "--description=Audio Notes backend images" "--project=$ProjectId"
}

# Cloud Build and the VM run as the Compute Engine default service account.
# Some projects do not auto-grant it roles, in which case builds cannot read
# their source and the VM cannot pull the image. These bindings are idempotent.
$projectNumber = (& gcloud projects describe $ProjectId "--format=value(projectNumber)").Trim()
$computeSa = "${projectNumber}-compute@developer.gserviceaccount.com"
Write-Host "==> Ensuring IAM for $computeSa" -ForegroundColor Cyan
Invoke-Gcloud projects add-iam-policy-binding $ProjectId "--member=serviceAccount:$computeSa" "--role=roles/cloudbuild.builds.builder" "--condition=None" "--quiet" | Out-Null
Invoke-Gcloud artifacts repositories add-iam-policy-binding $Repository "--location=$Region" "--member=serviceAccount:$computeSa" "--role=roles/artifactregistry.reader" "--quiet" | Out-Null

if (-not $Tag) {
  $Tag = "latest"
  try {
    $sha = (& git -C $RepoRoot rev-parse --short HEAD 2>$null)
    if ($LASTEXITCODE -eq 0 -and $sha) { $Tag = $sha.Trim() }
  } catch { }
}
$Image = "$Region-docker.pkg.dev/$ProjectId/$Repository/${ImageName}:$Tag"

if (-not $SkipBuild) {
  Write-Host "==> Building + pushing $Image via Cloud Build" -ForegroundColor Cyan
  Invoke-Gcloud builds submit $BackendDir "--tag=$Image" "--project=$ProjectId"
} else {
  Write-Host "==> Skipping build; deploying existing $Image" -ForegroundColor Yellow
}

if (-not (Test-Path $EnvFile)) {
  throw "Env file '$EnvFile' not found. Copy deploy/.env.example to deploy/.env and fill it in."
}

$envText = [System.IO.File]::ReadAllText($EnvFile)
$envText = [regex]::Replace($envText, '(?m)^IMAGE=.*$', "IMAGE=$Image")
if ($Domain) { $envText = [regex]::Replace($envText, '(?m)^DOMAIN=.*$', "DOMAIN=$Domain") }

$domainMatch = [regex]::Match($envText, '(?m)^DOMAIN=(.+)$')
$Domain = if ($domainMatch.Success) { $domainMatch.Groups[1].Value.Trim() } else { "" }
if (-not $Domain -or $Domain -eq "CHANGE_ME") {
  throw "Set DOMAIN in $EnvFile (or pass -Domain), e.g. <VM_STATIC_IP>.sslip.io or your own domain."
}

$pgMatch = [regex]::Match($envText, '(?m)^POSTGRES_PASSWORD=(.+)$')
if (-not $pgMatch.Success -or $pgMatch.Groups[1].Value.Trim() -eq "CHANGE_ME") {
  throw "Set POSTGRES_PASSWORD in $EnvFile (generate one with: python -c ""import secrets; print(secrets.token_urlsafe(32))"")."
}

# Stage the exact files that go to the VM (avoids a BOM and keeps scp simple).
$stageDir = Join-Path $PSScriptRoot ".deploy-stage"
New-Item -ItemType Directory -Force -Path $stageDir | Out-Null
Copy-Item (Join-Path $PSScriptRoot "docker-compose.prod.yml") (Join-Path $stageDir "docker-compose.yml") -Force
Copy-Item (Join-Path $PSScriptRoot "Caddyfile") $stageDir -Force
Copy-Item (Join-Path $PSScriptRoot "vm-setup.sh") $stageDir -Force
Copy-Item (Join-Path $PSScriptRoot "remote-deploy.sh") $stageDir -Force
$stagedEnv = Join-Path $stageDir ".env"
[System.IO.File]::WriteAllText($stagedEnv, $envText, (New-Object System.Text.UTF8Encoding($false)))

# The VM's service-account scopes often cannot pull from Artifact Registry, so
# prefer a short-lived token from the local gcloud user. The remote script falls
# back to the instance metadata token when this is empty.
$accessToken = ""
try { $accessToken = ((& gcloud auth print-access-token 2>$null) -join "").Trim() } catch { }
$stagedToken = Join-Path $stageDir ".docker-token"
[System.IO.File]::WriteAllText($stagedToken, $accessToken, (New-Object System.Text.UTF8Encoding($false)))
if (-not $accessToken) {
  Write-Warning "Could not read a local gcloud access token; the VM will try its own service-account credentials."
}

$vmExists = Test-Gcloud compute instances describe $VmName "--zone=$Zone" "--project=$ProjectId" "--format=value(name)"
if (-not $vmExists) {
  if (-not $CreateVm) {
    throw "VM '$VmName' not found in zone $Zone. Re-run with -CreateVm, or create it manually (see deploy/README.md)."
  }
  Write-Host "==> Reserving static IP '$IpName'" -ForegroundColor Cyan
  if (-not (Test-Gcloud compute addresses describe $IpName "--region=$Region" "--project=$ProjectId" "--format=value(address)")) {
    Invoke-Gcloud compute addresses create $IpName "--region=$Region" "--project=$ProjectId"
  }
  $ip = (& gcloud compute addresses describe $IpName "--region=$Region" "--project=$ProjectId" "--format=value(address)").Trim()

  if (-not (Test-Gcloud compute firewall-rules describe "audionotes-allow-web" "--project=$ProjectId")) {
    Write-Host "==> Creating firewall rule for tcp:80,tcp:443" -ForegroundColor Cyan
    Invoke-Gcloud compute firewall-rules create "audionotes-allow-web" "--allow=tcp:80,tcp:443" "--target-tags=audionotes-backend" "--direction=INGRESS" "--project=$ProjectId"
  }

  Write-Host "==> Creating VM '$VmName' ($MachineType) at $ip" -ForegroundColor Cyan
  Invoke-Gcloud compute instances create $VmName "--zone=$Zone" "--project=$ProjectId" "--machine-type=$MachineType" "--image-family=debian-12" "--image-project=debian-cloud" "--boot-disk-size=30GB" "--address=$IpName" "--tags=audionotes-backend" "--scopes=cloud-platform"
  Write-Host "    Backend public IP: $ip" -ForegroundColor Green
  Write-Host "    If you use .sslip.io, set DOMAIN=$ip.sslip.io in $EnvFile and re-run." -ForegroundColor Yellow
}

Write-Host "==> Waiting for SSH on $VmName" -ForegroundColor Cyan
Wait-ForVmSsh -Name $VmName -ZoneName $Zone -Proj $ProjectId

if (-not $SkipSetup) {
  Write-Host "==> Bootstrapping Docker on $VmName" -ForegroundColor Cyan
  Invoke-Gcloud compute scp (Join-Path $stageDir "vm-setup.sh") "${VmName}:/tmp/audionotes-vm-setup.sh" "--zone=$Zone" "--project=$ProjectId" "--quiet"
  Invoke-Gcloud compute ssh $VmName "--zone=$Zone" "--project=$ProjectId" "--quiet" "--command=sudo bash /tmp/audionotes-vm-setup.sh"
}

Write-Host "==> Uploading compose files to $VmName" -ForegroundColor Cyan
Invoke-Gcloud compute ssh $VmName "--zone=$Zone" "--project=$ProjectId" "--quiet" "--command=mkdir -p /tmp/audionotes-deploy"
Invoke-Gcloud compute scp (Join-Path $stageDir "docker-compose.yml") (Join-Path $stageDir "Caddyfile") (Join-Path $stageDir "remote-deploy.sh") $stagedEnv $stagedToken "${VmName}:/tmp/audionotes-deploy/" "--zone=$Zone" "--project=$ProjectId" "--quiet"

Write-Host "==> Deploying stack on $VmName" -ForegroundColor Cyan
# A multi-line --command is split on newlines by the Windows/gcloud CLI chain,
# so the remote steps live in remote-deploy.sh and run as a single-line command.
Invoke-Gcloud compute ssh $VmName "--zone=$Zone" "--project=$ProjectId" "--quiet" "--command=sudo bash /tmp/audionotes-deploy/remote-deploy.sh $Region"

Write-Host "==> Verifying https://$Domain/health" -ForegroundColor Cyan
Start-Sleep -Seconds 5
try {
  $health = Invoke-WebRequest -UseBasicParsing -Uri "https://$Domain/health" -TimeoutSec 30
  Write-Host $health.Content -ForegroundColor Green
} catch {
  Write-Warning "Health check failed (DNS may still be propagating, or Caddy is still issuing the certificate): $($_.Exception.Message)"
}

Write-Host ""
Write-Host "Backend deployed." -ForegroundColor Green
Write-Host "  API base:  https://$Domain"
Write-Host "  Image:     $Image"
Write-Host "  Next step: deploy the frontend (deploy/deploy-frontend.ps1) and then set"
Write-Host "             FRONTEND_ORIGIN in $EnvFile to the Vercel URL and re-run this script."
