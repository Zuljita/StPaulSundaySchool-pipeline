"""Printed sheets, to the design system in `design_standards/`.

This replaces the DOCX and PDF renderers, which were built to
`03-Design-and-Brand-Standard.md`. That document was retired by Core
Standards §5 on September 7: "Design, typography, and layout live in the
design project, in its CLAUDE.md: palette, type scale, header and chip
anatomy, page counts, column structure, print settings, and the fit-check
procedure. None of it is restated here or in Drive. If a design fact is
needed, it is read from there, not remembered."

The old renderers remembered. They carried a two-family type system, a
palette, and a page geometry as Python constants, and by the time the
design project shipped, every one of those constants was wrong: the wrong
navy, two faces instead of three, a full-width navy bar where the system
has a rail, and — because Montserrat and Lora were never bundled — a PDF
set in Helvetica and Times.

So this module reads. `design_standards/tokens/*.css` is loaded off disk
and carried into the sheet unchanged, which makes §5 mechanically true
rather than a thing a renderer is trusted to honour. Change a token in
the design system and the next build prints it. There is no second copy
of the palette here, and there must not be one.

What this module owns is assembly: which approved section goes in the
rail and which in the substance column, on which of the sheet's fixed
pages. That is structure, not design, and it follows `design_standards/
CLAUDE.md`, "Structure per skeleton", which names the blocks page by
page. The one-line table in `ui_kits/handouts/README.md` summarises the
same thing and is not the same thing; building from it put three blocks
of the teacher's guide on the wrong page.

Three rules hold it honest.

  * Nothing is dropped. A section this module does not recognise flows
    into the substance column in document order rather than vanishing.
    Twelve pieces once went to print and five never reached the app;
    silence is the failure mode that costs the most to find.
  * Nothing is invented. An empty slot renders as an absent block, never
    as placeholder prose. `lesson.yml` leaves unknown fields null on
    purpose and this module keeps them null.
  * Nothing is measured. The page box is fixed and clips rather than
    reflows, and Python cannot know how tall a paragraph sets. Fit is
    checked in a browser by `tools/fit_check.py`, which fails the build
    on an overflowing page instead of letting a sheet lose its footer
    quietly.
"""

from __future__ import annotations

import html
import re
import shutil
from pathlib import Path

from ..model import REPO_ROOT, Lesson, Piece, Section, _normalize_heading
from ..scripture import (VERSE_MARK, is_excerpt, parse_exact_reference,
                         words)
from .blocks import blocks
from .handoff import piece_heading

DESIGN_ROOT = REPO_ROOT / "design_standards"
TOKEN_DIR = DESIGN_ROOT / "tokens"
FONT_DIR = DESIGN_ROOT / "assets" / "fonts"
LOGO = DESIGN_ROOT / "assets" / "stpaul-logo.png"

# Written once per build and linked by every sheet, rather than inlined
# into each of twelve files. The whole output directory is zipped by
# package.py, so a volunteer still gets one thing to open.
ASSET_DIR = "_assets"
STYLESHEET_NAME = "sheet.css"

# The only colour this module names. It is the desk a sheet sits on in a
# browser, never printed and not part of the palette, and it is the value
# design_standards/ui_kits/handouts/index.html uses for the same job.
# Every other colour on a sheet comes from the tokens, and a test holds
# this module to that: a palette remembered here is a palette that drifts.
SCREEN_BACKDROP = "#e8e6e0"

# design_standards/CLAUDE.md, "The 12 pieces": the chip is the piece's
# identity, and Nursery carries its age range where the others carry a
# level. Built from the labels handoff.py already defines so the two
# cannot drift.
NURSERY_CHIP = "Nursery Notes · Birth–3"


# ---------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+?)\*(?!\*)")

# Underscores typed as a line to write an answer on.
_WRITE_RULE = re.compile(r"_{6,}")

# "1 · The gathering (5 min)" — the lesson steps carry their own number
# and duration, and the design system sets both in a minute column to the
# left of the step. Parsed rather than re-typed: the text is approved and
# the renderer may not restate it.
_STEP = re.compile(r"^\s*(?P<n>\d+)\s*[·.\-]\s*(?P<text>.*?)\s*"
                   r"(?:\((?P<minutes>\d+)\s*min\)\s*)?$")


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _inline(text: str) -> str:
    """Markdown's two inline markers, and nothing else.

    The approved text uses `**` and `*` and no other markup. Anything
    further would be this renderer deciding how a sentence should read.
    """
    out = _esc(text)
    out = _BOLD.sub(r"<strong>\1</strong>", out)
    out = _ITALIC.sub(r"<em>\1</em>", out)
    return out


def _paragraphs(body: str, *, cls: str = "") -> str:
    """A section body as flowing print blocks, sharing the one parser.

    `blocks()` is the single reading of a section body. Print and the app
    disagreeing about whether a line is a bullet is exactly the drift
    that module exists to prevent, so this renderer asks it rather than
    reading the Markdown itself.
    """
    attr = f' class="{cls}"' if cls else ""
    out: list[str] = []
    items: list[str] = []

    def flush() -> None:
        if items:
            out.append('<ul class="ticks">' + "".join(
                f'<li><span class="tick"></span><span>{i}</span></li>' for i in items
            ) + "</ul>")
            items.clear()

    for kind, text in blocks(body):
        if kind == "rule":
            continue
        if kind == "bullet":
            items.append(_inline(text))
            continue
        flush()
        if kind == "subhead":
            out.append(f'<h3 class="lbl">{_inline(text)}</h3>')
        elif kind == "scripture":
            out.append(f'<p class="quote">{_inline(text)}</p>')
        else:
            # A run of underscores is a line for a student to write on,
            # which the design system draws rather than types. Set as
            # typed underscores it is one unbreakable forty-character
            # word, and it pushed a handout 70px off the side of the
            # sheet. The rule is the same thing the text asks for, at the
            # column's width, and it can break.
            rules = len(_WRITE_RULE.findall(text))
            lead = _WRITE_RULE.sub("", text).strip()
            if lead:
                out.append(f"<p{attr}>{_inline(lead)}</p>")
            if rules:
                out.append(_lines(rules))
    flush()
    return "".join(out)


# ---------------------------------------------------------------------
# The stylesheet
#
# Tokens come off disk. What is added here is the part the design system
# describes as page geometry rather than as a component: the sheet, the
# rail grid, and the handful of print settings a browser needs before it
# will put ink where the design says.
# ---------------------------------------------------------------------

