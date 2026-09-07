#!/usr/bin/env python
"""Record a doctrinal review against the exact text that was reviewed.

    python tools/approve.py 2026-09-20-trinity-16 \
        --reviewer "Bryan Wolfmueller" --role pastor \
        --note "reviewed 9/18 with the elders, notes applied"

    python tools/approve.py 2026-09-20-trinity-16 \
        --reviewer "Bryan Wolfmueller" --role pastor --changes-requested \
        --note "Primary guide still says Was ist das?"

The review is bound to the content's canonical hash. Editing so much as
a comma afterwards invalidates it, which is the point: an approval is a
statement about specific words, not about a Sunday.

By default this refuses to record an approval while the linter reports
errors, so a reviewer is never asked to sign text that mechanically
violates a written standard. --force overrides that and records why.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):      # Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


from stpaul.approval import APPROVED, CHANGES_REQUESTED, Review, record_review, reviewer_roster
from stpaul.hashing import content_hash
from stpaul.model import CONTENT_DIR, load_lesson, load_rules
from stpaul.rules import check_lesson, summarize


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sunday")
    ap.add_argument("--reviewer", required=True, help="reviewer's full name")
    ap.add_argument("--role", default="", help="role, e.g. pastor. Defaults to the roster entry.")
    ap.add_argument("--github", default="", help="GitHub login, if the review came through a PR")
    ap.add_argument("--note", default="", help="what was reviewed, and any caveat")
    ap.add_argument("--changes-requested", action="store_true",
                    help="record a rejection rather than an approval")
    ap.add_argument("--force", action="store_true",
                    help="record even though the linter reports errors")
    args = ap.parse_args()

    slug = args.sunday
    sunday_dir = CONTENT_DIR / slug
    if not sunday_dir.is_dir():
        print(f"No such Sunday: {slug}", file=sys.stderr)
        return 2

    roster = reviewer_roster()
    known = {r["name"]: r for r in roster.get("reviewers", [])}
    entry = known.get(args.reviewer)
    role = args.role or (entry or {}).get("role", "")
    github = args.github or (entry or {}).get("github", "")

    if not entry:
        print(f"WARNING: '{args.reviewer}' is not in standards/reviewers.yml.")
        print("         Add them there so the approval roster stays reviewable in git.")
    if not role:
        print("A role is required (--role, or add the reviewer to standards/reviewers.yml).",
              file=sys.stderr)
        return 2

    decision = CHANGES_REQUESTED if args.changes_requested else APPROVED

    if decision == APPROVED:
        lesson = load_lesson(slug)
        findings = check_lesson(load_rules(), lesson)
        errors, warnings = summarize(findings)
        if errors and not args.force:
            print(f"\nRefusing to record an approval: {errors} lint error(s) outstanding.\n")
            for f in findings:
                if f.severity == "error":
                    print(f)
            print("\nFix them, or re-run with --force if the reviewer has seen them "
                  "and approved anyway.")
            return 1
        if warnings:
            print(f"note: {warnings} warning(s) outstanding. Run tools/lint.py to read them.")
        if errors and args.force:
            args.note = (args.note + f" [forced over {errors} lint error(s)]").strip()

    digest, _ = content_hash(sunday_dir)
    review = Review.new(
        reviewer=args.reviewer, role=role, decision=decision,
        content_sha256=digest, note=args.note, github=github,
    )
    record_review(slug, review)

    verb = "Approval" if decision == APPROVED else "Changes-requested"
    print(f"\n{verb} recorded for {slug}")
    print(f"  reviewer: {args.reviewer} ({role})")
    print(f"  content:  {digest}")
    print(f"  at:       {review.at}")
    print(f"\nWritten to approvals/{slug}.approval.json. Commit it.")
    print("Any edit to this Sunday's content from here invalidates this review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
