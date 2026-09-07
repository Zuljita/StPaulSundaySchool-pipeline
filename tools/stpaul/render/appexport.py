"""The Base44 app export.

Two files, both generated in the same pass as the printed pieces from the
same approved bytes:

  <sunday>-Lesson-Export.md   the schema locked in
                              04-Base44-Markdown-Export-Standard.md
  <sunday>.json               the same content as structured data, which
                              is easier for the app to import than
                              re-parsing Markdown

Both carry `source_sha256`. That field is the answer to "are the app and
the handouts in sync?": if the hash on the app's lesson matches the hash
in the printed piece's colophon, they came from the same approved text.
It is a comparison of two strings rather than a reading of two documents.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..model import Lesson, Piece
from .handoff import LEVEL_LABELS, PIECE_LABELS, piece_heading

# 04-Base44-Markdown-Export-Standard.md §3: body organized by level, in
# this fixed order.
LEVEL_ORDER = ["pre_k", "primary", "intermediate", "middle_school", "high_school"]

LEVEL_HEADINGS = {
    "pre_k": "Pre-K & Kindergarten",
    "primary": "Primary (Grades 1–2)",
    "intermediate": "Intermediate (Grades 3–5)",
    "middle_school": "Middle School",
    "high_school": "High School",
}


def _piece_payload(lesson: Lesson, piece: Piece) -> dict:
    return {
        "id": piece.id,
        "type": piece.type,
        "level": piece.level,
        "order": piece.order,
        "label": piece_heading(lesson, piece),
        "title": piece.title,
        "sections": [{"heading": s.heading, "body": s.body} for s in piece.sections],
    }


def render_json(lesson: Lesson, source_hash: str) -> dict:
    m = lesson.meta
    return {
        "schema": "stpaul-lesson/1",
        "source_sha256": source_hash,
        "sunday": lesson.slug,
        "date": str(m.get("date", "")),
        "liturgical_day": m.get("liturgical_day"),
        "special_day": m.get("special_day"),
        "unit": m.get("unit"),
        "week_in_unit": m.get("week_in_unit"),
        "gospel": m.get("gospel"),
        "translation": m.get("translation"),
        "theme": m.get("theme"),
        "title": m.get("title"),
        "catechism_link": m.get("catechism_link"),
        "lords_prayer_form": m.get("lords_prayer_form", "trespasses"),
        "hymn": m.get("hymn"),
        "art": m.get("art"),
        "memory_verses": m.get("memory_verses"),
        "copyright": m.get("copyright"),
        "attribution": m.get("attribution"),
        "gospel_text": m.get("gospel_text"),
        "law_and_gospel": m.get("law_and_gospel"),
        "pieces_count": len(lesson.pieces),
        "levels": [lv for lv in LEVEL_ORDER
                   if any(p.level == lv for p in lesson.pieces)],
        "pieces": [_piece_payload(lesson, p) for p in lesson.pieces],
    }


def _yaml_block(data: dict, indent: int = 0) -> list[str]:
    """Minimal YAML emitter, enough for the export front matter."""
    pad = " " * indent
    out = []
    for k, v in data.items():
        if v is None:
            out.append(f"{pad}{k}: null")
        elif isinstance(v, dict):
            out.append(f"{pad}{k}:")
            out.extend(_yaml_block(v, indent + 2))
        elif isinstance(v, list):
            out.append(f"{pad}{k}:")
            for item in v:
                out.append(f"{pad}  - {item}")
        elif isinstance(v, bool):
            out.append(f"{pad}{k}: {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            out.append(f"{pad}{k}: {v}")
        else:
            s = str(v).replace('"', '\\"')
            out.append(f'{pad}{k}: "{s}"')
    return out


def render_markdown(lesson: Lesson, source_hash: str) -> str:
    """The export in the shape 04-Base44-Markdown-Export-Standard.md locks."""
    m = lesson.meta
    front = {
        "date": str(m.get("date", "")),
        "liturgical_day": m.get("liturgical_day"),
        "special_day": m.get("special_day"),
        "unit": m.get("unit"),
        "week_in_unit": m.get("week_in_unit"),
        "gospel": m.get("gospel"),
        "translation": m.get("translation"),
        "theme": m.get("theme"),
        "catechism_link": m.get("catechism_link"),
        "lords_prayer_form": m.get("lords_prayer_form", "trespasses"),
        "hymn": m.get("hymn"),
        "art": m.get("art"),
        "memory_verses": m.get("memory_verses"),
        "levels": [lv for lv in LEVEL_ORDER if any(p.level == lv for p in lesson.pieces)],
        "pieces_count": len(lesson.pieces),
        "copyright": m.get("copyright"),
        "attribution": m.get("attribution"),
        "source_sha256": source_hash,
    }

    out = ["---"] + _yaml_block(front) + ["---", ""]

    day = m.get("liturgical_day", lesson.slug)
    out += [f"# {day} — {m.get('date_display', m.get('date'))}".replace("—", "·"),
            f"## {m.get('gospel','')} · {m.get('title','')}".rstrip(" ·"), ""]

    if m.get("gospel_text"):
        out += [f"### The Text ({m.get('translation','')})", "", m["gospel_text"], ""]

    lg = m.get("law_and_gospel") or {}
    if lg:
        out += ["### Law and Gospel in This Text", ""]
        if lg.get("law"):
            out += [f"**The Law.** {lg['law']}", ""]
        if lg.get("gospel"):
            out += [f"**The Gospel.** {lg['gospel']}", ""]

    # Levels first, in the standard's fixed order, then the two
    # all-ages pieces, then production notes.
    for level in LEVEL_ORDER:
        pieces = [p for p in lesson.pieces if p.level == level]
        if not pieces:
            continue
        out += ["---", "", f"## {LEVEL_HEADINGS[level]}", ""]
        for p in sorted(pieces, key=lambda p: p.order):
            out += [f"### {PIECE_LABELS.get(p.type, p.type)}", ""]
            for s in p.sections:
                out += [f"**{s.heading}.**", "", s.body, ""]

    for pid, heading in (("family-take-home", "Family Take-Home"),
                         ("nursery-notes", "Nursery (Birth–3)")):
        p = lesson.piece(pid)
        if not p:
            continue
        out += ["---", "", f"## {heading}", ""]
        for s in p.sections:
            out += [f"**{s.heading}.**", "", s.body, ""]

    notes = m.get("production_notes") or []
    out += ["---", "", "## Production Notes", ""]
    for n in notes:
        out.append(f"- {n}")
    out.append(f"- Generated from approved source `{source_hash}`.")
    out.append("")

    return "\n".join(out)


def write(lesson: Lesson, out_dir: Path, source_hash: str) -> list[Path]:
    d = out_dir / "app"
    d.mkdir(parents=True, exist_ok=True)

    j = d / f"{lesson.slug}.json"
    j.write_text(
        json.dumps(render_json(lesson, source_hash), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    day_slug = (lesson.meta.get("liturgical_day") or lesson.slug).replace(" ", "-")
    md = d / f"{lesson.meta.get('date')}-{day_slug}-Lesson-Export.md"
    md.write_text(render_markdown(lesson, source_hash), encoding="utf-8")

    return [j, md]