PRINT_CSS = """\
/* Assembled by tools/stpaul/render/sheet.py. The tokens above are
   design_standards/tokens/*.css, copied verbatim; everything below is
   page geometry and print behaviour. */

* { box-sizing: border-box; }

html, body { margin: 0; padding: 0; background: __SCREEN_BACKDROP__; }

@page { size: 8.5in 11in; margin: 0; }

/* Two fills exist in this system, the pale tint and the solid navy, and
   both are backgrounds. A browser drops backgrounds when it prints
   unless told otherwise, which would take the navy memory panel down to
   white type on white paper. */
* { -webkit-print-color-adjust: exact; print-color-adjust: exact; }

.page {
  width: var(--page-width);
  height: var(--page-height);
  background: var(--surface-page);
  font-family: var(--font-body);
  font-size: var(--size-body);
  line-height: var(--lh-body);
  color: var(--text-body);
  overflow: hidden;          /* the box clips, as the design system says */
  margin: 0 auto;
}

.inner {
  padding: var(--page-pad-top) var(--page-pad-side) var(--page-pad-foot);
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* design_standards/CLAUDE.md: teacher's guide page 3 tightens. */
.page.lesson .inner {
  padding: var(--lesson-pad-top) var(--page-pad-side) var(--lesson-pad-foot);
}

@media print {
  html, body { background: var(--surface-page); }
  .page { page-break-after: always; break-after: page; margin: 0; }
  .page:last-of-type { page-break-after: auto; break-after: auto; }
}

p, h1, h2, h3, ul, figure { margin: 0; }

/* The design system's own weight for a bolded lead phrase, and the only
   bold cut vendored. Left to the browser, <strong> asks for 700, which
   is not a weight this system has: it would be synthesised. */
strong { font-weight: var(--weight-strong); }

/* Every direct child of the flex column takes flex: none, or a squeezed
   multi-column block spills sideways off the sheet. */
.inner > * { flex: none; }

.stack { display: flex; flex-direction: column; gap: var(--stack-md); min-width: 0; }
.stack-lg { gap: var(--stack-lg); }
.stack-sm { gap: var(--stack-sm); }

.lbl {
  font-family: var(--font-label);
  font-size: var(--size-label);
  font-weight: var(--weight-label);
  letter-spacing: var(--track-label);
  text-transform: uppercase;
  color: var(--text-label);
  margin: 0 0 5px;
}
.lbl.sm { font-size: var(--size-meta); }
.lbl.on-solid { color: var(--on-solid-label); }
.lbl.law { color: var(--rule-law); }

.chip {
  display: inline-block;
  background: var(--surface-solid);
  color: var(--on-solid);
  padding: var(--chip-pad);
  font-family: var(--font-label);
  font-size: var(--size-chip);
  font-weight: var(--weight-chip);
  letter-spacing: var(--track-label);
  text-transform: uppercase;
}
.chip.sm { padding: var(--chip-pad-sm); font-size: var(--size-chip-sm); }

.masthead {
  display: grid;
  grid-template-columns: 1fr auto;
  align-items: end;
  gap: 24px;
  border-bottom: var(--rule-heavy) solid var(--border-masthead);
  padding-bottom: 9px;
  margin-bottom: 12px;
}
.wordmark {
  display: flex;
  align-items: flex-end;
  gap: 11px;
  margin-bottom: 8px;
}
.wordmark img { display: block; width: var(--logo-width); height: auto; }
.wordmark span {
  font-family: var(--font-label);
  font-size: 13px;
  font-weight: var(--weight-chip);
  letter-spacing: var(--track-wordmark);
  text-transform: uppercase;
  color: var(--text-display);
  padding-bottom: 1px;
}
.masthead h1 {
  font-family: var(--font-display);
  font-size: var(--size-h1);
  font-weight: 400;
  line-height: var(--lh-display);
  letter-spacing: -0.01em;
  color: var(--text-display);
}
.meta {
  text-align: right;
  font-family: var(--font-label);
  font-size: var(--size-meta);
  font-weight: var(--weight-label);
  line-height: var(--lh-meta);
  letter-spacing: var(--track-meta);
  text-transform: uppercase;
  color: var(--text-meta);
}

.running {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 20px;
  border-bottom: var(--rule-medium) solid var(--border-masthead);
  padding-bottom: 8px;
  margin-bottom: 12px;
}
.running .who { display: flex; align-items: center; gap: 10px; }
.running .who > span:first-child {
  font-family: var(--font-label);
  font-size: var(--size-chip-sm);
  font-weight: var(--weight-chip);
  letter-spacing: var(--track-wordmark);
  text-transform: uppercase;
  color: var(--text-display);
}
.running .meta { line-height: 1.4; }

.theme {
  font-family: var(--font-display);
  font-style: italic;
  font-size: var(--size-theme);
  line-height: var(--lh-theme);
  color: var(--text-label);
  margin-bottom: 12px;
}
.theme .question {
  color: var(--text-meta);
  font-style: normal;
  font-size: var(--size-body-sm);
  font-family: var(--font-body);
}

/* The rail and the substance. minmax(0, …) is load-bearing: a bare
   2.05fr lets a multi-column Gospel block overflow the sheet sideways. */
.frame {
  display: grid;
  grid-template-columns: var(--grid-rail);
  gap: var(--grid-gutter);
  flex: 1;
  min-height: 0;
}
/* The family take-home is the exception: no rail, flowing bands. */
.frame.one { grid-template-columns: 1fr; }

.rail {
  border-right: var(--rule-hair) solid var(--border-hairline);
  padding-right: var(--rail-pad);
  display: flex;
  flex-direction: column;
  gap: var(--stack-md);
  min-width: 0;
}
.rail p, .rail li { font-size: var(--size-scripture-sm); line-height: var(--lh-body); }
.rail > * { flex: none; }

.quote { font-size: var(--size-scripture); line-height: var(--lh-scripture); }

/* Last line of defence for the sheet's width. Nothing in the copy should
   be an unbreakable forty-character token, but a reference, a URL or a
   typed rule would be, and the cost of one is a column off the page. */
.stack p, .rail p, .bands p, .step p { overflow-wrap: break-word; }

.scripture {
  column-count: 2;
  column-gap: var(--grid-gutter);
  column-rule: var(--rule-hair) solid var(--border-hairline-soft);
  font-size: var(--size-scripture);
  line-height: var(--lh-scripture);
}
.scripture.one { column-count: 1; }
.scripture sup {
  font-family: var(--font-label);
  font-size: var(--size-verse-number);
  color: var(--verse-number);
  vertical-align: super;
  line-height: 0;
}

/* minmax(0, …) on every track, for the reason geometry.css records about
   the rail: a bare 1fr takes min-width: auto, so one long word or a
   multi-column child pushes the whole grid off the side of the sheet.
   Measured: a student handout ran 139px wide before this. */
.pair { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; }
.pair > div { padding-top: 7px; }
.pair .law { border-top: var(--rule-heavy) solid var(--rule-law); }
.pair .gospel { border-top: var(--rule-heavy) solid var(--rule-gospel); }
.pair p { font-size: var(--size-body-sm); line-height: var(--lh-scripture); }

.tint {
  background: var(--surface-tint);
  padding: var(--tint-pad);
  display: grid;
  gap: 5px;
}
.tint p { font-size: var(--size-scripture-sm); line-height: var(--lh-body-tight); }

.navy {
  background: var(--surface-solid);
  color: var(--on-solid);
  padding: var(--panel-pad);
}
.navy .verse {
  font-family: var(--font-display);
  font-size: var(--size-panel-verse);
  line-height: var(--lh-quote);
}
.navy .ref {
  margin-top: 4px;
  font-family: var(--font-label);
  font-size: var(--size-meta);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--on-solid-label);
}
.navy p { color: var(--on-solid); }

/* Prose that followed the verse in the same approved section. It is not
   part of the panel and does not take its fill. */
.after-panel { margin-top: var(--stack-sm); display: grid; gap: var(--stack-xs); }

.step {
  display: grid;
  grid-template-columns: var(--step-minute-col) minmax(0, 1fr);
  gap: var(--step-gutter);
  align-items: start;
  border-top: var(--rule-hair) solid var(--border-hairline-soft);
  padding-top: 6px;
}
.step .when {
  font-family: var(--font-label);
  font-size: var(--size-label);
  font-weight: var(--weight-label);
  letter-spacing: var(--track-meta);
  text-transform: uppercase;
  color: var(--text-label);
}
.step .what p { font-size: var(--size-body-lead); line-height: var(--lh-body-tight); }
.step .what > * + * { margin-top: 6px; }

/* The design system sets its checkbox and season marker in two Unicode
   characters, U+25A1 and U+25A0. Neither is in the Latin cuts of any of
   the three families, so both fall through to whatever symbol font the
   machine happens to have: a different square on the runner than on the
   designer's desk, or a missing-glyph box. Drawn here instead, at the
   same size and colour, so the sheet prints the same everywhere. */
.ticks { list-style: none; padding: 0; display: grid; gap: 4px; }
.ticks li {
  display: flex;
  gap: 8px;
  align-items: baseline;
  font-size: var(--size-body-sm);
  line-height: var(--lh-body-tight);
}
.tick {
  flex: none;
  width: 8px;
  height: 8px;
  border: 1px solid var(--checkbox);
  transform: translateY(-1px);
}
.season-mark {
  display: inline-block;
  width: 7px;
  height: 7px;
  background: currentColor;
}

.art { display: flex; flex-direction: column; gap: 4px; height: var(--artwork-height); }
.art .plate {
  width: 100%;
  flex: 1;
  min-height: 0;
  object-fit: cover;
  object-position: 50% 22%;
  border: var(--rule-hair) solid var(--border-hairline);
  background: var(--surface-tint);
  display: block;
}
.art figcaption {
  font-family: var(--font-label);
  font-size: var(--size-art-credit);
  line-height: 1.4;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-meta);
}

.bands { display: grid; gap: var(--stack-lg); }
.bands.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.bands.three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.bands > * { min-width: 0; }

.lines { display: grid; gap: var(--writing-gap); }
.lines span {
  border-bottom: var(--rule-hair) solid var(--rule-writing);
  height: var(--writing-height);
}

footer.sheet {
  border-top: var(--rule-hair) solid var(--border-hairline);
  margin-top: auto;
  padding-top: 7px;
  display: grid;
  gap: 6px;
  font-family: var(--font-label);
  font-size: var(--size-meta);
  line-height: 1.5;
  letter-spacing: 0.06em;
  color: var(--text-meta);
}
footer.sheet .line { display: flex; justify-content: space-between; gap: 16px; text-transform: uppercase; }
footer.sheet .credit { font-size: var(--size-credit); letter-spacing: var(--track-credit); }

/* A proof is watermarked so it cannot be mistaken for a releasable
   sheet. Nothing else on the page is red at this size. */
.draft-mark {
  position: absolute;
  top: 0;
  right: 0;
  background: var(--red);
  color: var(--on-solid);
  font-family: var(--font-label);
  font-size: var(--size-chip-sm);
  font-weight: var(--weight-chip);
  letter-spacing: var(--track-label);
  text-transform: uppercase;
  padding: var(--chip-pad-sm);
}
.page { position: relative; }
"""


