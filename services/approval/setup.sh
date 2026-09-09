#!/usr/bin/env bash
#
# One-shot setup for the approval service.
#
# Two things, then a deploy: the GitHub token the Worker commits
# approvals with, and the deploy itself. The token is the only secret
# this service holds, and it is scoped to Contents on the data repository
# and nothing else.
#
#   ./setup.sh
#
# Prerequisites, in the order the script needs them:
#   * wrangler logged in            npx wrangler login
#   * GOOGLE_CLIENT_ID filled in    services/approval/wrangler.toml
#   * a GitHub fine-grained PAT     Contents: read and write, data repo only

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- 0. Refuse to run half-configured ------------------------------------

if grep -qE '^GOOGLE_CLIENT_ID = ""' "$HERE/wrangler.toml"; then
  cat >&2 <<'MSG'
GOOGLE_CLIENT_ID is still empty in wrangler.toml.

Deploying now would produce a service that rejects every sign-in, which
looks like a broken deployment rather than a missing value. Create the
OAuth client first (review/README.md, step 2), paste the client ID in,
then re-run.
MSG
  exit 1
fi

# --- 1. GitHub token -----------------------------------------------------

echo "GitHub token for committing approvals."
echo "Fine-grained PAT, Contents: read and write, on the data repository"
echo "only. Wrangler will prompt; the value is not echoed."
npx wrangler secret put GITHUB_TOKEN
echo

# --- 2. Deploy -----------------------------------------------------------

echo "Building..."
npx wrangler deploy --dry-run >/dev/null
echo "Deploying..."
npx wrangler deploy

cat <<'MSG'

Done. Remaining, and neither can be automated from here:

  1. standards/reviewers.yml in the data repo: add each reviewer's Google
     address. That roster is what decides who may approve.

  2. The test that actually proves it works: approve a Sunday, change one
     comma of it, and re-run

         python tools/verify.py <sunday>

     It must report "stale" and name the changed file. If it does not,
     nothing else about this setup matters.
MSG
