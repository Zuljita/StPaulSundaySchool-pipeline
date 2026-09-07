"""Design constants, read out of 03-Design-and-Brand-Standard.md.

The palette changes at Trinity 17 and the change is explicitly not
retroactive, so which palette a piece uses is a function of its date.
Encoding that here means it is decided by the calendar rather than
remembered, which is the same reason the translation schedule lives in
rules.yml.

Sizes assume US Letter portrait with 0.75in margins (§5).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# 03-Design-and-Brand-Standard.md §2, "Note on Trinity 17 forward".
NEW_PALETTE_FROM = date(2026, 9, 27)


@dataclass(frozen=True)
class Palette:
    name: str
    navy: str        # primary: header bars, rules
    secondary: str   # subheads, theme line
    red: str         # reference numerals ONLY (§2, "discipline on the red")
    charcoal: str = "292B2C"
    black: str = "000000"
    white: str = "FFFFFF"


LEGACY = Palette(name="legacy (Rally Day / Trinity 16)",
                 navy="1E4E72", secondary="5780AB", red="C00000")
CURRENT = Palette(name="current (Trinity 17 forward)",
                  navy="002664", secondary="2B65B5", red="C41230")


def palette_for(d: date) -> Palette:
    return CURRENT if d >= NEW_PALETTE_FROM else LEGACY


# §1 Typefaces. Two families, never a third.
DISPLAY_FONT = "Montserrat"
TEXT_FONT = "Lora"

# §4 Type scale, in points.
TYPE = {
    "piece_title":  {"font": DISPLAY_FONT, "size": 18, "leading": 22, "bold": True},
    "theme_line":   {"font": DISPLAY_FONT, "size": 10, "leading": 14, "bold": True, "italic": True},
    "section_bar":  {"font": DISPLAY_FONT, "size": 11, "leading": 22, "bold": True, "caps": True},
    "subhead":      {"font": DISPLAY_FONT, "size": 10, "leading": 14, "bold": True},
    "body":         {"font": TEXT_FONT, "size": 11, "leading": 15},
    "scripture":    {"font": TEXT_FONT, "size": 10.5, "leading": 15, "indent": 0.25},
    "direction":    {"font": TEXT_FONT, "size": 10, "leading": 14, "italic": True},
    "credit":       {"font": TEXT_FONT, "size": 8, "leading": 10},
}

# §4, "Level 1 is the exception": Pre-K/K sets body at 13/18 minimum.
PREK_BODY = {"font": TEXT_FONT, "size": 13, "leading": 18}

PAGE = {
    "width_in": 8.5,
    "height_in": 11.0,
    "margin_in": 0.75,
}

# §3 The signature device.
BAR_HEIGHT_PT = 22
BAR_LETTERSPACING = 0.020  # +20/1000 em

# §6: no horizontal rules anywhere, including the ones Markdown makes
# from "---". They are stripped in conversion.
STRIP_HORIZONTAL_RULES = True


def body_style(level: str) -> dict:
    return dict(PREK_BODY) if level == "pre_k" else dict(TYPE["body"])