def stylesheet() -> str:
    """The design system's tokens, then this renderer's page geometry.

    Read in the order `design_standards/styles.css` imports them, so a
    sheet cascades the way the design project's own pages do. fonts.css
    is rewritten to point one directory up at `assets/fonts/`; the sheets
    sit one directory up from their own font copies too, so the same
    relative paths resolve.
    """
    parts = []
    for name in ("fonts.css", "colors.css", "typography.css", "geometry.css"):
        parts.append(f"/* --- design_standards/tokens/{name} --- */")
        parts.append((TOKEN_DIR / name).read_text(encoding="utf-8").strip())
    # A token rather than %-formatting: the CSS is full of "100%".
    parts.append(PRINT_CSS.replace("__SCREEN_BACKDROP__", SCREEN_BACKDROP))
    return "\n\n".join(parts) + "\n"


def write_assets(out_dir: Path, lesson: Lesson | None = None) -> list[Path]:
    """Copy the stylesheet, the faces, the mark and the week's plate.

    Everything a sheet needs sits beside it, so the built directory
    prints on a machine with no network and no fonts installed. That is
    the whole reason the faces were vendored.
    """
    assets = out_dir / ASSET_DIR
    (assets / "assets" / "fonts").mkdir(parents=True, exist_ok=True)
    (assets / "tokens").mkdir(parents=True, exist_ok=True)
    written = []

    # The stylesheet sits under tokens/ and the faces under assets/fonts/,
    # mirroring design_standards/ exactly. That is not tidiness: fonts.css
    # carries `url('../assets/fonts/…')`, and those bytes are copied
    # unchanged, so the only layout in which they resolve is the one they
    # were written for. Flattening this puts the sheets back in Georgia
    # and Segoe UI without a word of warning from the browser.
    css = assets / "tokens" / STYLESHEET_NAME
    css.write_text(stylesheet(), encoding="utf-8", newline="\n")
    written.append(css)

    for face in sorted(FONT_DIR.glob("*.woff2")):
        target = assets / "assets" / "fonts" / face.name
        shutil.copyfile(face, target)
        written.append(target)

    if LOGO.exists():
        target = assets / "assets" / LOGO.name
        shutil.copyfile(LOGO, target)
        written.append(target)

    if lesson is not None:
        plate = _plate_file(lesson)
        if plate is not None:
            (assets / "art").mkdir(parents=True, exist_ok=True)
            target = assets / "art" / plate.name
            shutil.copyfile(plate, target)
            written.append(target)
    return written


