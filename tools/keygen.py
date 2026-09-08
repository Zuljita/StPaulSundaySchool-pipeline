#!/usr/bin/env python
"""Generate the approval signing keypair.

    python tools/keygen.py

Prints the private key and writes the public key to
`standards/approval-key.pub` in the data repository.

**The private key is printed once and never written to disk here.** Put
it straight into the approval service's secret store:

    cd services/approval && npx wrangler secret put APPROVAL_SIGNING_KEY

If it ends up in a file, a shell history, or a chat window, treat it as
compromised: generate a new pair, commit the new public key, and every
approval signed with the old one stops verifying. That last part is the
system working, not a problem to route around.

The public half belongs in git. Everyone verifies against it, so it
should be reviewable, and replacing it should be a visible commit that
someone can question.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from stpaul.model import STANDARDS_DIR
from stpaul.signing import generate_keypair


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing public key")
    ap.add_argument("--private-to-stdout", action="store_true",
                    help="write ONLY the private key to stdout, everything else "
                         "to stderr, so it can be piped straight into a secret "
                         "store without ever being displayed or written to disk")
    args = ap.parse_args()

    pub_path = STANDARDS_DIR / "approval-key.pub"
    if pub_path.is_file() and not args.force:
        print(f"{pub_path} already exists.\n"
              "Replacing it invalidates every approval signed with the old key.\n"
              "Pass --force if that is what you intend.", file=sys.stderr)
        return 2

    private_pem, public_b64 = generate_keypair()

    pub_path.parent.mkdir(parents=True, exist_ok=True)
    pub_path.write_text(
        "# Ed25519 public key for approval signatures.\n"
        "# The private half lives only in the approval service's secret store.\n"
        "# Replacing this line invalidates every approval signed with the old key,\n"
        "# which is why it belongs in git where the change is visible.\n"
        f"{public_b64}\n",
        encoding="utf-8")

    if args.private_to_stdout:
        # Commentary to stderr, key to stdout, so a pipe carries the key and
        # nothing else. The point of the mode: the private half goes from
        # here into the secret store without passing through a screen, a
        # file, a clipboard or a shell history.
        print(f"Public key written to {pub_path}. Commit it.", file=sys.stderr)
        sys.stdout.write(private_pem)
        return 0

    print(f"Public key written to {pub_path}")
    print("Commit it.\n")
    print("Private key, shown once. Put it in the service secret and nowhere else:\n")
    print(private_pem)
    print("Then set, in standards/reviewers.yml:\n")
    print("  policy:\n    require_signed_approvals: true\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
