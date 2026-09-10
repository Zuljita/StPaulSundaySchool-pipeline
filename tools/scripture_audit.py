#!/usr/bin/env python
"""Track Scripture use against each publisher's stated permission limits.

    python tools/scripture_audit.py
    python tools/scripture_audit.py --project 36

No translation this program uses is in the public domain. The NKJV is
(c) 1982 Thomas Nelson; the ESV is (c) 2001 Crossway. Both publishers
allow quotation up to a limit without written permission, and both limits
are cumulative across a work. A one-year lectionary quietly accumulates
verses, so this exists to watch the total rather than assume it.

One test per publisher:

  verses      total quoted, against the no-permission ceiling, and
              projected across a year

A per-piece share-of-work test lived here too and was removed. It
measured one piece's Scripture against that same piece, but both
publishers state their threshold as a share of *the work* the quotation
appears in, and for a curriculum that is the year rather than a single
handout. Measured per-piece it flagged the student sheets that print the
pericope, which is what those sheets are for. Whether a given piece
leans too hard on the text is a judgment about the curriculum, and the
church makes it on review.

This is arithmetic, not legal advice. The church should confirm its own
use with each publisher; a Sunday School curriculum given away is usually
straightforward, and both publishers have a permissions contact.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from stpaul.model import all_sundays, load_lesson, load_rules

REF = re.compile(r"(\d+):(\d+)\s*[-–—]\s*(?:(\d+):)?(\d+)")


def verses_in(reference: str) -> int:
    """Count verses in a pericope reference such as "Luke 7:11-17"."""
    m = REF.search(reference or "")
    if not m:
        return 1 if re.search(r"\d+:\d+", reference or "") else 0
    start_v, end_v = int(m.group(2)), int(m.group(4))
    if m.group(3):          # spans a chapter boundary; not countable from the ref alone
        return 0
    return max(0, end_v - start_v + 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", type=int, default=36,
                    help="Sundays in a full year, for the projection (default 36)")
    args = ap.parse_args()

    rules = load_rules()
    spec = (rules.get("scripture_copyright") or {})
    cfgs = spec.get("translations") or {}

    totals: dict[str, int] = {}
    counts: dict[str, int] = {}

    print(f"{'Sunday':<26} {'transl':<7} {'reference':<20} {'verses':>7}")
    print("-" * 64)

    for slug in all_sundays():
        lesson = load_lesson(slug)
        tr = (lesson.translation or "").upper() or "(undeclared)"
        ref = str(lesson.meta.get("gospel") or "")
        n = verses_in(ref)
        totals[tr] = totals.get(tr, 0) + n
        counts[tr] = counts.get(tr, 0) + 1
        print(f"{slug:<26} {tr:<7} {ref or '(none)':<20} {n:>7}")

    print()
    print("Against each publisher's no-permission ceiling")
    print("-" * 64)
    for tr, total in sorted(totals.items()):
        cfg = cfgs.get(tr)
        if not cfg:
            print(f"  {tr:<12} {total:>4} verses   (no limit on file for this translation)")
            continue
        cap = cfg.get("max_verses_no_permission", 0)
        per = total / max(1, counts[tr])
        proj = per * args.project
        bar = "OVER" if proj > cap else "ok"
        print(f"  {tr:<12} {total:>4} verses so far, cap {cap}")
        print(f"  {'':<12} ~{per:.0f}/Sunday, projected {proj:.0f} over {args.project} Sundays  [{bar}]")
        print(f"  {'':<12} holder: {cfg.get('holder','')}")

    print()
    print("Arithmetic, not legal advice. Confirm the church's own use with each")
    print("publisher. The full text of a copyrighted translation is never stored")
    print("in this repository; only the weekly pericope that actually prints.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
