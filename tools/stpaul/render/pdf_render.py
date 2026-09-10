"""PDF rendering, to the same brand standard as the DOCX.

Two properties matter more than fidelity here, because both are things
that went wrong before:

  * The text is real text. Trinity 15's PDFs were exported with type
    converted to outlines, so they contain no recoverable words at all
    and only OCR can read them back. Nothing this renderer produces has
    that problem.
  * The output is deterministic. The PDF is stamped with the source hash
    and a fixed document date, so building the same approved content
    twice produces the same bytes.
"""

from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, PageTemplate,
                                Paragraph, Spacer)

from ..model import Lesson, Piece
from . import brand
from .blocks import blocks
from .handoff import piece_heading

# Montserrat and Lora are not bundled with reportlab. Rather than ship
# font binaries, map to the closest core fonts and record that the PDF is
# a proof rather than the press-ready artifact. The DOCX carries the real
# font names for the design project.
FONT_MAP = {brand.DISPLAY_FONT: "Helvetica", brand.TEXT_FONT: "Times-Roman"}


def _font(name: str, bold=False, italic=False) -> str:
    base = FONT_MAP.get(name, "Helvetica")
    if base == "Helvetica":
        if bold and italic: return "Helvetica-BoldOblique"
        if bold: return "Helvetica-Bold"
        if italic: return "Helvetica-Oblique"
        return "Helvetica"
    if bold and italic: return "Times-BoldItalic"
    if bold: return "Times-Bold"
    if italic: return "Times-Italic"
    return "Times-Roman"


def _md_to_rl(text: str) -> str:
    """Convert the inline markers to reportlab's mini-HTML, escaping first."""
    text = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", text)
    return text


class SectionBar(Flowable):
    """§3: the reversed navy bar. Full column width, white caps, centered."""

    def __init__(self, text: str, width: float, palette: brand.Palette):
        super().__init__()
        self.text = text.upper()
        self.width = width
        self.palette = palette
        self.height = brand.BAR_HEIGHT_PT

    def draw(self):
        st = brand.TYPE["section_bar"]
        font = _font(st["font"], bold=True)
        tracking = brand.BAR_LETTERSPACING * st["size"]
        c = self.canv

        c.setFillColor(HexColor("#" + self.palette.navy))
        c.rect(0, 0, self.width, self.height, stroke=0, fill=1)

        # Letterspacing lives on the text object, not the canvas, so the
        # tracked width has to be measured rather than taken from
        # stringWidth alone.
        tw = c.stringWidth(self.text, font, st["size"])
        tw += tracking * max(0, len(self.text) - 1)

        t = c.beginText()
        t.setFont(font, st["size"])
        t.setCharSpace(tracking)
        t.setFillColor(HexColor("#" + self.palette.white))
        # Optically centered: nudged up off the true centre line.
        t.setTextOrigin((self.width - tw) / 2.0, (self.height - st["size"]) / 2.0 + 1.5)
        t.textOut(self.text)
        c.drawText(t)


def _styles(palette: brand.Palette, level: str) -> dict:
    body = brand.body_style(level)
    return {
        "body": ParagraphStyle(
            "body", fontName=_font(body["font"]), fontSize=body["size"],
            leading=body["leading"], textColor=HexColor("#" + palette.black),
            spaceAfter=6),
        "scripture": ParagraphStyle(
            "scripture", fontName=_font(brand.TYPE["scripture"]["font"]),
            fontSize=brand.TYPE["scripture"]["size"] if level != "pre_k" else brand.PREK_BODY["size"],
            leading=brand.TYPE["scripture"]["leading"],
            leftIndent=brand.TYPE["scripture"]["indent"] * inch,
            # §2: Scripture is always black.
            textColor=HexColor("#" + palette.black), spaceAfter=6),
        "subhead": ParagraphStyle(
            "subhead", fontName=_font(brand.TYPE["subhead"]["font"], bold=True),
            fontSize=brand.TYPE["subhead"]["size"], leading=brand.TYPE["subhead"]["leading"],
            textColor=HexColor("#" + palette.secondary), spaceBefore=6, spaceAfter=2),
        "theme": ParagraphStyle(
            "theme", fontName=_font(brand.TYPE["theme_line"]["font"], bold=True, italic=True),
            fontSize=brand.TYPE["theme_line"]["size"], leading=brand.TYPE["theme_line"]["leading"],
            textColor=HexColor("#" + palette.secondary), alignment=TA_CENTER,
            spaceBefore=2, spaceAfter=10),
        "bullet": ParagraphStyle(
            "bullet", fontName=_font(body["font"]), fontSize=body["size"],
            leading=body["leading"], leftIndent=14, bulletIndent=4,
            textColor=HexColor("#" + palette.black), spaceAfter=2),
        "credit": ParagraphStyle(
            "credit", fontName=_font(brand.TYPE["credit"]["font"]),
            fontSize=brand.TYPE["credit"]["size"], leading=brand.TYPE["credit"]["leading"],
            textColor=HexColor("#" + palette.navy), spaceBefore=12),
    }


def render(lesson: Lesson, piece: Piece, source_hash: str, out_path: Path) -> Path:
    palette = brand.palette_for(lesson.date)
    styles = _styles(palette, piece.level)
    margin = brand.PAGE["margin_in"] * inch
    frame_w = LETTER[0] - 2 * margin

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(out_path), pagesize=LETTER,
        # reportlab writes /CreationDate, /ModDate and a random document
        # ID by default, so two builds of identical approved content
        # produced two different PDFs. invariant fixes all three. Without
        # it the claim that a rebuild proves a handout came from the
        # approved bytes is not checkable on the printed artefact.
        invariant=1,
        leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=margin,
        title=f"{piece_heading(lesson, piece)} · {lesson.meta.get('liturgical_day','')}",
        author="St. Paul Lutheran Church, Austin",
        subject=f"source {source_hash}",
    )
    frame = Frame(margin, margin, frame_w, LETTER[1] - 2 * margin, id="body",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    label = f"{piece_heading(lesson, piece)} · {lesson.meta.get('date_display', lesson.meta.get('date'))}"

    def footer(canvas, _doc):
        """§7: label left, page number right, no rule above."""
        canvas.saveState()
        st = brand.TYPE["credit"]
        canvas.setFont(_font(st["font"]), st["size"])
        canvas.setFillColor(HexColor("#" + palette.navy))
        canvas.drawString(margin, margin * 0.55, label)
        canvas.drawRightString(LETTER[0] - margin, margin * 0.55, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=footer)])

    story: list = [SectionBar(piece.title or piece_heading(lesson, piece), frame_w, palette),
                   Spacer(1, 6)]

    theme = lesson.meta.get("theme")
    if theme and lesson.meta.get("theme_line_active", True):
        story.append(Paragraph(_md_to_rl(theme), styles["theme"]))

    for section in piece.sections:
        story += [Spacer(1, 4), SectionBar(section.heading, frame_w, palette), Spacer(1, 6)]
        for kind, text in blocks(section.body):
            if kind == "rule":
                continue  # §6
            if kind == "bullet":
                story.append(Paragraph(_md_to_rl(text), styles["bullet"], bulletText="•"))
            elif kind == "scripture":
                story.append(Paragraph(_md_to_rl(text), styles["scripture"]))
            elif kind == "subhead":
                story.append(Paragraph(_md_to_rl(text), styles["subhead"]))
            else:
                story.append(Paragraph(_md_to_rl(text), styles["body"]))

    story.append(Paragraph(f"Source {source_hash[:12]}", styles["credit"]))
    doc.build(story)
    return out_path
