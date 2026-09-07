#!/usr/bin/env python
"""Compare what the app serves against what the handouts say.

    python tools/drift.py                          # every Sunday the app has
    python tools/drift.py 2026-09-20-trinity-16
    python tools/drift.py --against ocr            # compare to OCR'd print instead

This tool exists to measure a problem the pipeline is meant to make
impossible. Once a Sunday is built from approved content, both outputs
carry the same `source_sha256` and the answer is a string comparison. For
the Sundays produced before that, the app and the print are two
independent retellings and the only way to know how far apart they drifted
is to line them up and look.

Comparison is deliberately coarse. It reports:
  * pieces present in one place and missing from the other,
  * section headings that do not match,
  * sentences in one that do not appear in the other.

It does not try to judge whether a difference matters. That is a reading
question for a person, and the report is meant to give them a short list
rather than two long documents.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from stpaul.model import CONTENT_DIR, DATA_ROOT, load_lesson

SNAPSHOT = DATA_ROOT / "build" / "app-snapshot.json"
OCR_DIR = DATA_ROOT / "build" / "ocr"

# The app names pieces by (type, level); content/ names them by id.
APP_TYPE_TO_ID = {
    ("FAMILY-TAKE-HOME", None): "family-take-home",
    ("NURSERY-NOTES", None): "nursery-notes",
    ("TEACHER-GUIDE", "prek"): "prek-teacher-guide",
    ("TEACHER-GUIDE", "primary"): "primary-teacher-guide",
    ("TEACHER-GUIDE", "intermediate"): "intermediate-teacher-guide",
    ("TEACHER-GUIDE", "middle"): "middleschool-teacher-guide",
    ("TEACHER-GUIDE", "middle_school"): "middleschool-teacher-guide",
    ("TEACHER-GUIDE", "high"): "highschool-teacher-guide",
    ("TEACHER-GUIDE", "high_school"): "highschool-teacher-guide",
    ("STUDENT-HANDOUT", "prek"): "prek-craft-page",
    ("STUDENT-HANDOUT", "primary"): "primary-student-handout",
    ("STUDENT-HANDOUT", "intermediate"): "intermediate-student-handout",
    ("STUDENT-HANDOUT", "middle"): "middleschool-student-handout",
    ("STUDENT-HANDOUT", "middle_school"): "middleschool-student-handout",
    ("STUDENT-HANDOUT", "high"): "highschool-student-handout",
    ("STUDENT-HANDOUT", "high_school"): "highschool-student-handout",
}

TAG = re.compile(r"<[^>]+>")


def _plain(s: str) -> str:
    """Strip markup and normalise quotes so wording is compared, not encoding."""
    s = TAG.sub("", s or "")
    s = (s.replace("’", "'").replace("‘", "'")
           .replace("“", '"').replace("”", '"')
           .replace("—", " ").replace("–", "-"))
    s = re.sub(r"[*_#>]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", _plain(text))
            if len(s.strip()) > 45]


def _app_piece_id(doc: dict) -> str | None:
    t = (doc.get("type") or "").upper()
    lv = (doc.get("level") or "").lower() or None
    return APP_TYPE_TO_ID.get((t, lv)) or APP_TYPE_TO_ID.get((t, None))


def _app_text(doc: dict) -> tuple[str, list[str]]:
    parts, headings = [], []
    for sec in doc.get("sections") or []:
        h = (sec.get("heading") or "").strip()
        if h:
            headings.append(h)
        parts.append(sec.get("body") or "")
        for sub in sec.get("subsections") or []:
            sh = (sub.get("heading") or "").strip()
            if sh:
                headings.append(sh)
            parts.append(sub.get("body") or "")
    return "\n".join(parts), headings


def _norm_heading(h: str) -> str:
    h = _plain(h).lower()
    h = re.sub(r"\((esv|nkjv)\)", "", h)
    h = re.sub(r"[^a-z0-9 ]+", " ", h)
    return re.sub(r"\s+", " ", h).strip()


def compare(slug: str, app_record: dict, against: str) -> dict:
    result = {"sunday": slug, "app_pieces": {}, "issues": []}

    app_docs = {}
    for doc in app_record.get("documents") or []:
        pid = _app_piece_id(doc)
        if pid:
            app_docs[pid] = doc
        else:
            result["issues"].append(
                f"app document of type {doc.get('type')!r} level {doc.get('level')!r} "
                f"does not map to any of the twelve pieces")

    if against == "ocr":
        local = _load_ocr(slug)
        local_label = "OCR of the printed PDFs"
    else:
        local = _load_content(slug)
        local_label = f"content/{slug}"

    result["local_label"] = local_label

    only_local = sorted(set(local) - set(app_docs))
    only_app = sorted(set(app_docs) - set(local))

    if only_local:
        result["issues"].append(
            f"in {local_label} but MISSING FROM THE APP: {', '.join(only_local)}")
    if only_app:
        result["issues"].append(
            f"in the app but missing from {local_label}: {', '.join(only_app)}")

    for pid in sorted(set(app_docs) & set(local)):
        app_body, app_headings = _app_text(app_docs[pid])
        loc_body, loc_headings = local[pid]

        a_h = {_norm_heading(h) for h in app_headings if h}
        l_h = {_norm_heading(h) for h in loc_headings if h}
        app_sents = _sentences(app_body)
        loc_sents = _sentences(loc_body)
        loc_blob = " ".join(loc_sents)
        app_blob = " ".join(app_sents)

        entry = {
            "headings_only_in_app": sorted(a_h - l_h),
            "headings_only_in_local": sorted(l_h - a_h),
            "sentences_only_in_app": [s for s in app_sents if s not in loc_blob],
            "sentences_only_in_local": [s for s in loc_sents if s not in app_blob],
            "app_sentence_count": len(app_sents),
            "local_sentence_count": len(loc_sents),
        }
        result["app_pieces"][pid] = entry
    return result


def _load_content(slug: str) -> dict[str, tuple[str, list[str]]]:
    try:
        lesson = load_lesson(slug)
    except Exception:
        return {}
    return {p.id: (p.body, [s.heading for s in p.sections]) for p in lesson.pieces}


def _load_ocr(slug: str) -> dict[str, tuple[str, list[str]]]:
    """Match OCR text files to piece ids by the numbering in their names."""
    if not OCR_DIR.is_dir():
        return {}
    order_to_id = {
        "01": "family-take-home", "02": "nursery-notes",
        "03": "prek-teacher-guide", "04": "prek-craft-page",
        "05": "primary-teacher-guide", "06": "primary-student-handout",
        "07": "intermediate-teacher-guide", "08": "intermediate-student-handout",
        "09": "middleschool-teacher-guide", "10": "middleschool-student-handout",
        "11": "highschool-teacher-guide", "12": "highschool-student-handout",
    }
    out = {}
    for f in OCR_DIR.glob("*.txt"):
        m = re.search(r"\s-\s(\d\d)\s", f.name)
        if not m:
            continue
        pid = order_to_id.get(m.group(1))
        if pid:
            out[pid] = (f.read_text(encoding="utf-8"), [])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sunday", nargs="*")
    ap.add_argument("--against", choices=["content", "ocr"], default="content")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--snapshot", default=str(SNAPSHOT))
    args = ap.parse_args()

    snap = Path(args.snapshot)
    if not snap.is_file():
        print(f"No app snapshot at {snap}. Run: python tools/fetch_app.py", file=sys.stderr)
        return 2
    records = json.loads(snap.read_text(encoding="utf-8"))

    by_slug = {}
    for r in records:
        d = r.get("sunday_date", "")
        day = (r.get("liturgical_day") or "").lower().replace(" ", "-")
        by_slug[f"{d}-{day}"] = r

    slugs = args.sunday or sorted(by_slug)
    reports = []
    for slug in slugs:
        rec = by_slug.get(slug)
        if not rec:
            print(f"The app has no record for {slug}. It has: {', '.join(sorted(by_slug))}")
            continue
        reports.append(compare(slug, rec, args.against))

    if args.json:
        print(json.dumps(reports, indent=2, ensure_ascii=False))
        return 0

    for rep in reports:
        print(f"\n{'='*72}\n{rep['sunday']}   app  vs  {rep['local_label']}\n{'='*72}")
        for issue in rep["issues"]:
            print(f"  ! {issue}")
        if not rep["app_pieces"]:
            print("  (no pieces in common to compare)")
        for pid, e in rep["app_pieces"].items():
            diffs = (e["headings_only_in_app"] or e["headings_only_in_local"]
                     or e["sentences_only_in_app"] or e["sentences_only_in_local"])
            status = "DIFFERS" if diffs else "matches"
            print(f"\n  {pid:<32} {status}"
                  f"   (app {e['app_sentence_count']} sent., local {e['local_sentence_count']})")
            if e["headings_only_in_local"]:
                print(f"      sections only in print: {', '.join(e['headings_only_in_local'])}")
            if e["headings_only_in_app"]:
                print(f"      sections only in app:   {', '.join(e['headings_only_in_app'])}")
            for s in e["sentences_only_in_app"][:3]:
                print(f"      app only : {s[:120]}")
            for s in e["sentences_only_in_local"][:3]:
                print(f"      print only: {s[:120]}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