# ---------------------------------------------------------------------
# Components
#
# One function per component in design_standards/components/, same names,
# same markup. They take strings that are already escaped.
# ---------------------------------------------------------------------

def _chip(text: str, *, small: bool = False) -> str:
    cls = "chip sm" if small else "chip"
    return f'<span class="{cls}">{text}</span>'


def _section_label(text: str, *, tone: str = "blue", small: bool = False) -> str:
    cls = "lbl"
    if small:
        cls += " sm"
    if tone == "onSolid":
        cls += " on-solid"
    elif tone == "law":
        cls += " law"
    return f'<h2 class="{cls}">{text}</h2>'


def _masthead(*, chip: str, title: str, date: str, occasion: str,
              reference: str, season: str, season_var: str | None) -> str:
    mark = ""
    if season and season_var:
        mark = (f'<span class="season-mark" style="color: var({season_var});"></span> '
                f'{season}')
    lines = "<br>".join(x for x in (date, occasion, reference) if x)
    if mark:
        lines = f"{lines}<br>{mark}" if lines else mark
    # design_standards/readme.md: "Never draw, reconstruct, or approximate
    # the church's mark. If the file is unavailable, set the church name in
    # plain type."
    img = (f'<img src="{ASSET_DIR}/assets/{LOGO.name}" alt="St. Paul Lutheran Church">'
           if LOGO.exists() else '')
    return (
        '<header class="masthead"><div>'
        f'<div class="wordmark">{img}<span>Sunday School</span></div>'
        f'<div style="margin-bottom: 8px;">{_chip(chip)}</div>'
        f"<h1>{title}</h1>"
        "</div>"
        f'<p class="meta">{lines}</p>'
        "</header>"
    )


def _running_header(chip: str, right: str) -> str:
    return (
        '<header class="running">'
        f'<div class="who"><span>St. Paul Sunday School</span>{_chip(chip, small=True)}</div>'
        f'<p class="meta">{right}</p>'
        "</header>"
    )


def _theme_line(theme: str, level_question: str = "") -> str:
    if not theme:
        return ""
    q = f' <span class="question">{level_question}</span>' if level_question else ""
    return f'<p class="theme">{theme}{q}</p>'


def _tint(items: list[tuple[str, str]]) -> str:
    if not items:
        return ""
    inner = "".join(
        f'<div>{_section_label(label, small=True)}{body}</div>'
        for label, body in items if body
    )
    return f'<div class="tint">{inner}</div>' if inner else ""


def _navy(label: str, verse: str, ref: str = "") -> str:
    if not verse:
        return ""
    tail = f'<p class="ref">{ref}</p>' if ref else ""
    return (f'<div class="navy">{_section_label(label, tone="onSolid")}'
            f'<p class="verse">{verse}</p>{tail}</div>')


def _pair(law: str, gospel: str) -> str:
    if not (law or gospel):
        return ""
    return (
        '<div class="pair">'
        f'<div class="law">{_section_label("The Law", tone="law", small=True)}<p>{law}</p></div>'
        f'<div class="gospel">{_section_label("The Gospel", small=True)}<p>{gospel}</p></div>'
        "</div>"
    )


def _artwork(src: str | None, credit: str) -> str:
    """The panel stands whether or not the plate is there.

    design_standards/readme.md: "an absent image leaves the panel empty."
    A drawn substitute is not an option and neither is dropping the
    panel, which would reflow the rail and change where the footer sits.
    """
    plate = (f'<img class="plate" src="{src}" alt="{credit}">' if src
             else '<div class="plate"></div>')
    cap = f"<figcaption>{credit}</figcaption>" if credit else ""
    return f'<figure class="art">{plate}{cap}</figure>'


def _scripture(text: str, *, columns: int = 2) -> str:
    """Verse-numbered Gospel, set in the publisher's own words.

    Verse numbers come marked in the approved text the way the publisher
    sends them, and `scripture.VERSE_MARK` is the one reading of that
    mark. They are set in the label face and the one red the system
    allows for them; nothing else here touches the text. The Voice Guide
    does not read a verse, and neither does this.
    """
    if not text:
        return ""
    marked = VERSE_MARK.sub(r"<sup>\1</sup>", _esc(text))
    cls = "scripture" if columns == 2 else "scripture one"
    return f'<div class="{cls}"><p>{marked}</p></div>'


def _lines(count: int) -> str:
    return '<div class="lines">' + "<span></span>" * count + "</div>"


def _footer(left: str, right: str, credit: list[str] | None = None) -> str:
    """design_standards/CLAUDE.md, "Footers".

    "Montserrat 9px uppercase, hairline rule above, pinned to the foot of
    the sheet: piece and date left, 'Page n of m' right. The ESV /
    hymn-license / authorship credit line appears once per document, in
    8.5px sentence case under the running line."

    Once per document is why the credit is passed in rather than built
    here: only the last page gets it.
    """
    tail = "".join(f'<p class="credit">{c}</p>' for c in (credit or []) if c)
    return (f'<footer class="sheet"><div class="line"><span>{left}</span>'
            f"<span>{right}</span></div>{tail}</footer>")


# ---------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------

def _page(inner: str, *, lesson_padding: bool = False, draft: bool = False) -> str:
    cls = "page lesson" if lesson_padding else "page"
    mark = '<span class="draft-mark">Draft · do not distribute</span>' if draft else ""
    return f'<section class="{cls}">{mark}<div class="inner">{inner}</div></section>'


