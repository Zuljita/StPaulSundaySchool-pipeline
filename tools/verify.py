#!/usr/bin/env python
"""Ask whether a Sunday's content still matches what was approved.

    python tools/verify.py                       # every Sunday
    python tools/verify.py 2026-09-20-trinity-16
    python tools/verify.py --json

Exit code is 1 if any requested Sunday is not currently approved. This is
what CI runs, and what build.py calls before it will write anything.

The four answers:

  approved         content hash matches, policy satisfied. Safe to build.
  stale            content changed after review. Names the changed files.
  insufficient     text is the reviewed text, but not enough reviewers
                   have signed off, or a required role has not.
  no-approval-file never reviewed.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):      # Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


from stpaul.approval import OK, verify
from stpaul.model import all_sundays


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sunday", nargs="*")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    slugs = args.sunday or all_sundays()
    if not slugs:
        print("No Sundays found under content/.")
        return 0

    results = {}
    failed = False

    for slug in slugs:
        v = verify(slug)
        results[slug] = asdict(v)
        if not v.ok:
            failed = True
        if args.json:
            continue

        mark = "OK  " if v.ok else "FAIL"
        print(f"\n{mark}  {slug}")
        print(f"      status:  {v.status}")
        print(f"      content: {v.current_hash[:16]}")
        if v.approved_hash and v.approved_hash != v.current_hash:
            print(f"      approved:{v.approved_hash[:16]}  <-- does not match")
        print(f"      {v.detail}")
        if v.changed_files:
            print(f"      changed since approval ({len(v.changed_files)}):")
            for f in v.changed_files[:20]:
                print(f"        - {f}")
            if len(v.changed_files) > 20:
                print(f"        ... and {len(v.changed_files) - 20} more")
        if v.approving_reviews:
            for r in v.approving_reviews:
                print(f"      approved by {r['reviewer']} ({r['role']}) at {r['at']}")

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
