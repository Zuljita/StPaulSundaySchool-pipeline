<#
.SYNOPSIS
    Upload a staged site to R2.

.DESCRIPTION
    Reads r2-manifest.json out of a directory staged by
    tools\publish_site.py and uploads each object under the key the
    manifest gives it. The key is the URL path, so what lands in the
    bucket is what the site serves.

    This script decides nothing. publish_site.py already re-checked, for
    every Sunday it staged, that the content still hashes to what was
    built and still carries a current approval. If a Sunday should not be
    published, it is not in the staged directory to begin with.

.EXAMPLE
    python tools\build.py --all
    python tools\publish_site.py
    pwsh services\site\publish.ps1 -Staged D:\dev\StPaulSundaySchool\dist-site

.NOTES
    Needs wrangler authenticated against the account holding the bucket:
        npx wrangler login
    or CLOUDFLARE_API_TOKEN set to a token with Workers R2 Storage: Edit.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string] $Staged,

    [string] $Bucket = "stpaul-sundayschool",

    # Print what would be uploaded and stop.
    [switch] $WhatIfOnly
)

$ErrorActionPreference = "Stop"

$manifestPath = Join-Path $Staged "r2-manifest.json"
if (-not (Test-Path $manifestPath)) {
    throw "No r2-manifest.json in $Staged. Run: python tools\publish_site.py"
}

$objects = (Get-Content $manifestPath -Raw | ConvertFrom-Json).objects
if (-not $objects) { throw "The manifest lists no objects." }

$total = ($objects | Measure-Object -Property bytes -Sum).Sum
Write-Host ("{0} object(s), {1:N0} KiB -> r2://{2}" -f $objects.Count, ($total / 1KB), $Bucket)

if ($WhatIfOnly) {
    $objects | ForEach-Object { Write-Host ("  {0}" -f $_.key) }
    return
}

$done = 0
foreach ($o in $objects) {
    $file = Join-Path $Staged ($o.key -replace '/', '\')
    if (-not (Test-Path $file)) { throw "Manifest names a file that is not staged: $($o.key)" }

    # --remote writes to the real bucket rather than a local simulation.
    npx --yes wrangler@4 r2 object put "$Bucket/$($o.key)" `
        --file "$file" `
        --content-type $o.content_type `
        --remote | Out-Null

    if ($LASTEXITCODE -ne 0) { throw "Upload failed at $($o.key)." }

    $done++
    Write-Host ("  [{0}/{1}] {2}" -f $done, $objects.Count, $o.key)
}

Write-Host ""
Write-Host "Uploaded $done object(s)."
Write-Host "The site serves them at the hostname in services\site\wrangler.toml."