def _paginate(parts: list[tuple[str, bool]], *, chip: str, date: str,
              credit: list[str], draft: bool) -> list[str]:
    """Stamp the footers, once the page count is known.

    A skeleton cannot write its own footers: "Page n of m" needs the
    total, and the credit line goes on the last page only. So a skeleton
    returns page bodies and this puts the feet on them.
    """
    total = len(parts)
    left = " · ".join(x for x in (chip, date) if x)
    out = []
    for i, (body, lesson_padding) in enumerate(parts, 1):
        foot = _footer(left, f"Page {i} of {total}",
                       credit if i == total else None)
        out.append(_page(body + foot, lesson_padding=lesson_padding, draft=draft))
    return out


def _credits(lesson: Lesson, piece: Piece, section: Section | None) -> list[str]:
    """The credit line, in the footer where the design system puts it.

    It was a body block, which is why a teacher's guide spent a fifth of
    a page on copyright notices set at reading size. The design gives it
    8.5px sentence case under the running line, once per document, and
    `SheetFooter` has had a slot for it all along.

    Both sources print when both exist. `lesson.yml`'s notice is the
    publisher's, per audience; the piece's Credits section is what the
    pastor approved on that sheet, and today it is the only one filled in.
    Preferring one would drop the other, and neither is this renderer's
    to drop. The heading is not printed: the design names no label for
    this line, and "Credits" is a handle in the source rather than
    something a reader needs.
    """
    out = []
    notice = _notice(lesson, piece)
    if notice:
        out.append(notice)
    if section is not None:
        for kind, block in blocks(section.body):
            if kind != "rule":
                out.append(_inline(block))
    return out


class Pool:
    """The piece's sections, handed out once each.

    A skeleton asks for the sections it knows how to place. Whatever is
    left over is not discarded: `rest()` returns it in document order and
    the skeleton flows it into the substance column. A piece that grows a
    new section prints it in a plain but correct place, rather than
    disappearing between two builds and being noticed at a print shop.
    """

    def __init__(self, piece: Piece) -> None:
        self._sections = list(piece.sections)
        self._taken: set[int] = set()

    def take(self, *names: str) -> Section | None:
        wanted = {_normalize_heading(n) for n in names}
        for i, s in enumerate(self._sections):
            if i in self._taken:
                continue
            if _normalize_heading(s.heading) in wanted:
                self._taken.add(i)
                return s
        return None

    def take_prefix(self, prefix: str) -> Section | None:
        """For a heading that carries a reference in it.

        "This Week's Hymn · LSB 578" names the hymn in the heading, so it
        cannot be matched whole; the stem is stable and the number is
        not.
        """
        want = _normalize_heading(prefix)
        for i, s in enumerate(self._sections):
            if i in self._taken:
                continue
            if _normalize_heading(s.heading).startswith(want):
                self._taken.add(i)
                return s
        return None

    def rest(self) -> list[Section]:
        out = [s for i, s in enumerate(self._sections) if i not in self._taken]
        self._taken |= set(range(len(self._sections)))
        return out


def _block(section: Section | None, *, cls: str = "") -> str:
    if section is None:
        return ""
    return (f"<div>{_section_label(_esc(section.heading))}"
            f"{_paragraphs(section.body, cls=cls)}</div>")


def _flow(sections: list[Section]) -> str:
    return "".join(_block(s) for s in sections)


def _steps(section: Section | None) -> str:
    """`The Lesson`, set as the design system's numbered steps.

    Each `###` subhead is one step and carries its own number and
    minutes. A subhead that does not parse that way is still a step; it
    just has no minute column, which is better than refusing to print it.
    """
    if section is None:
        return ""

    lead: list[str] = []
    steps: list[dict] = []
    for kind, text in blocks(section.body):
        if kind == "rule":
            continue
        if kind == "subhead":
            m = _STEP.match(text)
            if m:
                minutes = m.group("minutes")
                when = f'{m.group("n")} · {minutes} min' if minutes else m.group("n")
                steps.append({"when": when, "head": _inline(m.group("text")), "body": []})
            else:
                steps.append({"when": "", "head": _inline(text), "body": []})
            continue
        para = f"<p>{_inline(text)}</p>"
        (steps[-1]["body"] if steps else lead).append(para)

    if not (lead or steps):
        return ""

    rendered = "".join(
        f'<div class="step"><p class="when">{_esc(s["when"])}</p>'
        f'<div class="what"><p>{s["head"]}</p>{"".join(s["body"])}</div></div>'
        for s in steps
    )
    heading = _section_label(_esc(section.heading))
    return f'<div class="stack stack-sm">{heading}{"".join(lead)}{rendered}</div>'


# ---------------------------------------------------------------------
# Shared front matter
# ---------------------------------------------------------------------

# rules.yml, locked_strings.attribution: the same split decides which
# copyright notice a sheet carries. Named here rather than inferred,
# because a piece landing on the wrong side of it prints the wrong
# publisher's notice.
TEACHER_FACING = ("teacher_guide", "nursery_notes", "family_take_home")

# design_standards/tokens/colors.css carries five season tokens. Which
# season a Sunday falls in is a liturgical fact, not a design one, so
# only the seasons the day names outright are inferred here; anything
# else leaves the marker off rather than colouring the church year by
# guess.
SEASONS = {
    "trinity": ("Trinity", "--season-trinity"),
    "advent": ("Advent", "--season-violet"),
    "lent": ("Lent", "--season-violet"),
    "easter": ("Easter", "--season-gold"),
    "epiphany": ("Epiphany", "--season-blue"),
    "pentecost": ("Pentecost", "--season-red"),
    "christmas": ("Christmas", "--season-gold"),
}


def _season(lesson: Lesson) -> tuple[str, str | None]:
    explicit = lesson.meta.get("season")
    if explicit:
        name, var = SEASONS.get(str(explicit).strip().lower(), (str(explicit), None))
        return _esc(name), var
    day = str(lesson.meta.get("liturgical_day") or "").strip().lower()
    for key, (name, var) in SEASONS.items():
        if day.startswith(key):
            return _esc(name), var
    return "", None


def _meta(lesson: Lesson) -> tuple[str, str, str]:
    m = lesson.meta
    date = _esc(str(m.get("date_display") or m.get("date") or ""))
    occasion = _esc(str(m.get("liturgical_day") or ""))
    reference = _esc(str(m.get("gospel") or ""))
    return date, occasion, reference


def _title(lesson: Lesson, piece: Piece) -> str:
    """The week's Title, carried identically on all twelve pieces.

    Core Standards section 4 locks it across the set. Until it is filled
    the piece's own h1 stands in: it is approved text, where a
    placeholder would not be.
    """
    return _esc(str(lesson.meta.get("title") or piece.title or ""))


