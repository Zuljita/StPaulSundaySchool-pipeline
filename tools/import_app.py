#!/usr/bin/env python
"""Lift a Sunday out of the Base44 app snapshot into content/.

    python tools/fetch_app.py
    python tools/import_app.py 2026-09-13-trinity-15

This exists for Rally Day. Its PDFs were exported with the type flattened
to outlines, so they contain no recoverable text and the app is the only
place its words still exist as words. Without this, Rally Day has no
source at all.

WHAT COMES OUT IS MARKED `status: reconstructed`, NOT `approved`.

Nobody reviewed the app's copy as the source of record. It may differ
from what was printed and handed to teachers, and for Trinity 16 it
demonstrably does. Reconstructed content has to be read against the
originals by a person before it can be approved, and the gate will not
build it until someone does.

Nothing here writes prose. Sections come across exactly as the app
serves them.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from stpaul.model import CONTENT_DIR, REPO_ROOT

SNAPSHOT = REPO_ROOT / "build" / "app-snapshot.json"

# The app's (type, level) pairs, mapped onto the twelve-piece manifest.
PIECE_MAP = {
    ("FAMILY-TAKE-HOME", None): ("family-take-home", "family_take_home", "all", 1),
    ("NURSERY-NOTES", None): ("nursery-notes", "nursery_notes", "nursery", 2),
    ("TEACHER-GUIDE", "prek"): ("prek-teacher-guide", "teacher_guide", "pre_k", 3),
    ("STUDENT-HANDOUT", "prek"): ("prek-craft-page", "craft_page", "pre_k", 4),
    ("TEACHER-GUIDE", "primary"): ("primary-teacher-guide", "teacher_guide", "primary", 5),
    ("STUDENT-HANDOUT", "primary"): ("primary-student-handout", "student_handout", "primary", 6),
    ("TEACHER-GUIDE", "intermediate"): ("intermediate-teacher-guide", "teacher_guide", "intermediate", 7),
    ("STUDENT-HANDOUT", "intermediate"): ("intermediate-student-handout", "student_handout", "intermediate", 8),
    ("TEACHER-GUIDE", "middle"): ("middleschool-teacher-guide", "teacher_guide", "middle_school", 9),
    ("STUDENT-HANDOUT", "middle"): ("middleschool-student-handout", "student_handout", "middle_school", 10),
    ("TEACHER-GUIDE", "high"): ("highschool-teacher-guide", "teacher_guide", "high_school", 11),
    ("STUDENT-HANDOUT", "high"): ("highschool-student-handout", "student_handout", "high_school", 12),
}

SUP = re.compile(r"<sup>(\d+)</sup>")
TAG = re.compile(r"<[^>]+>")


def detag(s: str) -> str:
    """Drop the app's HTML, keeping verse numbers as plain text."""
    s = SUP.sub(r"\1 ", s or "")
    s = TAG.sub("", s)
    return html.unescape(s).strip()


