#!/usr/bin/env python
"""Mechanically lift already-produced DOCX pieces into content/.

    python tools/import_legacy.py 2026-09-20-trinity-16 --from archive/2026-09-20-trinity-16

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It does not write, rephrase, complete, or improve one word of curriculum
text. It reads what is in the DOCX and writes exactly that. Where a field
cannot be determined by reading the file, it is emitted as null and
listed under `needs_input:` in lesson.yml for a human to fill.

That restraint is the point of the whole exercise. The failure being
fixed here is a language model regenerating reviewed text; an import that
"tidied up while converting" would be that same failure wearing a
different hat. Anything imported is therefore faithful to the archive,
including its mistakes, and the linter is what surfaces those mistakes
afterwards.

Structure is recovered from the formatting the pieces already carry:
  * a shaded paragraph, or navy all-caps, is a section heading -> `## Heading`
  * text in the secondary blue is a subhead                    -> `### Subhead`
  * everything else is body copy

Two-column pieces (Family Take-Home, Middle School and High School
guides) lay their content out in tables, so the walk descends into table
cells in document order rather than reading top-level paragraphs only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):      # Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


from stpaul.model import CONTENT_DIR, REPO_ROOT

SECONDARY_BLUES = {"5780AB", "2B65B5"}
CHECKBOX = re.compile(r"^[☐☑☐☑]\s*")

# Map archive filenames onto the twelve-piece manifest.
PIECE_MAP = [
    ("Family-TakeHome",            "family-take-home",            "family_take_home", "all",           1),
    ("Nursery-Notes",              "nursery-notes",               "nursery_notes",    "nursery",       2),
    ("PreK-TeacherGuide",          "prek-teacher-guide",          "teacher_guide",    "pre_k",         3),
    ("PreK-CraftPage",             "prek-craft-page",             "craft_page",       "pre_k",         4),
    ("Primary-TeacherGuide",       "primary-teacher-guide",       "teacher_guide",    "primary",       5),
    ("Primary-StudentHandout",     "primary-student-handout",     "student_handout",  "primary",       6),
    ("Intermediate-TeacherGuide",  "intermediate-teacher-guide",  "teacher_guide",    "intermediate",  7),
    ("Intermediate-StudentHandout","intermediate-student-handout","student_handout",  "intermediate",  8),
    ("MiddleSchool-TeacherGuide",  "middleschool-teacher-guide",  "teacher_guide",    "middle_school", 9),
    ("MiddleSchool-StudentHandout","middleschool-student-handout","student_handout",  "middle_school", 10),
    ("HighSchool-TeacherGuide",    "highschool-teacher-guide",    "teacher_guide",    "high_school",   11),
    ("HighSchool-StudentHandout",  "highschool-student-handout",  "student_handout",  "high_school",   12),
]


def _fill(paragraph) -> str | None:
    shd = paragraph._p.find(f".//{{{paragraph._p.nsmap['w']}}}shd") if 'w' in paragraph._p.nsmap else None
    if shd is None:
        shd = paragraph._p.find(".//" + qn("w:shd"))
    if shd is None:
        return None
    val = shd.get(qn("w:fill"))
    return None if val in (None, "auto") else val.upper()


def _first_run_color(paragraph) -> str | None:
    for r in paragraph.runs:
        if not r.text.strip():
            continue
        try:
            if r.font.color is not None and r.font.color.rgb is not None:
                return str(r.font.color.rgb).upper()
        except Exception:
            return None
        return None
    return None


def _is_bold(paragraph) -> bool:
    for r in paragraph.runs:
        if r.text.strip():
            return bool(r.font.bold)
    return False


def _title_case(heading: str) -> str:
    """Print headings are set in caps. Restore readable case for source.

    Only the case is changed, never the words. Small words stay lower
    unless they lead, and a few fixed terms keep their spelling.
    """
    small = {"a", "an", "and", "the", "of", "in", "on", "at", "to", "for", "is", "it", "this"}
    keep = {"god": "God", "christ": "Christ", "jesus": "Jesus", "lsb": "LSB",
            "esv": "ESV", "nkjv": "NKJV", "i": "I"}
    words = heading.strip().split()
    out = []
    for i, w in enumerate(words):
        low = w.lower()
        if low in keep:
            out.append(keep[low])
        elif low in small and i != 0:
            out.append(low)
        elif w.isupper() and len(w) <= 2 and w not in ("A", "I"):
            out.append(w)
        else:
            out.append(low.capitalize())
    return " ".join(out)


NAVIES = {"1E4E72", "002664"}


def _iter_paragraphs(parent):
    """Yield every paragraph in document order, descending into tables.

    python-docx exposes doc.paragraphs and doc.tables as separate flat
    lists, which loses the interleaving. The two-column pieces put most
    of their body inside a table, so reading only top-level paragraphs
    silently drops nearly the whole document.
    """
    from docx.document import Document as _Doc
    from docx.table import Table, _Cell
    from docx.text.paragraph import Paragraph

    if isinstance(parent, _Doc):
        parent_elm = parent.element.body
    elif isinstance(parent, _Cell):
        parent_elm = parent._tc
    else:
        raise TypeError(type(parent))

    for child in parent_elm.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            table = Table(child, parent)
            for row in table.rows:
                for cell in row.cells:
                    yield from _iter_paragraphs(cell)


def _looks_like_heading(text: str, colour: str | None, fill: str | None) -> bool:
    if fill:
        return True
    # Print headings are set in caps. Navy caps with no shading is the
    # same device drawn differently, and appears in the two-column pieces.
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    all_caps = all(c.isupper() for c in letters)
    return bool(all_caps and colour in NAVIES and len(text) < 60)


def extract_piece(path: Path) -> tuple[str, list[str]]:
    """Return (markdown body, list of section headings found).

    Student handouts and craft pages set their section headings in the
    secondary blue rather than in a navy bar, so a first pass that finds
    no navy heading at all re-reads the piece treating the secondary blue
    as the heading level. This follows the document rather than imposing
    a shape on it.
    """
    body, headings = _extract(path, blue_is_heading=False)
    if not headings:
        body, headings = _extract(path, blue_is_heading=True)
    return body, headings


def _extract(path: Path, *, blue_is_heading: bool) -> tuple[str, list[str]]:
    doc = Document(str(path))
    lines: list[str] = []
    headings: list[str] = []
    seen: set[str] = set()

    for p in _iter_paragraphs(doc):
        text = p.text.strip()
        if not text:
            continue
        # Table layouts repeat some runs; skip an exact immediate repeat.
        key = text[:80]
        if key in seen and len(text) > 40:
            continue
        seen.add(key)

        fill = _fill(p)
        colour = _first_run_color(p)

        if _looks_like_heading(text, colour, fill):
            heading = _title_case(text)
            headings.append(heading)
            lines += ["", f"## {heading}", ""]
            continue

        if colour in SECONDARY_BLUES and len(text) < 70 and not text.endswith("."):
            if blue_is_heading:
                heading = _title_case(text)
                headings.append(heading)
                lines += ["", f"## {heading}", ""]
            else:
                lines += ["", f"### {text}", ""]
            continue

        if CHECKBOX.match(text):
            lines.append(f"- {CHECKBOX.sub('', text)}")
            continue

        lines.append(text)
        lines.append("")

    body = "\n".join(lines)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body, headings


def import_sunday(slug: str, src: Path, *, force: bool) -> int:
    dest = CONTENT_DIR / slug
    pieces_dir = dest / "pieces"
    if dest.exists() and not force:
        print(f"{dest} already exists. Pass --force to overwrite.", file=sys.stderr)
        return 2
    pieces_dir.mkdir(parents=True, exist_ok=True)

    found = 0
    missing = []
    for pattern, pid, ptype, level, order in PIECE_MAP:
        matches = [p for p in src.glob("*.docx")
                   if pattern.lower() in p.name.lower().replace(" ", "")
                   and "combined" not in p.name.lower()]
        if not matches:
            missing.append(pid)
            continue
        body, headings = extract_piece(matches[0])
        title = _title_case(pid.replace("-", " "))

        out = [
            "---",
            f"piece: {pid}",
            f"type: {ptype}",
            f"level: {level}",
            f"order: {order}",
            f"imported_from: {matches[0].relative_to(REPO_ROOT).as_posix()!r}",
            "---",
            "",
            f"# {title}",
            "",
            body,
            "",
        ]
        (pieces_dir / f"{order:02d}-{pid}.md").write_text("\n".join(out), encoding="utf-8")
        found += 1
        print(f"  {order:>2}. {pid:<32} {len(headings)} section(s)  <- {matches[0].name}")

    lesson_yml = dest / "lesson.yml"
    if not lesson_yml.exists() or force:
        lesson_yml.write_text(_lesson_stub(slug, missing), encoding="utf-8")

    print(f"\nImported {found}/12 pieces into content/{slug}/")
    if missing:
        print(f"Missing from the archive: {', '.join(missing)}")
    print("\nNothing was rewritten. Run tools/lint.py to see what the archive "
          "already violates, and fill the null fields in lesson.yml by hand.")
    return 0


def _lesson_stub(slug: str, missing: list[str]) -> str:
    date = slug[:10]
    day = slug[11:].replace("-", " ").title()
    return f"""# Lesson front matter for {day}.
