"""DOCX rendering, to 03-Design-and-Brand-Standard.md.

Implements the parts of the brand standard a generator can be held to:
the reversed navy header bar (§3), the type scale (§4), the Theme Line
(§4a), page setup (§5), no horizontal rules (§6), and the footer (§7).

Fonts are named, not embedded. Montserrat and Lora are free Google Fonts
and the standard says every volunteer can install them; a machine without
them will substitute, which changes how the file looks but not what it
says.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from ..model import Lesson, Piece
from . import brand, package
from .blocks import blocks
from .handoff import piece_heading

INLINE = re.compile(r"(\*\*.+?\*\*|\*.+?\*)")


def _rgb(hexstr: str) -> RGBColor:
    return RGBColor.from_string(hexstr)


def _shade(paragraph, hex_fill: str) -> None:
    """Fill a paragraph's background. This is the reversed bar (§3)."""
    pPr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    pPr.append(shd)


def _spacing(paragraph, *, before=0, after=0, line=None) -> None:
    pf = paragraph.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if line:
        pf.line_spacing = Pt(line)


def _letterspace(run, em: float, size_pt: float) -> None:
    """Track a run. Word measures spacing in twentieths of a point."""
    rPr = run._r.get_or_add_rPr()
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:val"), str(int(em * size_pt * 20)))
    rPr.append(spacing)


def _add_runs(paragraph, text: str, style: dict, color: str) -> None:
    """Write text, honouring **bold** and *italic* inline markers."""
    for part in INLINE.split(text):
        if not part:
            continue
        bold = style.get("bold", False)
        italic = style.get("italic", False)
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            part, bold = part[2:-2], True
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            part, italic = part[1:-1], True
        run = paragraph.add_run(part)
        run.font.name = style["font"]
        run.font.size = Pt(style["size"])
        run.font.bold = bold
        run.font.italic = italic
        run.font.color.rgb = _rgb(color)
        # East-Asian font name must be set too or Word substitutes.
        rPr = run._r.get_or_add_rPr()
        rFonts = rPr.find(qn("w:rFonts"))
        if rFonts is None:
            rFonts = OxmlElement("w:rFonts")
            rPr.append(rFonts)
        rFonts.set(qn("w:ascii"), style["font"])
        rFonts.set(qn("w:hAnsi"), style["font"])


def _section_bar(doc, text: str, palette: brand.Palette) -> None:
    """§3: full-width navy rectangle, white Montserrat SemiBold caps."""
    st = brand.TYPE["section_bar"]
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _spacing(p, before=10, after=6, line=st["leading"])
    _shade(p, palette.navy)
    run = p.add_run(text.upper())
    run.font.name = st["font"]
    run.font.size = Pt(st["size"])
    run.font.bold = True
    run.font.color.rgb = _rgb(palette.white)
    _letterspace(run, brand.BAR_LETTERSPACING, st["size"])


def _footer(doc, lesson: Lesson, piece: Piece) -> None:
    """§7: piece label and Sunday on the left, live page number on the right."""
    sec = doc.sections[0]
    para = sec.footer.paragraphs[0]
    para.text = ""
    palette = brand.palette_for(lesson.date)
    st = brand.TYPE["credit"]

    label = f"{piece_heading(lesson, piece)} · {lesson.meta.get('date_display', lesson.meta.get('date'))}"
    run = para.add_run(label)
    run.font.name = st["font"]
    run.font.size = Pt(st["size"])
    run.font.color.rgb = _rgb(palette.navy)

    para.add_run("\t")
    run = para.add_run("Page ")
    run.font.name = st["font"]
    run.font.size = Pt(st["size"])
    run.font.color.rgb = _rgb(palette.navy)

    # PAGE field, so the number renumbers itself rather than being baked in.
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    para._p.append(fld)


def render(lesson: Lesson, piece: Piece, source_hash: str, out_path: Path) -> Path:
    palette = brand.palette_for(lesson.date)
    body_style = brand.body_style(piece.level)
    doc = Document()

    sec = doc.sections[0]
    sec.page_width = Inches(brand.PAGE["width_in"])
    sec.page_height = Inches(brand.PAGE["height_in"])
    for side in ("top", "bottom", "left", "right"):
        setattr(sec, f"{side}_margin", Inches(brand.PAGE["margin_in"]))

    # Piece title, in a reversed bar (§3, §4).
    _section_bar(doc, piece.title or piece_heading(lesson, piece), palette)

    # Theme Line (§4a): identical on all twelve pieces, directly beneath
    # the bar, above everything else including "What You Need".
    theme = lesson.meta.get("theme")
    if theme and lesson.meta.get("theme_line_active", True):
        st = brand.TYPE["theme_line"]
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _spacing(p, before=2, after=10, line=st["leading"])
        _add_runs(p, theme, st, palette.secondary)

    for section in piece.sections:
        _section_bar(doc, section.heading, palette)
        for block in blocks(section.body):
            kind, text = block
            if kind == "rule":
                continue  # §6: no horizontal rules, ever.
            if kind == "bullet":
                p = doc.add_paragraph(style="List Bullet")
                _spacing(p, after=2, line=body_style["leading"])
                _add_runs(p, text, body_style, palette.black)
                continue
            if kind == "scripture":
                st = dict(brand.TYPE["scripture"])
                if piece.level == "pre_k":
                    st["size"] = brand.PREK_BODY["size"]
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Inches(brand.TYPE["scripture"]["indent"])
                _spacing(p, after=6, line=st["leading"])
                # §2: Scripture is always black, on every piece, at every level.
                _add_runs(p, text, st, palette.black)
                continue
            if kind == "subhead":
                p = doc.add_paragraph()
                _spacing(p, before=6, after=2, line=brand.TYPE["subhead"]["leading"])
                _add_runs(p, text, brand.TYPE["subhead"], palette.secondary)
                continue
            p = doc.add_paragraph()
            _spacing(p, after=6, line=body_style["leading"])
            _add_runs(p, text, body_style, palette.black)

    # Colophon: the source hash, so a printed page can be checked against
    # the app. Deliberately tiny, in the credits style (§4).
    st = brand.TYPE["credit"]
    p = doc.add_paragraph()
    _spacing(p, before=12, after=0, line=st["leading"])
    _add_runs(p, f"Source {source_hash[:12]}", st, palette.navy)

    _footer(doc, lesson, piece)

    # Word stamps a document with when it was written. Left alone, two
    # builds of the same approved bytes differ, which would make the one
    # property this pipeline rests on false for the file a teacher
    # actually prints. Dated from the lesson instead: deterministic,
    # derived from the content, and correct to a person reading the
    # file's properties.
    stamp = datetime(lesson.date.year, lesson.date.month, lesson.date.day)
    core = doc.core_properties
    core.created = stamp
    core.modified = stamp
    core.last_modified_by = "St. Paul Sunday School pipeline"
    core.revision = 1
    core.title = piece.title or piece_heading(lesson, piece)
    core.author = "St. Paul Lutheran Church, Austin"
    core.comments = f"source {source_hash}"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))

    # A .docx is a ZIP, and python-docx writes its entries through
    # `writestr`, which timestamps each one from the clock. The document
    # metadata above does not reach those.
    package.normalize(out_path, package.date_time_for(lesson.date))
    return out_path