def piece_markdown(doc: dict, pid: str, ptype: str, level: str, order: int,
                   source: str) -> str:
    out = [
        "---",
        f"piece: {pid}",
        f"type: {ptype}",
        f"level: {level}",
        f"order: {order}",
        f"imported_from: {source!r}",
        "provenance: base44-app",
        "needs_verification: true",
        "---",
        "",
        f"# {pid.replace('-', ' ').title()}",
        "",
    ]
    for sec in doc.get("sections") or []:
        heading = (sec.get("heading") or "").strip()
        if heading:
            out += [f"## {heading}", ""]
        body = detag(sec.get("body") or "")
        if body:
            out += [body, ""]
        for sub in sec.get("subsections") or []:
            sh = (sub.get("heading") or "").strip()
            if sh:
                out += [f"### {sh}", ""]
            sb = detag(sub.get("body") or "")
            if sb:
                out += [sb, ""]
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sunday")
    ap.add_argument("--snapshot", default=str(SNAPSHOT))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    snap = Path(args.snapshot)
    if not snap.is_file():
        print(f"No snapshot at {snap}. Run: python tools/fetch_app.py", file=sys.stderr)
        return 2

    records = json.loads(snap.read_text(encoding="utf-8"))
    rec = None
    for r in records:
        d = r.get("sunday_date", "")
        day = (r.get("liturgical_day") or "").lower().replace(" ", "-")
        if f"{d}-{day}" == args.sunday:
            rec = r
            break
    if rec is None:
        print(f"The app has no record for {args.sunday}.", file=sys.stderr)
        return 2

    dest = CONTENT_DIR / args.sunday
    if dest.exists() and not args.force:
        print(f"{dest} already exists. Pass --force to overwrite.", file=sys.stderr)
        return 2
    (dest / "pieces").mkdir(parents=True, exist_ok=True)

    found, unmapped = [], []
    for doc in rec.get("documents") or []:
        key = ((doc.get("type") or "").upper(), (doc.get("level") or "").lower() or None)
        target = PIECE_MAP.get(key) or PIECE_MAP.get((key[0], None))
        if not target:
            unmapped.append(key)
            continue
        pid, ptype, level, order = target
        (dest / "pieces" / f"{order:02d}-{pid}.md").write_text(
            piece_markdown(doc, pid, ptype, level, order,
                           f"base44 app, entity Sunday {rec.get('sunday_date')}"),
            encoding="utf-8")
        found.append(pid)
        print(f"  {order:>2}. {pid:<32} {len(doc.get('sections') or [])} section(s)")

    missing = [v[0] for v in PIECE_MAP.values() if v[0] not in found]
    (dest / "lesson.yml").write_text(_lesson_yml(args.sunday, rec, missing), encoding="utf-8")

    print(f"\nImported {len(found)}/12 pieces into content/{args.sunday}/")
    if unmapped:
        print(f"Unmapped app documents: {unmapped}")
    if missing:
        print(f"Not present in the app: {', '.join(sorted(set(missing)))}")
    print("\nMarked status: reconstructed. It will not build until a human has read it\n"
          "against the originals and approved it.")
    return 0


def _lesson_yml(slug: str, rec: dict, missing: list[str]) -> str:
    def q(v):
        return "null" if v in (None, "") else json.dumps(str(v), ensure_ascii=False)

    return f"""# Reconstructed from the Base44 app, not from a reviewed source.
#
# Rally Day's PDFs were exported with the type converted to outlines, so
# they hold no recoverable text. The app is the only place these words
# still exist as words. That makes this the best available record and
# NOT an authoritative one: it was never reviewed as the source, and it
# may differ from what was printed and handed to teachers.
#
# Before this can be approved, someone has to read it against the
# originals. tools/drift.py --against ocr shows where the app and the
# printed pages disagree.

sunday: {slug}
date: {rec.get('sunday_date')}
liturgical_day: {q(rec.get('liturgical_day'))}
special_day: {q(rec.get('special_day'))}

status: reconstructed
provenance: base44-app
needs_verification: true

gospel: {q(rec.get('gospel_reference'))}
translation: {q(rec.get('translation'))}

title: {q(rec.get('title'))}
theme: {q(rec.get('gospel_theme') or rec.get('theme'))}
theme_line_active: false

catechism_link: {q(rec.get('catechism_link'))}
lords_prayer_form: trespasses

hymn:
  title: {q(rec.get('hymn_title'))}
  lsb: {q(rec.get('hymn_number'))}
  license: {q(rec.get('hymn_license'))}

art:
  source: {q(rec.get('art_source'))}
  plate_title: {q(rec.get('art_plate'))}

attribution: >-
  These Sunday School Lessons are built especially for St. Paul Lutheran
  Church by Pastor Bryan Wolfmueller with Claude AI on the same Sunday
  Gospel Lesson.

production_notes:
  - "Reconstructed from the Base44 app on import. Not doctrinally reviewed in this form."

needs_input:
  - "Verify every field above against the printed originals."
{chr(10).join(f'  - "Piece absent from the app: {m}"' for m in sorted(set(missing)))}
"""


if __name__ == "__main__":
    raise SystemExit(main())