#
# Imported mechanically from the archive. Every field below that could
# not be read out of the source files is null. Fill them in by hand.
# Do not let a model guess at them: these values are printed, and one of
# them (translation) is doctrinally load-bearing.

sunday: {slug}
date: {date}
liturgical_day: "{day}"
special_day: null

# draft | in_review | approved
# Only content marked approved and carrying a matching approval record
# will build. See tools/verify.py.
status: draft

unit: null
week_in_unit: null

gospel: null
# ESV from 2026-09-20 forward; NKJV for 2026-09-13 only.
# Enforced by standards/rules.yml -> translation_schedule.
translation: null

# Identical wording on all twelve pieces. Core Standards section 4.
title: null
theme: null
theme_line_active: false

catechism_link: null
lords_prayer_form: trespasses

hymn:
  title: null
  lsb: null
  author: null
  tune: null
  license: null
  copyright_holder: null
  season_range: null

art:
  source: null
  plate_title: null
  license: null

memory_verses:
  pre_k: null
  primary: null
  intermediate: null
  middle_school: null
  high_school: null

copyright:
  teacher_guide_notice: null
  student_facing_notice: null

attribution: >-
  These Sunday School Lessons are built especially for St. Paul Lutheran
  Church by Pastor Bryan Wolfmueller with Claude AI on the same Sunday
  Gospel Lesson.

gospel_text: null
law_and_gospel:
  law: null
  gospel: null

production_notes: []

needs_input:
  - "Every field above that is still null."
{chr(10).join(f'  - "Missing piece: {m}"' for m in missing)}
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sunday")
    ap.add_argument("--from", dest="src", required=True)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    src = Path(args.src).resolve()
    if not src.is_dir():
        print(f"No such directory: {src}", file=sys.stderr)
        return 2
    print(f"Importing {args.sunday} from {src}/\n")
    return import_sunday(args.sunday, src, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
