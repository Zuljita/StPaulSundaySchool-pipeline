# One-shot setup for the approval service. PowerShell 7+.
#
# Two things, then a deploy: the GitHub token the Worker commits
# approvals with, and the deploy itself. That token is the only secret
# this service holds, and it is scoped to Contents on the data repository
# and nothing else.
#
#   .\setup.ps1
#
# Prerequisites, in the order the script needs them:
#   * wrangler logged in            npx wrangler login
#   * GOOGLE_CLIENT_ID filled in    services\approval\wrangler.toml
#   * a GitHub fine-grained PAT     Contents: read and write, data repo only

[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$Here = $PSScriptRoot

# --- 0. Refuse to run half-configured ------------------------------------

$toml = Get-Content (Join-Path $Here 'wrangler.toml') -Raw
if ($toml -match '(?m)^GOOGLE_CLIENT_ID = ""') {
    Write-Host @'
GOOGLE_CLIENT_ID is still empty in wrangler.toml.

Deploying now would produce a service that rejects every sign-in, which
looks like a broken deployment rather than a missing value. Create the
OAuth client first (review\README.md, step 2), paste the client ID in,
then re-run.
'@ -ForegroundColor Yellow
    exit 1
}

# --- 1. GitHub token -----------------------------------------------------

Write-Host "GitHub token for committing approvals."
Write-Host "Fine-grained PAT, Contents: read and write, on the data repository"
Write-Host "only. Wrangler will prompt; the value is not echoed."
& npx wrangler secret put GITHUB_TOKEN
if ($LASTEXITCODE -ne 0) { Write-Error "wrangler secret put failed." }
Write-Host ""

# --- 2. Deploy -----------------------------------------------------------

Write-Host "Building..."
& npx wrangler deploy --dry-run | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Error "build failed; nothing deployed." }

Write-Host "Deploying..."
& npx wrangler deploy
if ($LASTEXITCODE -ne 0) { Write-Error "deploy failed." }

Write-Host @'

Done. Remaining, and neither can be automated from here:

  1. standards\reviewers.yml in the data repo: add each reviewer's Google
     address. That roster is what decides who may approve.

  2. The test that actually proves it works: approve a Sunday, change one
     comma of it, and re-run

         python tools\verify.py <sunday>

     It must report "stale" and name the changed file. If it does not,
     nothing else about this setup matters.
'@
