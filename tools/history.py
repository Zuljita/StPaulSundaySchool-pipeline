#!/usr/bin/env python
"""Who approved what, and when.

    python tools/history.py                       # everything, newest first
    python tools/history.py 2026-09-27-trinity-17 # one Sunday
    python tools/history.py --reviewer "Bryan"    # one person
    python tools/history.py --json                # for a spreadsheet or a report

The approval records are JSON files, one per Sunday, and git history holds
the rest. Both are exact and neither is readable. This prints the trail as
a person would want to read it: a chronological log of decisions, who made
them, and whether each one still stands.

WHAT "STILL STANDS" MEANS

An approval is bound to a content hash. If the text changed afterwards,
the review is still a true record of what that person approved, it just no
longer applies to what is in the repository now. Those are shown as
superseded rather than hidden, because "Bryan approved this on the 18th
and it was edited on the 20th" is the interesting part of an audit trail,
not noise to filter out.

Nothing here verifies signatures. tools/verify.py does that and is what
the build gates on. This is the reading view.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from stpaul.approval import APPROVED, load_approval
from stpaul.hashing import content_hash
from stpaul.model import APPROVALS_DIR, CONTENT_DIR, all_sundays
from stpaul.signing import read_public_key, verify_review
from stpaul.model import STANDARDS_DIR

DECISION = {
    "approved": "approved",
    "changes_requested": "changes requested",
}


def collect(slugs: list[str]) -> list[dict]:
    """Every review on record, flattened and sorted newest first."""
    public_key = read_public_key(STANDARDS_DIR)
    rows: list[dict] = []

    for slug in slugs:
        record = load_approval(slug)
        if not record:
            continue
        try:
            current, _ = content_hash(CONTENT_DIR / slug)
        except Exception:
            current = ""

        for r in record.get("reviews", []):
            signed = bool(r.get("signature"))
            rows.append({
                "sunday": slug,
                "at": r.get("at", ""),
                "reviewer": r.get("reviewer", "?"),
                "role": r.get("role", ""),
                "identity": r.get("verified_identity", ""),
                "method": r.get("method", ""),
                "decision": r.get("decision", ""),
                "note": (r.get("note") or "").strip(),
                "content_sha256": r.get("content_sha256", ""),
                "applies_now": bool(current) and r.get("content_sha256") == current,
                "signed": signed,
                "signature_valid": (
                    verify_review(r, slug, public_key) if signed and public_key else None
                ),
            })

    rows.sort(key=lambda r: r["at"], reverse=True)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sunday", nargs="*", help="Sunday slug(s). Default: all.")
    ap.add_argument("--reviewer", default="", help="filter by name, case-insensitive substring")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    slugs = args.sunday or sorted(
        p.name.replace(".approval.json", "")
        for p in APPROVALS_DIR.glob("*.approval.json")
    ) or all_sundays()

    rows = collect(slugs)
    if args.reviewer:
        needle = args.reviewer.lower()
        rows = [r for r in rows if needle in r["reviewer"].lower()]

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
        return 0

    if not rows:
        print("No reviews on record yet.")
        print("\nA review appears here once a pastor approves a Sunday in the review")
        print("app, or once someone runs tools/approve.py.")
        return 0

    print(f"{len(rows)} review(s), newest first\n")
    for r in rows:
        # A review that no longer applies is still a true record of what
        # that person approved; it is marked, not hidden.
        marks = []
        if not r["applies_now"]:
            marks.append("superseded, the text changed after this")
        if r["signed"] and r["signature_valid"] is False:
            marks.append("SIGNATURE DOES NOT VERIFY")
        if not r["signed"]:
            marks.append("unsigned, recorded from the command line")

        who = r["reviewer"] + (f" ({r['role']})" if r["role"] else "")
        print(f"  {r['at']}  {DECISION.get(r['decision'], r['decision'])}")
        print(f"      {who}")
        if r["identity"]:
            print(f"      verified as {r['identity']}")
        print(f"      {r['sunday']}  content {r['content_sha256'][:16]}")
        if r["note"]:
            print(f"      note: {r['note']}")
        for m in marks:
            print(f"      -- {m}")
        print()

    approvals = [r for r in rows if r["decision"] == APPROVED]
    standing = [r for r in approvals if r["applies_now"]]
    people = sorted({r["reviewer"] for r in rows})
    print(f"{len(approvals)} approval(s), {len(standing)} of which still apply "
          f"to the current text.")
    print(f"Reviewers on record: {', '.join(people)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
