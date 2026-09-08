#!/usr/bin/env bash
#
# One-shot setup for the approval service.
#
# Run this yourself. It is written so that the signing key never appears
# on a screen, in a file, in a clipboard or in shell history: keygen
# writes the private half to stdout and it is piped straight into
# Cloudflare's secret store. Nobody, including whoever helped build this,
# ever holds it.
#
# That is not ceremony. The gate's claim is that write access to the
# curriculum repository is not enough to approve doctrine, and that claim
# is only true while the key lives in exactly one place.
#
#   ./setup.sh /path/to/data-repo
#
# Prerequisites, in the order the script needs them:
#   * wrangler logged in            npx wrangler login
#   * GOOGLE_CLIENT_ID filled in    services/approval/wrangler.toml
#   * a GitHub fine-grained PAT     Contents: read and write, data repo only

set -euo pipefail

DATA_ROOT="${1:-}"
if [[ -z "$DATA_ROOT" || ! -d "$DATA_ROOT/standards" ]]; then
  echo "usage: ./setup.sh /path/to/data-repo" >&2
  echo "  (the directory containing standards/, content/, approvals/)" >&2
  exit 2
fi
DATA_ROOT="$(cd "$DATA_ROOT" && pwd)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE="$(cd "$HERE/../.." && pwd)"

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

echo "pipeline:  $PIPELINE"
echo "data repo: $DATA_ROOT"
echo

# --- 1. Signing key ------------------------------------------------------

PUB="$DATA_ROOT/standards/approval-key.pub"
if [[ -f "$PUB" ]]; then
  echo "A public key already exists at:"
  echo "  $PUB"
  echo
  echo "Replacing it invalidates every approval already signed with the old"
  echo "key, and those Sundays would need re-approving. Skipping key setup."
  echo "To replace it deliberately, delete that file and re-run."
else
  echo "Generating the signing key and piping it straight to Cloudflare."
  echo "It is not displayed and not written to disk."
  STPAUL_DATA="$DATA_ROOT" python "$PIPELINE/tools/keygen.py" --private-to-stdout \
    | npx wrangler secret put APPROVAL_SIGNING_KEY
  echo
  echo "Commit the public key:"
  echo "  cd '$DATA_ROOT' && git add standards/approval-key.pub && git commit"
fi
echo

# --- 2. GitHub token -----------------------------------------------------

echo "GitHub token for committing approvals."
echo "Fine-grained PAT, Contents: read and write, on the data repository"
echo "only. Wrangler will prompt; the value is not echoed."
npx wrangler secret put GITHUB_TOKEN
echo

# --- 3. Deploy -----------------------------------------------------------

echo "Building..."
npx wrangler deploy --dry-run >/dev/null
echo "Deploying..."
npx wrangler deploy

cat <<'MSG'

Done. Remaining, and neither can be automated from here:

  1. standards/reviewers.yml in the data repo: add each reviewer's Google
     address, then set require_signed_approvals: true. That flag is what
     closes the gate.

  2. The test that actually proves it works: approve a Sunday, change one
     comma of it, and re-run

         python tools/verify.py <sunday>

     It must report "stale" and name the changed file. If it does not,
     nothing else about this setup matters.
MSG