def _chip_text(lesson: Lesson, piece: Piece) -> str:
    if piece.type == "nursery_notes":
        return _esc(NURSERY_CHIP)
    return _esc(piece_heading(lesson, piece))


def _theme(lesson: Lesson) -> str:
    if not lesson.meta.get("theme_line_active", True):
        return ""
    return _inline(str(lesson.meta.get("theme") or ""))


def _notice(lesson: Lesson, piece: Piece) -> str:
    """The publisher's notice for this sheet's audience.

    A dict is the current shape; a bare string is what older lesson.yml
    files carry. Both are read rather than one being converted, so an
    approved Sunday does not have to be touched in order to print.
    """
    c = lesson.meta.get("copyright")
    if isinstance(c, str):
        return _inline(c)
    if isinstance(c, dict):
        key = ("teacher_guide_notice" if piece.type in TEACHER_FACING
               else "student_facing_notice")
        value = c.get(key)
        return _inline(str(value)) if value else ""
    return ""


def _memory_verse(lesson: Lesson, piece: Piece) -> str:
    verses = lesson.meta.get("memory_verses")
    if not isinstance(verses, dict):
        return ""
    value = verses.get(piece.level)
    return _inline(str(value)) if value else ""


def _hymn(lesson: Lesson) -> str:
    h = lesson.meta.get("hymn")
    if not isinstance(h, dict):
        return _esc(str(h)) if h else ""
    parts = [str(h["title"])] if h.get("title") else []
    if h.get("lsb"):
        parts.append(f"LSB {h['lsb']}")
    return _esc(" · ".join(parts))


def _plate_file(lesson: Lesson) -> Path | None:
    """The week's painting on disk, when `art.source` names one.

    `art.source` may be a filename beside the week's content or a prose
    credit ("Schnorr von Carolsfeld, plate 42"). Only the first is a
    plate to print; the second is read as a credit and nothing more.
    """
    a = lesson.meta.get("art")
    if not isinstance(a, dict) or not a.get("source"):
        return None
    candidate = lesson.dir / str(a["source"])
    return candidate if candidate.is_file() else None


def _art(lesson: Lesson) -> tuple[str | None, str]:
    """The week's plate, and the line credited beneath it.

    When the file is not there the panel still prints, empty: the design
    system forbids a drawn substitute, and dropping the panel would
    reflow the rail and move the footer.
    """
    a = lesson.meta.get("art")
    if not isinstance(a, dict):
        return None, ""
    credit = _esc(" · ".join(str(a[k]) for k in ("plate_title", "source")
                                 if a.get(k)))
    plate = _plate_file(lesson)
    if plate is not None:
        return f"{ASSET_DIR}/art/{plate.name}", credit
    return None, credit


def _rail_artwork(lesson: Lesson) -> str:
    src, credit = _art(lesson)
    return _artwork(src, credit)


# "The Law:" or "The Law." opening a paragraph. The convention holds on
# every teacher's guide and on the nursery notes, and it is the only thing
# that tells the two halves apart without reading them.
_LAW_LEAD = re.compile(r"^\s*The\s+Law\s*[:.]\s*", re.I)
_GOSPEL_LEAD = re.compile(r"^\s*The\s+Gospel\s*[:.]\s*", re.I)


def _pair_from(lesson: Lesson, section: Section | None) -> str:
    """The Law and the Gospel, side by side under their two rules.

    The piece's own section is preferred over `lesson.yml`'s two fields:
    it is what the pastor approved for this level, and the fields carry
    the shared summary. The split is structural, on the lead phrase the
    text already uses, so nothing here decides where one half ends.

    Whatever else the section holds — "Supplied verbatim", a teacher's
    note — is set above the pair rather than dropped. An earlier draft of
    this function kept only the two halves, and the line telling a
    teacher not to improvise the section disappeared with it.
    """
    if section is not None:
        law = gospel = ""
        lead: list[str] = []
        for kind, text in blocks(section.body):
            if kind == "rule":
                continue
            if not law and _LAW_LEAD.match(text):
                law = _inline(_LAW_LEAD.sub("", text))
            elif not gospel and _GOSPEL_LEAD.match(text):
                gospel = _inline(_GOSPEL_LEAD.sub("", text))
            else:
                lead.append(f"<p>{_inline(text)}</p>")
        if law or gospel:
            return (f"<div>{_section_label(_esc(section.heading))}"
                    f'{"".join(lead)}{_pair(law, gospel)}</div>')
        return _block(section)

    lg = lesson.meta.get("law_and_gospel")
    if isinstance(lg, dict) and (lg.get("law") or lg.get("gospel")):
        return (f'<div>{_section_label("Law and Gospel in This Text")}'
                f'{_pair(_inline(str(lg.get("law") or "")), _inline(str(lg.get("gospel") or "")))}'
                "</div>")
    return ""


def _navy_from(section: Section | None, label: str, fallback_ref: str) -> str:
    """A section set as the one solid panel on the sheet.

    The first paragraph is the thing the room should leave with. A
    paragraph after it that is only a Scripture reference becomes the
    credit under it, read by the shared reference parser rather than by a
    guess about what a reference looks like. Everything further down the
    section is prose and prints under the panel, because it is approved
    text and this renderer does not choose what a family reads.
    """
    if section is None:
        return ""
    body = [(k, t) for k, t in blocks(section.body) if k != "rule"]
    if not body:
        return ""

    verse = _inline(body[0][1])
    rest = body[1:]
    ref = fallback_ref
    if rest:
        candidate = rest[0][1].strip()
        bare = re.sub(r"\s*\([^)]*\)\s*$", "", candidate)   # "Luke 7:13 (ESV)"
        if len(candidate) <= 60 and parse_exact_reference(bare):
            ref = _esc(candidate)
            rest = rest[1:]

    tail = "".join(f"<p>{_inline(t)}</p>" for _, t in rest)
    return _navy(label, verse, ref) + (f'<div class="after-panel">{tail}</div>' if tail else "")


def _frame(rail: str, substance: str) -> str:
    """The rail and the week's substance, or one column when there is no rail."""
    if not rail:
        return f'<div class="frame one"><div class="stack">{substance}</div></div>'
    return (f'<div class="frame"><aside class="rail">{rail}</aside>'
            f'<div class="stack">{substance}</div></div>')


