#!/usr/bin/env python
"""Turn approving pull-request reviews into approval records.

Run by .github/workflows/approval.yml when a review is submitted.

    python tools/record_pr_approval.py --pr 14 --repo owner/name

Why identity comes from GitHub rather than from a typed-in name: an
approval asserts that a specific person read specific words. A name in a
form field asserts only that someone typed it. The GitHub account that
submitted the review is the strongest identity available without
building an identity system, and it is already the thing gating who can
merge.

The reviewer must appear in standards/reviewers.yml with a matching
`github:` login. An approval from an account not on the roster is
reported and ignored, so adding an approver stays a visible commit
rather than a click.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from stpaul.approval import (APPROVED, CHANGES_REQUESTED, Review, record_review,
                             reviewer_roster)
from stpaul.hashing import content_hash
from stpaul.model import CONTENT_DIR

SLUG_RE = re.compile(r"(\d{4}-\d{2}-\d{2}-[a-z0-9-]+)")


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout


def sundays_touched(repo: str, pr: int) -> list[str]:
    """Which Sundays does this pull request actually change?"""
    files = json.loads(gh("api", f"repos/{repo}/pulls/{pr}/files", "--paginate"))
    slugs = set()
    for f in files:
        m = re.match(r"content/([^/]+)/", f.get("filename", ""))
        if m:
            slugs.add(m.group(1))
    return sorted(slugs)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    args = ap.parse_args()
    if not args.repo:
        print("--repo is required (or set GITHUB_REPOSITORY)", file=sys.stderr)
        return 2

    roster = reviewer_roster()
    by_login = {(r.get("github") or "").lower(): r
                for r in roster.get("reviewers", []) if r.get("github")}

    slugs = sundays_touched(args.repo, args.pr)
    if not slugs:
        print("This pull request does not change any Sunday under content/. Nothing to record.")
        return 0

    reviews = json.loads(gh("api", f"repos/{args.repo}/pulls/{args.pr}/reviews", "--paginate"))
    if not reviews:
        print("No reviews on this pull request yet.")
        return 0

    wrote = False
    for slug in slugs:
        sunday_dir = CONTENT_DIR / slug
        if not sunday_dir.is_dir():
            continue
        digest, _ = content_hash(sunday_dir)
        print(f"\n{slug}  content {digest[:16]}")

        # Only the latest state per reviewer counts.
        latest: dict[str, dict] = {}
        for r in reviews:
            login = ((r.get("user") or {}).get("login") or "").lower()
            if r.get("state") in ("APPROVED", "CHANGES_REQUESTED"):
                latest[login] = r

        for login, r in sorted(latest.items()):
            entry = by_login.get(login)
            if not entry:
                print(f"  ignored: @{login} approved but is not in standards/reviewers.yml")
                continue

            # The review body carries the hash the reviewer was shown.
            # If it names a different one, the text moved under them.
            body = r.get("body") or ""
            m = re.search(r"content_sha256:\s*([0-9a-f]{64})", body)
            if m and m.group(1) != digest:
                print(f"  ignored: @{login} reviewed {m.group(1)[:16]}, "
                      f"content is now {digest[:16]}")
                continue

            decision = APPROVED if r["state"] == "APPROVED" else CHANGES_REQUESTED
            record_review(slug, Review(
                reviewer=entry["name"], role=entry.get("role", ""),
                decision=decision, at=r.get("submitted_at", ""),
                content_sha256=digest,
                note=f"via pull request #{args.pr}: " + body.split("\n")[0][:200],
                github=login,
            ))
            wrote = True
            print(f"  recorded: {entry['name']} (@{login}) {decision}")

    if not wrote:
        print("\nNothing recorded.")
    else:
        print("\nApproval records updated. Commit approvals/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
