<#
.SYNOPSIS
  Deploy the Next.js frontend to Vercel and configure its build-time env vars.

.DESCRIPTION
  Uses the Vercel CLI directly (install once with: npm i -g vercel). Run
  `vercel login` first. The first deploy links/creates the project
  non-interactively using the defaults.

  With -BackendOrigin the app proxies /api/* to that origin through Vercel
  (see next.config.ts). NEXT_PUBLIC_API_URL should then be the public site URL
  so the browser calls same-origin. Env vars are set for production + preview
  before deploying.

.EXAMPLE
  ./deploy-frontend.ps1 -ApiUrl https://audionotes.vercel.app -BackendOrigin https://35.244.57.121.sslip.io -Alias audionotes.vercel.app
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$ApiUrl,
  [string]$BackendOrigin = "",
  [string]$Alias = "",
  [string]$GithubRepo = "",
  [int]$MaxUploadMb = 200,
  [switch]$Preview,
  [string]$FrontendDir = ""
)

# Native tools (vercel) log to stderr; do not treat that as fatal. Failures are
# detected via $LASTEXITCODE.
$ErrorActionPreference = "Continue"

$RepoRoot = Split-Path -Parent $PSScriptRoot
if (-not $FrontendDir) { $FrontendDir = Join-Path $RepoRoot "frontend" }

if (-not (Get-Command vercel -ErrorAction SilentlyContinue)) {
  throw "The Vercel CLI was not found on PATH. Install it with: npm i -g vercel"
}
if (-not (Test-Path $FrontendDir)) {
  throw "Frontend directory '$FrontendDir' not found."
}

$ApiUrl = $ApiUrl.TrimEnd("/")
if ($BackendOrigin) { $BackendOrigin = $BackendOrigin.TrimEnd("/") }

Push-Location $FrontendDir
try {
  if (-not (Test-Path (Join-Path $FrontendDir ".vercel\project.json"))) {
    Write-Host "==> Linking Vercel project (non-interactive defaults)" -ForegroundColor Cyan
    & vercel link --yes
    if ($LASTEXITCODE -ne 0) { throw "vercel link failed." }
  }

  function Set-VercelEnv([string]$Name, [string]$Value) {
    foreach ($target in @("production", "preview")) {
      & vercel env rm $Name $target --yes *> $null
      $Value | & vercel env add $Name $target
      if ($LASTEXITCODE -ne 0) { throw "Failed to set $Name for the $target environment." }
    }
    Write-Host "    set $Name ($Value)" -ForegroundColor DarkGray
  }

  Write-Host "==> Configuring Vercel environment" -ForegroundColor Cyan
  Set-VercelEnv "NEXT_PUBLIC_API_URL" $ApiUrl
  Set-VercelEnv "NEXT_PUBLIC_MAX_UPLOAD_MB" "$MaxUploadMb"
  if ($BackendOrigin) { Set-VercelEnv "BACKEND_ORIGIN" $BackendOrigin }
  if ($GithubRepo) { Set-VercelEnv "NEXT_PUBLIC_GITHUB_REPO_URL" $GithubRepo }

  Write-Host "==> Deploying to Vercel" -ForegroundColor Cyan
  $deployArgs = if ($Preview) { @("--yes") } else { @("--prod", "--yes") }
  $deployOut = (& vercel @deployArgs 2>&1 | Out-String)
  Write-Host $deployOut
  if ($LASTEXITCODE -ne 0) { throw "vercel deploy failed." }

  if ($Alias) {
    $match = [regex]::Match($deployOut, '"url"\s*:\s*"([^"]+)"')
    if ($match.Success) {
      $deployment = $match.Groups[1].Value
      Write-Host "==> Pointing $Alias at $deployment" -ForegroundColor Cyan
      & vercel alias set $deployment $Alias
      if ($LASTEXITCODE -ne 0) { Write-Warning "Could not set alias $Alias." }
    } else {
      Write-Warning "Could not find the deployment URL in the Vercel output; skipping alias."
    }
  }
}
finally {
  Pop-Location
}

Write-Host ""
Write-Host "Frontend deployed." -ForegroundColor Green
if ($Alias) { Write-Host "  URL: https://$Alias" -ForegroundColor Green }
Write-Host "Now set FRONTEND_ORIGIN in deploy/.env to the same URL and run" -ForegroundColor Green
Write-Host "deploy.ps1 -SkipBuild so the backend allowlist matches." -ForegroundColor Green