# ---------------------------------------------------------------------
# The three skeletons
#
# ui_kits/handouts/README.md: "Any new piece is one of these." Levels
# differ by name, never by layout.
# ---------------------------------------------------------------------

# The catechism section. Core Standards §4 locks the heading to "From the
# Small Catechism" on every guide at every level, and rules.yml enforces
# it; the guides currently carry "Catechism Connection" and "Catechism /
# Confessions", which lint already reports. All three are matched here so
# the section reaches its slot either way. Renaming it is the author's
# fix, not this renderer's.
CATECHISM = ("From the Small Catechism", "Catechism Connection",
             "Catechism / Confessions")

# design_standards/CLAUDE.md: "What Children Ask (or Discussion Guardrails
# for middle and high school)". The middle school guide carries both, so
# both are taken and stacked rather than one being chosen over the other.
QUESTIONS = ("Discussion Guardrails", "What Children Ask")


def _teacher_guide(lesson: Lesson, piece: Piece, pool: Pool, *,
                   draft: bool) -> list[str]:
    """Three pages, laid out as design_standards/CLAUDE.md lays them out.

    "Structure per skeleton" is specific about which block sits on which
    page, and this follows it rather than the one-line summary in
    ui_kits/handouts/README.md, which is where an earlier version of this
    function came from. That version put Law and Gospel on page 2, pulled
    the Catechism forward to page 1, and set Memory Work in the rail;
    all three belong elsewhere.

    Two slots the spec names have no section in the content: "Time Today"
    and, on most levels, "This Week in the Room". They are left empty.
    The artwork panel is not here either: readme.md puts it "at the foot
    of the student rail", and this is not a student piece.
    """
    date, occasion, reference = _meta(lesson)
    season, season_var = _season(lesson)
    chip = _chip_text(lesson, piece)
    running = f"{occasion} · {date}".strip(" ·")

    needs = pool.take("What You Need")
    in_the_room = pool.take("This Week in the Room", "Lesson Overview")
    teacher = pool.take("For the Teacher")
    law_gospel = pool.take("Law and Gospel in this Text")
    memory = pool.take("Memory Work This Week", "Memory Work & Hymn",
                       "Memory Work")
    hymn = pool.take_prefix("Hymn")
    text = pool.take("The Text")
    questions = [s for s in (pool.take(q) for q in QUESTIONS) if s]
    catechism = pool.take(*CATECHISM)
    the_lesson = pool.take("The Lesson")
    prayer = pool.take("Closing Prayer")
    credits = pool.take("Credits")
    rest = pool.rest()

    # Page 1 — sidebar: what a teacher reaches for. Main column: the prep.
    rail = "".join([_block(needs), _reference_block(lesson), _block(in_the_room)])
    page1 = "".join([
        _masthead(chip=chip, title=_title(lesson, piece), date=date,
                  occasion=occasion, reference=reference,
                  season=season, season_var=season_var),
        _theme_line(_theme(lesson)),
        _frame(rail, "".join([_block(teacher), _pair_from(lesson, law_gospel),
                              _block(memory), _block(hymn)])),
    ])

    # Page 2 — the Gospel in full, then the questions beside the Catechism.
    gospel_block = _gospel_block(lesson, text)
    asked = "".join(_block(s) for s in questions)
    if asked and catechism:
        band = f'<div class="bands two"><div>{asked}</div>{_block(catechism)}</div>'
    else:
        band = asked + _block(catechism)
    body2 = gospel_block + band + _flow(rest)
    page2 = "".join([
        _running_header(chip, running),
        f'<div class="stack stack-lg">{body2}</div>',
    ]) if body2 else ""

    # Page 3 — The Lesson. The spec prints every prayer inline at the step
    # that uses it; the closing prayer is set here as its own block
    # instead, because moving approved text inside a step is a decision
    # about where a teacher reads it and the guides disagree already. The
    # primary guide's Closing Prayer reads "See Step 6 above", so on that
    # level it is a pointer; on high school it is the prayer itself.
    body3 = _steps(the_lesson) + _block(prayer)
    page3 = "".join([
        _running_header(chip, running),
        f'<div class="stack stack-lg">{body3}</div>',
    ]) if body3 else ""

    parts = [(page1, False)]
    if page2:
        parts.append((page2, False))
    if page3:
        parts.append((page3, True))
    return _paginate(parts, chip=chip, date=date, draft=draft,
                     credit=_credits(lesson, piece, credits))


# A block has to be this long before it can be mistaken for the passage.
# `is_excerpt` answers "are these the publisher's words, in order", and a
# short instruction can satisfy that by accident where a paragraph of the
# Gospel cannot.
_PASSAGE_MIN_WORDS = 20


def _gospel_block(lesson: Lesson, text: Section | None) -> str:
    """The Gospel in full, and whatever the section says around it.

    The piece's "The Text" section holds two different things: a line
    telling the teacher how to read it, and the passage. When
    `lesson.yml` carries the publisher's text, the passage is set with
    the design system's Scripture component, two columns with red verse
    numbers. The instruction is not the passage and still has to print;
    an earlier version of this kept the heading and threw the rest away.

    Which blocks are the passage is answered by `scripture.is_excerpt`,
    the same reading the rule engine uses to hold a quotation to the
    text, rather than by a guess made here.
    """
    passage = str(lesson.meta.get("gospel_text") or "")
    if not passage:
        return _block(text)

    heading = _esc(text.heading) if text else "The Holy Gospel"
    around = []
    if text is not None:
        for kind, block in blocks(text.body):
            if kind == "rule":
                continue
            if (len(words(block)) >= _PASSAGE_MIN_WORDS
                    and is_excerpt(block, passage)):
                continue          # the passage itself, set below
            around.append(f"<p>{_inline(block)}</p>")
    return (f"<div>{_section_label(heading)}{''.join(around)}"
            f"{_scripture(passage)}</div>")


def _reference_block(lesson: Lesson) -> str:
    """"The Text" as the sidebar carries it: the reference, not the passage.

    The passage itself is page 2, "the Gospel printed in full". The
    sidebar line is what a teacher looks up, and it comes from
    `lesson.yml` rather than from the piece, so the two cannot disagree.
    """
    ref = str(lesson.meta.get("gospel") or "").strip()
    if not ref:
        return ""
    translation = str(lesson.meta.get("translation") or "").strip()
    label = f"The Text ({translation})" if translation else "The Text"
    return f"<div>{_section_label(_esc(label))}<p>{_esc(ref)}</p></div>"


