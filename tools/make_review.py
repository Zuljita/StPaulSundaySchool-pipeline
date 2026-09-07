#!/usr/bin/env python
"""Build the data the review app reads.

    python tools/make_review.py                      # every Sunday
    python tools/make_review.py 2026-09-27-trinity-17

Writes review/data/<sunday>.json and review/data/index.json.

The review app is static. It reads these files and nothing else, so the
words a pastor reads on screen come from the same `content/` files the
build renders, through the same parser. There is no second copy of the
text to drift.

The content hash travels with the data. When a reviewer approves, that
hash is what the approval is bound to, so an approval can never quietly
attach to text other than the text on the reviewer's screen.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from stpaul.approval import load_approval, verify
from stpaul.hashing import content_hash
from stpaul.model import CONTENT_DIR, DATA_ROOT, all_sundays, load_lesson, load_rules
from stpaul.render.handoff import piece_heading
from stpaul.rules import check_lesson, summarize

# Generated from content, so it belongs with the data, not with the
# pipeline. The approval service reads it from the data repository to
# decide what a reviewer is actually approving.
REVIEW_DATA = DATA_ROOT / "review" / "data"


def build(slug: str) -> dict:
    lesson = load_lesson(slug)
    digest, manifest = content_hash(CONTENT_DIR / slug)
    findings = check_lesson(load_rules(), lesson)
    errors, warnings = summarize(findings)
    v = verify(slug)
    record = load_approval(slug) or {}

    by_piece: dict[str, list] = {}
    for f in findings:
        by_piece.setdefault(f.piece or "_lesson", []).append(asdict(f))

    return {
        "sunday": slug,
        "content_sha256": digest,
        "files": manifest,
        "meta": {k: (str(val) if hasattr(val, "isoformat") else val)
                 for k, val in lesson.meta.items()},
        "status": lesson.status,
        "approval": {
            "state": v.status,
            "ok": v.ok,
            "detail": v.detail,
            "reviews": record.get("reviews", []),
            "policy": record.get("policy", {}),
        },
        "lint": {"errors": errors, "warnings": warnings, "by_piece": by_piece},
        "pieces": [
            {
                "id": p.id,
                "type": p.type,
                "level": p.level,
                "order": p.order,
                "label": piece_heading(lesson, p),
                "title": p.title,
                "sha256": manifest.get(p.path.relative_to(CONTENT_DIR / slug).as_posix(), ""),
                "sections": [{"heading": s.heading, "body": s.body} for s in p.sections],
            }
            for p in lesson.pieces
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sunday", nargs="*")
    args = ap.parse_args()

    slugs = args.sunday or all_sundays()
    if not slugs:
        print("No Sundays found under content/.")
        return 0

    REVIEW_DATA.mkdir(parents=True, exist_ok=True)
    index = []
    for slug in slugs:
        data = build(slug)
        (REVIEW_DATA / f"{slug}.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        index.append({
            "sunday": slug,
            "date": data["meta"].get("date"),
            "liturgical_day": data["meta"].get("liturgical_day"),
            "gospel": data["meta"].get("gospel"),
            "content_sha256": data["content_sha256"],
            "approval_state": data["approval"]["state"],
            "errors": data["lint"]["errors"],
            "warnings": data["lint"]["warnings"],
            "pieces": len(data["pieces"]),
        })
        print(f"  {slug}  {len(data['pieces'])} pieces, "
              f"{data['lint']['errors']} error(s), {data['lint']['warnings']} warning(s), "
              f"{data['approval']['state']}")

    index.sort(key=lambda r: str(r["date"]), reverse=True)
    (REVIEW_DATA / "index.json").write_text(
        json.dumps({"sundays": index}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nWrote {len(index)} Sunday(s) to review/data/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
