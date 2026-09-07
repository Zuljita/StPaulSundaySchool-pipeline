"""Per-piece Markdown handoff, and the combined review document.

The handoff is the plainest possible rendering: the approved text, one
file per piece, with the shared front matter resolved in. It is what the
design project consumes, and what a human diffs when they want to see
what changed between two approved versions without opening Word.
"""

from __future__ import annotations

from pathlib import Path

from ..model import Lesson, Piece

PIECE_LABELS = {
    "family_take_home": "Family Take-Home",
    "nursery_notes": "Nursery Notes",
    "teacher_guide": "Teacher's Guide",
    "student_handout": "Student Handout",
    "craft_page": "Craft Page",
}

LEVEL_LABELS = {
    "all": "All Ages",
    "nursery": "Nursery",
    "pre_k": "Pre-K / K",
    "primary": "Primary 1–2",
    "intermediate": "Intermediate 3–5",
    "middle_school": "Middle School",
    "high_school": "High School",
}


def piece_heading(lesson: Lesson, piece: Piece) -> str:
    level = LEVEL_LABELS.get(piece.level, piece.level)
    label = PIECE_LABELS.get(piece.type, piece.type)
    if piece.level in ("all", "nursery"):
        return label
    return f"{level} · {label}"


def render_piece(lesson: Lesson, piece: Piece, source_hash: str) -> str:
    m = lesson.meta
    out = [
        "---",
        f"sunday: {lesson.slug}",
        f"date: {m.get('date')}",
        f"liturgical_day: {m.get('liturgical_day')!r}",
        f"piece: {piece.id}",
        f"piece_label: {piece_heading(lesson, piece)!r}",
        f"level: {piece.level}",
        f"translation: {m.get('translation')}",
        f"gospel: {m.get('gospel')!r}",
        f"theme: {m.get('theme')!r}",
        f"source_sha256: {source_hash}",
        "---",
        "",
        f"# {piece.title or piece_heading(lesson, piece)}",
        "",
    ]
    if m.get("theme"):
        out += [f"*{m['theme']}*", ""]
    out.append(piece.body)
    return "\n".join(out).rstrip() + "\n"


def render_combined(lesson: Lesson, source_hash: str) -> str:
    """All twelve pieces in manifest order, for printing and reading.

    This is the document a reviewer reads. It is generated from the same
    content the build renders, so a reviewer and a printed handout can
    never be looking at different words.
    """
    m = lesson.meta
    out = [
        f"# {m.get('liturgical_day', lesson.slug)} · {m.get('date')}",
        "",
        f"**{m.get('gospel', '')}** ({m.get('translation', '')})",
        "",
    ]
    if m.get("theme"):
        out += [f"*{m['theme']}*", ""]
    out += [
        f"Source hash `{source_hash}`",
        "",
        "This document is generated from the curriculum source. Do not edit it;",
        f"edit `content/{lesson.slug}/` and regenerate.",
        "",
    ]
    for piece in lesson.pieces:
        out += ["", f"## {piece_heading(lesson, piece)}", ""]
        body = piece.body
        # Demote the piece's own headings one level so the combined
        # document has a single coherent outline.
        body = "\n".join(
            ("#" + ln) if ln.startswith("##") else ln
            for ln in body.splitlines()
        )
        out.append(body)
    return "\n".join(out).rstrip() + "\n"


def write(lesson: Lesson, out_dir: Path, source_hash: str) -> list[Path]:
    d = out_dir / "handoff"
    d.mkdir(parents=True, exist_ok=True)
    written = []
    for piece in lesson.pieces:
        p = d / f"{piece.order:02d}-{piece.id}.md"
        p.write_text(render_piece(lesson, piece, source_hash), encoding="utf-8")
        written.append(p)
    combined = d / f"{lesson.slug}-combined.md"
    combined.write_text(render_combined(lesson, source_hash), encoding="utf-8")
    written.append(combined)
    return written