def _student_handout(lesson: Lesson, piece: Piece, pool: Pool, *,
                     draft: bool) -> list[str]:
    """One sheet: rail, the Gospel, the memory panel, then the activities."""
    date, occasion, reference = _meta(lesson)
    season, season_var = _season(lesson)
    chip = _chip_text(lesson, piece)

    catechism = pool.take("From the Small Catechism", "Catechism Connection")
    memory = pool.take("Memory Work")
    prayer = pool.take("Closing Prayer", "Pray this Together")
    credits = pool.take("Credits")
    activities = pool.rest()

    hymn = _hymn(lesson)
    rail = "".join([
        _tint([("Hymn", f"<p>{hymn}</p>")]) if hymn else "",
        _block(catechism),
        _block(prayer),
        _rail_artwork(lesson),
    ])

    gospel = _scripture(str(lesson.meta.get("gospel_text") or ""))
    panel = _navy_from(memory, "Memory Work", reference)
    if not panel:
        panel = _navy("Memory Work", _memory_verse(lesson, piece), reference)

    # The design system sets the activities as a two-up band. An odd one
    # out takes the full width rather than leaving a hole in the grid.
    cards = [_block(s) for s in activities]
    even = len(cards) - len(cards) % 2
    band = ""
    if cards[:even]:
        band += f'<div class="bands two">{"".join(cards[:even])}</div>'
    band += "".join(cards[even:])

    gospel_block = ""
    if gospel:
        label = "The Holy Gospel" + (f" · {reference}" if reference else "")
        gospel_block = f"<div>{_section_label(label)}{gospel}</div>"

    page = "".join([
        _masthead(chip=chip, title=_title(lesson, piece), date=date,
                  occasion=occasion, reference=reference,
                  season=season, season_var=season_var),
        _theme_line(_theme(lesson)),
        _frame(rail, f"{gospel_block}{panel}{band}"),
    ])
    return _paginate([(page, False)], chip=chip, date=date, draft=draft,
                     credit=_credits(lesson, piece, credits))


def _family_take_home(lesson: Lesson, piece: Piece, pool: Pool, *,
                      draft: bool) -> list[str]:
    """Two pages, no rail: flowing bands, as the design system has it."""
    date, occasion, reference = _meta(lesson)
    season, season_var = _season(lesson)
    chip = _chip_text(lesson, piece)
    running = f"{occasion} · {date}".strip(" ·")

    verse = pool.take("The Verse to Say this Week", "Memory Work")
    heard = pool.take("What They Heard")
    question = pool.take("One Question at Dinner")
    parents = pool.take("A Word for the Parents")
    catechism = pool.take("From the Small Catechism")
    prayer = pool.take("Pray this Together", "Closing Prayer")
    hymn = pool.take_prefix("This Week's Hymn")
    credits = pool.take("Credits")
    rest = pool.rest()

    panel = _navy_from(verse, _esc(verse.heading) if verse else "", reference)

    band = ""
    if question or parents:
        band = f'<div class="bands two">{_block(question)}{_block(parents)}</div>'
    page1 = "".join([
        _masthead(chip=chip, title=_title(lesson, piece), date=date,
                  occasion=occasion, reference=reference,
                  season=season, season_var=season_var),
        _theme_line(_theme(lesson)),
        f'<div class="stack stack-lg">{panel}{_block(heard)}{band}</div>',
    ])

    body2 = "".join([_block(catechism), _block(prayer), _block(hymn),
                     _flow(rest)])
    page2 = "".join([
        _running_header(chip, running),
        f'<div class="stack stack-lg">{body2}</div>',
    ]) if body2 else ""

    parts = [(page1, False)]
    if page2:
        parts.append((page2, False))
    return _paginate(parts, chip=chip, date=date, draft=draft,
                     credit=_credits(lesson, piece, credits))


def _nursery_notes(lesson: Lesson, piece: Piece, pool: Pool, *,
                   draft: bool) -> list[str]:
    """One sheet.

    The design project names three skeletons and does not say which one
    Nursery Notes takes; its own table gives the piece one page and a
    chip of its own. It is teacher-facing and has no Gospel column, so it
    takes the rail frame, with the prayer and the plate in the rail. That
    is an assembly decision made here, and the one place in this module
    where the design system does not settle the question. It is worth a
    look from the pastor.
    """
    date, occasion, reference = _meta(lesson)
    season, season_var = _season(lesson)
    chip = _chip_text(lesson, piece)

    prayer = pool.take("Closing Prayer")
    credits = pool.take("Credits")
    rest = pool.rest()

    rail = "".join([_block(prayer), _rail_artwork(lesson)])
    page = "".join([
        _masthead(chip=chip, title=_title(lesson, piece), date=date,
                  occasion=occasion, reference=reference,
                  season=season, season_var=season_var),
        _theme_line(_theme(lesson)),
        _frame(rail, _flow(rest)),
    ])
    return _paginate([(page, False)], chip=chip, date=date, draft=draft,
                     credit=_credits(lesson, piece, credits))


SKELETONS = {
    "teacher_guide": _teacher_guide,
    "student_handout": _student_handout,
    "craft_page": _student_handout,      # borrows the student skeleton
    "family_take_home": _family_take_home,
    "nursery_notes": _nursery_notes,
}


# ---------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------

DOC = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<meta name="source-sha256" content="{source_hash}">
<link rel="stylesheet" href="{assets}/tokens/{stylesheet}">
</head>
<body>
{pages}
</body>
</html>
"""


def filename(piece: Piece, *, draft: bool = False) -> str:
    return f"{piece.order:02d}-{piece.id}" + ("-DRAFT" if draft else "") + ".html"


def render(lesson: Lesson, piece: Piece, source_hash: str, out_path: Path,
           *, draft: bool = False) -> Path:
    """One piece, as the printed sheets the design system describes."""
    pool = Pool(piece)
    # An unknown piece type still prints. The student skeleton is the
    # plainest of the three, and a sheet set in the wrong frame is a
    # thing a reviewer can see; a piece that silently fails to build is
    # how five of twelve went missing.
    skeleton = SKELETONS.get(piece.type, _student_handout)
    pages = skeleton(lesson, piece, pool, draft=draft)

    title = f"{piece_heading(lesson, piece)} · {lesson.meta.get('liturgical_day') or ''}"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        DOC.format(title=_esc(title.strip(" ·")), source_hash=_esc(source_hash),
                   assets=ASSET_DIR, stylesheet=STYLESHEET_NAME,
                   pages="\n".join(pages)),
        encoding="utf-8", newline="\n")
    return out_path
