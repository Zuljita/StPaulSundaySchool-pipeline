# One-shot setup for the approval service. PowerShell 7+.
#
# Run this yourself. It is written so that the signing key never appears
# on a screen, in a file, in a clipboard, or in shell history: keygen
# writes the private half to stdout, it is held in memory only long
# enough to hand to Cloudflare, and then discarded. Nobody, including
# whoever helped build this, ever holds it.
#
# That is not ceremony. The gate's claim is that write access to the
# curriculum repository is not enough to approve doctrine, and that claim
# is only true while the key lives in exactly one place.
#
#   .\setup.ps1 D:\dev\StPaulSundaySchool
#
# Prerequisites, in the order the script needs them:
#   * wrangler logged in            npx wrangler login
#   * GOOGLE_CLIENT_ID filled in    services\approval\wrangler.toml
#   * a GitHub fine-grained PAT     Contents: read and write, data repo only

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string] $DataRoot,

    # Deploy against a public key that is already committed, without
    # generating a new one. Only correct when APPROVAL_SIGNING_KEY is
    # already set in Cloudflare; `npx wrangler secret list` will say.
    [switch] $KeepExistingKey
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path (Join-Path $DataRoot 'standards'))) {
    Write-Error "Not a data repository: $DataRoot`n(expected it to contain standards\, content\, approvals\)"
}
$DataRoot = (Resolve-Path $DataRoot).Path
$Here     = $PSScriptRoot
$Pipeline = (Resolve-Path (Join-Path $Here '..\..')).Path

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

Write-Host "pipeline:  $Pipeline"
Write-Host "data repo: $DataRoot"
Write-Host ""

# --- 1. Signing key ------------------------------------------------------

$pub = Join-Path $DataRoot 'standards\approval-key.pub'
if ((Test-Path $pub) -and $KeepExistingKey) {
    Write-Host "Keeping the existing public key; assuming APPROVAL_SIGNING_KEY is set."
}
elseif (Test-Path $pub) {
    # Stop rather than skip. A committed public key does not prove the
    # matching secret is set in Cloudflare: a key file can arrive from a
    # stray test run, a half-finished setup, or a checkout of someone
    # else's work. Skipping in that state deploys a service that cannot
    # sign, reports success, and fails to verify every approval
    # afterwards. That is a bad thing to discover from a pastor.
    Write-Host @"
A public key already exists at:
  $pub

That does not prove the matching private key is set in Cloudflare, so
this script will not guess. Two cases:

  The key is live, and APPROVAL_SIGNING_KEY is already set.
    Confirm with:  npx wrangler secret list
    Then re-run with -KeepExistingKey to skip key setup and deploy.

  The key is stale, from a test run or an abandoned setup.
    Delete it and re-run. A new pair will be generated:
      Remove-Item '$pub'

Replacing a genuinely live key invalidates every approval signed with
it, and those Sundays would need re-approving, so check before deleting.
"@ -ForegroundColor Yellow
    exit 1
}
else {
    Write-Host "Generating the signing key and handing it straight to Cloudflare."
    Write-Host "It is not displayed and not written to disk."

    $env:STPAUL_DATA = $DataRoot
    # Native stderr carries the progress line; let it through to the console
    # rather than turning it into a terminating error.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $pem = (& python (Join-Path $Pipeline 'tools\keygen.py') --private-to-stdout) -join "`n"
    $ErrorActionPreference = $prev

    if (-not $pem.StartsWith('-----BEGIN PRIVATE KEY-----')) {
        Write-Error "keygen did not produce a PEM private key. Nothing was sent to Cloudflare."
    }

    try {
        $pem | & npx wrangler secret put APPROVAL_SIGNING_KEY
        if ($LASTEXITCODE -ne 0) { Write-Error "wrangler secret put failed." }
    }
    finally {
        # Out of memory as soon as it is no longer needed. It was never on
        # disk and never echoed.
        Remove-Variable pem -ErrorAction SilentlyContinue
        [System.GC]::Collect()
    }

    Write-Host ""
    Write-Host "Commit the public key:"
    Write-Host "  Set-Location '$DataRoot'; git add standards\approval-key.pub; git commit"
}
Write-Host ""

# --- 2. GitHub token -----------------------------------------------------

Write-Host "GitHub token for committing approvals."
Write-Host "Fine-grained PAT, Contents: read and write, on the data repository"
Write-Host "only. Wrangler will prompt; the value is not echoed."
& npx wrangler secret put GITHUB_TOKEN
if ($LASTEXITCODE -ne 0) { Write-Error "wrangler secret put failed." }
Write-Host ""

# --- 3. Deploy -----------------------------------------------------------

Write-Host "Building..."
& npx wrangler deploy --dry-run | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Error "build failed; nothing deployed." }

Write-Host "Deploying..."
& npx wrangler deploy
if ($LASTEXITCODE -ne 0) { Write-Error "deploy failed." }

Write-Host @'

Done. Remaining, and neither can be automated from here:

  1. standards\reviewers.yml in the data repo: add each reviewer's Google
     address, then set require_signed_approvals: true. That flag is what
     closes the gate.

  2. The test that actually proves it works: approve a Sunday, change one
     comma of it, and re-run

         python tools\verify.py <sunday>

     It must report "stale" and name the changed file. If it does not,
     nothing else about this setup matters.
'@
