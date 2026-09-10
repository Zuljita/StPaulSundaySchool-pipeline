"""The public web site.

A fourth renderer, beside handoff, DOCX and PDF, run in the same pass
over the same parse of the same approved bytes. That is the whole point
of it existing here rather than somewhere else.

WHY THIS REPLACES AN EXPORT

The Base44 export is a file handed to another system that then re-derives
a reading of it. `fetch_app.py`, `drift.py` and `import_app.py` are all
instruments for measuring how far that second reading drifted from the
first, and the answer, once, was that 5 of 12 pieces never arrived and 0
of the 7 that did matched the print. `source_sha256` exists because
nothing else could answer "are these the same document?"

When the site is rendered here, the question stops being askable. There
is no second derivation to drift. A page carries the same hash as the
handout in the same colophon, because both came out of this one call.

DETERMINISM

No clock, no network, no model, no randomness. Two builds of the same
approved bytes produce byte-identical HTML. `build.py` records the build
time in BUILD-PROVENANCE.json, deliberately outside the rendered files,
and nothing here may put a timestamp in a page.

ESCAPING

Every string that comes out of `content/` is HTML-escaped, including the
ones that look like markup. Imported content has carried raw tags before
(`import_app.detag` exists for exactly that), and this site is public.
A literal `<sup>` showing through on a page is a loud bug somebody fixes;
unescaped curriculum text on a public origin is an injection vector. The
loud failure is the correct trade.
"""

from __future__ import annotations

import html
import json
from datetime import date
import re
from pathlib import Path

from ..model import Lesson, Piece
from .appexport import LEVEL_HEADINGS, LEVEL_ORDER
from .blocks import blocks
from .handoff import LEVEL_LABELS, PIECE_LABELS, piece_heading

# Inline emphasis, matched the same way docx_render matches it.
INLINE = re.compile(r"(\*\*.+?\*\*|\*.+?\*)")

# Where the printable handouts live once published. The site links to
# them; it does not carry them.
HANDOUT_ROOT = "/handouts"

# design_standards/CLAUDE.md, Palette. Navy is the launcher and browser
# chrome colour; paper is what a page is painted on before the CSS lands.
THEME_COLOR = "082858"
BACKGROUND_COLOR = "fffefb"

# The piece list's own id, and the key the catch-all group files under.
# Both are anchors a teacher may bookmark, so they are constants rather
# than strings written twice.
PIECES_ID = "pieces"
OTHER_LEVEL = "other"

APP_NAME = "St. Paul Sunday School"
APP_SHORT_NAME = "Sunday School"


# ---------------------------------------------------------------------
# The stylesheet
#
# Adapted from design_standards/tokens/. The palette and the three type
# families carry over unchanged; the geometry does not, because that
# system is measured for an 816x1056 page box that clips and this is a
# phone in a pew. One stylesheet, served once and cached, rather than a
# copy inlined into every page.
# ---------------------------------------------------------------------

STYLESHEET = """\
@import url("https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1\
&family=Montserrat:wght@400;500;600&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;\
0,8..60,600;1,8..60,400&display=swap");

:root {
  /* Both palettes are real, so say so: this is what paints the canvas
     before the CSS lands and what styles the scrollbars and any form
     control. Without it a dark reader gets a white flash and light
     scrollbars framing a dark page. */
  color-scheme: light dark;

  --navy: #082858;
  --blue: #2858b8;
  --blue-light: #88c8d8;
  --red: #a81818;
  --ink: #1c1c19;
  --ink-secondary: #3b3b36;
  --ink-muted: #5c5c54;
  --paper: #fffefb;
  --tint: #eef7fa;
  --hairline-soft: #cfe0ea;

  /* The draft banner is the one filled block in the stylesheet, so it
     needs a background and an ink of its own. --red cannot serve: it is
     an ink colour, picked to be legible *on* paper, and in dark mode it
     lightens to stay that way. White on the lightened red measured
     2.3:1, under the 4.5:1 floor, on the one banner whose whole job is
     to stop an unapproved proof being handed out. */
  --draft-bg: #a81818;
  --draft-ink: #ffffff;

  --font-display: "Instrument Serif", Georgia, serif;
  --font-body: "Source Serif 4", Georgia, serif;
  --font-label: "Montserrat", system-ui, sans-serif;

  --measure: 34rem;
  --track-label: 0.13em;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --navy: #b8d4f0;
    --blue: #8fb8f0;
    --blue-light: #4a7ba8;
    --red: #ff8a8a;
    --ink: #e8e6e0;
    --ink-secondary: #c4c2bb;
    --ink-muted: #9a978f;
    --paper: #14161a;
    --tint: #1c2129;
    --hairline-soft: #2b3542;

    /* Deep red rather than the lightened ink red: on a dark page a
       #ff8a8a bar is the brightest thing on the screen, and this is
       read on a phone in a pew. 7.9:1. */
    --draft-bg: #8c1414;
    --draft-ink: #ffe4e4;
  }
}

*, *::before, *::after { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--font-body);
  font-size: 1.0625rem;
  line-height: 1.6;
  -webkit-text-size-adjust: 100%;
}

.wrap { max-width: 46rem; margin: 0 auto; padding-block: 2rem 4rem; padding-inline: 1.25rem; }

a { color: var(--blue); text-decoration-thickness: 1px; text-underline-offset: 2px; }
a:hover { color: var(--navy); }

/* --- masthead ---------------------------------------------------- */

.masthead {
  border-bottom: 2px solid var(--navy);
  padding-bottom: 0.75rem;
  margin-bottom: 2rem;
}
.masthead .church {
  font-family: var(--font-label);
  font-size: 0.6875rem;
  font-weight: 500;
  letter-spacing: var(--track-label);
  text-transform: uppercase;
  color: var(--blue);
  margin: 0;
}
.masthead .church a { color: inherit; text-decoration: none; }
.masthead .church a:hover { text-decoration: underline; }

h1 {
  font-family: var(--font-display);
  font-weight: 400;
  font-size: clamp(2rem, 6vw, 2.75rem);
  line-height: 1.05;
  color: var(--navy);
  margin: 0.5rem 0 0.25rem;
}

.meta {
  font-family: var(--font-label);
  font-size: 0.6875rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-muted);
  margin: 0;
}
.meta span + span::before { content: " · "; }

.theme {
  font-family: var(--font-display);
  font-style: italic;
  font-size: 1.375rem;
  line-height: 1.25;
  color: var(--blue);
  margin: 1.25rem 0 0;
}

/* --- sections ---------------------------------------------------- */

h2.section {
  font-family: var(--font-label);
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: var(--track-label);
  text-transform: uppercase;
  color: var(--paper);
  background: var(--navy);
  padding: 0.4rem 0.7rem;
  margin: 2.5rem 0 1rem;
  border-radius: 2px;
}

h3.subhead {
  font-family: var(--font-label);
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--blue);
  margin: 1.5rem 0 0.35rem;
}

p { margin: 0 0 0.9rem; max-width: var(--measure); }

blockquote.scripture {
  margin: 1.25rem 0;
  padding: 0.15rem 0 0.15rem 1.1rem;
  border-left: 3px solid var(--blue-light);
  color: var(--ink);
  max-width: var(--measure);
}
blockquote.scripture p:last-child { margin-bottom: 0; }

ul { margin: 0 0 1rem; padding-left: 1.2rem; max-width: var(--measure); }
li { margin-bottom: 0.35rem; }

/* --- the Sunday page --------------------------------------------- */

.lawgospel { margin: 1.5rem 0; }
.lawgospel > div { padding-left: 1.1rem; margin-bottom: 1rem; max-width: var(--measure); }
.lawgospel .law { border-left: 3px solid var(--red); }
.lawgospel .gospel { border-left: 3px solid var(--blue); }
.lawgospel .label {
  font-family: var(--font-label);
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: var(--track-label);
  text-transform: uppercase;
  display: block;
  margin-bottom: 0.2rem;
}
.lawgospel .law .label { color: var(--red); }
.lawgospel .gospel .label { color: var(--blue); }

.level { margin-bottom: 2rem; }
.level > h3 {
  font-family: var(--font-label);
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: var(--track-label);
  text-transform: uppercase;
  color: var(--ink-muted);
  border-bottom: 1px solid var(--hairline-soft);
  padding-bottom: 0.35rem;
  margin: 0 0 0.75rem;
}

.pieces { list-style: none; margin: 0; padding: 0; max-width: none; }
.pieces li {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.4rem 0.9rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--hairline-soft);
}
.pieces .name { flex: 1 1 14rem; font-size: 1.0625rem; }
.pieces .dl {
  font-family: var(--font-label);
  font-size: 0.625rem;
  font-weight: 600;
  letter-spacing: var(--track-label);
  text-transform: uppercase;
}

.package {
  background: var(--tint);
  border-left: 3px solid var(--blue);
  padding: 0.7rem 0.9rem;
  margin: 0 0 1.5rem;
  max-width: none;
}
.package a {
  font-family: var(--font-label);
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: var(--track-label);
  text-transform: uppercase;
}
.package .note {
  display: block;
  font-size: 0.8125rem;
  color: var(--ink-muted);
  margin-top: 0.2rem;
}

/* --- grade filter ------------------------------------------------- */
/* Anchors and :target, never script. The site is allowed exactly one
   JavaScript file and it registers the service worker; a second one
   would cost either an inline script or another line in the no-script
   budget, and a link costs neither.
   A browser without :has() drops these two rules and shows every level,
   which is the page exactly as it stood before the filter existed. */

.levelfilter {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin: 1.25rem 0 1.5rem;
}
.chip {
  font-family: var(--font-label);
  font-size: 0.6875rem;
  font-weight: 500;
  letter-spacing: var(--track-label);
  text-transform: uppercase;
  text-decoration: none;
  white-space: nowrap;
  color: var(--blue);
  background: var(--paper);
  border: 1px solid var(--hairline-soft);
  border-radius: 999px;
  padding: 0.35rem 0.7rem;
}
.chip:hover, .chip:focus-visible {
  border-color: var(--blue);
  background: var(--tint);
}

/* Both of these are :has() rules, and the second one keeps the prefix on
   purpose. Dropping it reads like a tidy-up and is not: the hide scores
   (0,4,0) and a bare `.levels > .level:target` scores (0,3,0), so the
   hide wins and a filtered page renders with no pieces on it at all. */
.levels:has(> .level:target) > .level { display: none; }
.levels:has(> .level:target) > .level:target { display: block; }

/* --- the Sunday list --------------------------------------------- */

/* max-width: none, because the generic `ul` rule caps lists at the reading
   measure and these rows are full-width dividers, not prose. */
.sundays { list-style: none; margin: 0; padding: 0; max-width: none; }
.sundays li { padding: 1.1rem 0; border-bottom: 1px solid var(--hairline-soft); }
.sundays .day {
  font-family: var(--font-display);
  font-size: 1.625rem;
  line-height: 1.1;
  display: block;
  text-decoration: none;
  color: var(--navy);
}
.sundays .day:hover { text-decoration: underline; }
.sundays .theme { font-size: 1.0625rem; margin-top: 0.3rem; }

/* --- install ----------------------------------------------------- */
/* Hidden until the browser says the site can actually be installed,
   which is the only moment the offer means anything. With JavaScript
   off, or on iOS where no such event is ever fired, it never appears. */
.install {
  margin: 2rem 0 0;
  padding: 0.55rem 1.1rem;
  font-family: var(--font-label);
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: var(--track-label);
  text-transform: uppercase;
  color: var(--paper);
  background: var(--navy);
  border: 0;
  border-radius: 2px;
  cursor: pointer;
}
.install:hover, .install:focus-visible { background: var(--blue); }
.install[hidden] { display: none; }

/* --- footer ------------------------------------------------------ */

footer {
  margin-top: 3.5rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--hairline-soft);
  font-size: 0.8125rem;
  line-height: 1.55;
  color: var(--ink-muted);
}
footer p { max-width: var(--measure); margin-bottom: 0.6rem; }
footer .colophon {
  font-family: var(--font-label);
  font-size: 0.625rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  word-break: break-all;
}

.draft-banner {
  background: var(--draft-bg);
  color: var(--draft-ink);
  font-family: var(--font-label);
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: var(--track-label);
  text-transform: uppercase;
  text-align: center;
  padding: 0.6rem 1rem;
}

.backlink {
  font-family: var(--font-label);
  font-size: 0.6875rem;
  font-weight: 500;
  letter-spacing: var(--track-label);
  text-transform: uppercase;
  display: inline-block;
  margin-bottom: 1.5rem;
}
"""


def _chip_active_rules() -> str:
    """Which chip is lit, one selector per level.

    CSS cannot tell that a chip's href names the level that is targeted,
    so the pairing has to be spelled out. It is generated from
    LEVEL_ORDER rather than typed out, so a level added there gets a chip
    that lights up without anyone remembering this block exists. That is
    the same reason the piece list is built from LEVEL_ORDER too: a list
    of levels kept in two places is a list of levels that will disagree.

    Every selector in the group uses :has(), so a browser without it
    drops the whole group and the chips simply stay unlit. Nothing is
    hidden by that, because the rules that hide are :has() rules too.
    """
    selectors = ",\n".join(
        f'.wrap:has(#level-{key}:target) .chip[href="#level-{key}"]'
        for key in (*LEVEL_ORDER, OTHER_LEVEL))
    return (
        "\n" + selectors + " {\n"
        "  color: var(--paper);\n"
        "  background: var(--navy);\n"
        "  border-color: var(--navy);\n"
        "}\n"
    )


STYLESHEET += _chip_active_rules()


# ---------------------------------------------------------------------
# Text to HTML
# ---------------------------------------------------------------------

def _esc(text: str) -> str:
    return html.escape(str(text if text is not None else ""), quote=True)


def _inline(text: str) -> str:
    """Escape, then honour **bold** and *italic*, as docx_render does."""
    out = []
    for part in INLINE.split(text or ""):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append(f"<strong>{_esc(part[2:-2])}</strong>")
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out.append(f"<em>{_esc(part[1:-1])}</em>")
        else:
            out.append(_esc(part))
    return "".join(out)


def _paragraph(text: str) -> str:
    """One block's text, with soft wraps joined into flowing prose.

    A newline inside a paragraph of Markdown is a soft wrap, not a line
    break, and both print renderers already treat it that way: reportlab
    collapses it inside a Paragraph, and a newline inside a Word run is
    not a break either. Emitting <br> here instead would have laid the
    same approved paragraph out one way on paper and another way on a
    phone, which is the drift this renderer exists to make impossible.

    Joined before emphasis is applied, so a **span** that happens to
    straddle a wrap still renders as one.
    """
    joined = " ".join(line.strip() for line in (text or "").splitlines() if line.strip())
    return _inline(joined)


def _render_body(body: str) -> list[str]:
    """A section body as HTML, using the one shared block parser."""
    out: list[str] = []
    open_list = False
    open_quote = False

    def close() -> None:
        nonlocal open_list, open_quote
        if open_list:
            out.append("</ul>")
            open_list = False
        if open_quote:
            out.append("</blockquote>")
            open_quote = False

    for kind, text in blocks(body):
        if kind == "rule":
            continue                      # §6: no horizontal rules, ever.
        if kind == "bullet":
            if open_quote:
                close()
            if not open_list:
                out.append("<ul>")
                open_list = True
            out.append(f"<li>{_inline(text)}</li>")
            continue
        if kind == "scripture":
            if open_list:
                close()
            if not open_quote:
                out.append('<blockquote class="scripture">')
                open_quote = True
            out.append(f"<p>{_paragraph(text)}</p>")
            continue
        close()
        if kind == "subhead":
            out.append(f'<h3 class="subhead">{_inline(text)}</h3>')
        else:
            out.append(f"<p>{_paragraph(text)}</p>")

    close()
    return out


# ---------------------------------------------------------------------
# Page shell
# ---------------------------------------------------------------------

# The head every page carries. The service worker registration is an
# external file rather than an inline script so the Content-Security
# Policy can stay free of 'unsafe-inline'.
HEAD_LINKS = [
    '<link rel="stylesheet" href="/assets/site.css">',
    '<link rel="manifest" href="/manifest.webmanifest">',
    '<link rel="icon" href="/assets/favicon.png" type="image/png">',
    '<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">',
    f'<meta name="theme-color" content="#{THEME_COLOR}">',
    '<meta name="apple-mobile-web-app-capable" content="yes">',
    '<meta name="apple-mobile-web-app-title" content="Sunday School">',
    '<script src="/assets/register-sw.js" defer></script>',
]


def _shell(title: str, body: list[str], *, draft: bool) -> str:
    banner = ['<div class="draft-banner">Draft proof. Not approved. Do not distribute.</div>'] \
        if draft else []
    return "\n".join([
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_esc(title)}</title>",
        *HEAD_LINKS,
        "</head>",
        "<body>",
        *banner,
        '<div class="wrap">',
        *body,
        # Hidden until beforeinstallprompt fires. See REGISTER_SW.
        '<button class="install" id="install" type="button" hidden>'
        'Add to home screen</button>',
        "</div>",
        "</body>",
        "</html>",
        "",
    ])


def _masthead(church: str, home: str | None = None) -> list[str]:
    name = _esc(church)
    inner = f'<a href="{home}">{name}</a>' if home else name
    return [f'<p class="church">{inner}</p>']


def _art_credit(art) -> str | None:
    """The week's artwork credit, whatever shape the field is in.

    Rendered if it is there and skipped if it is not. Nothing here
    invents a caption: an artwork with no credit in `lesson.yml` gets no
    credit line, rather than one this renderer made up.
    """
    if not art:
        return None
    if isinstance(art, str):
        return _esc(art)
    if isinstance(art, dict):
        parts = [str(art[k]) for k in ("title", "artist", "year", "credit")
                 if art.get(k)]
        return _esc(", ".join(parts)) if parts else None
    return None


def _colophon(lesson: Lesson, source_hash: str) -> list[str]:
    """Credits, then the hash.

    The hash is the same string printed in the handout's colophon and
    carried in the app export. Three places, one value: if a page and a
    sheet in someone's hand disagree, these two lines say so without
    anybody reading both documents.
    """
    m = lesson.meta
    out = ["<footer>"]

    for key in ("copyright", "attribution"):
        if m.get(key):
            out.append(f"<p>{_inline(str(m[key]))}</p>")

    credit = _art_credit(m.get("art"))
    if credit:
        out.append(f"<p>Artwork: {credit}</p>")

    out.append(f'<p class="colophon">Source {_esc(source_hash)}</p>')
    out.append("</footer>")
    return out


# ---------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------

def piece_filename(piece: Piece) -> str:
    return f"{piece.order:02d}-{piece.id}.html"


def _church(lesson: Lesson) -> str:
    return str(lesson.meta.get("church") or "St. Paul Lutheran Church, Austin")


def _day_title(lesson: Lesson) -> str:
    return str(lesson.meta.get("liturgical_day") or lesson.slug)


def _date_display(lesson: Lesson) -> str:
    return str(lesson.meta.get("date_display") or lesson.meta.get("date") or "")


def _level_groups(lesson: Lesson) -> list[tuple[str, str, list[Piece]]]:
    """The Sunday's pieces as (key, heading, pieces), in level order.

    Levels in the order the export standard fixes, then the two all-ages
    pieces, then anything the manifest grows later. Sorting by a known
    order rather than by whatever the filesystem returned is what keeps
    two builds byte-identical.

    The key is what the grade filter anchors on, and it is the level name
    rather than the heading on purpose: a heading is prose and may be
    reworded, and rewording it must not break a bookmark a teacher is
    holding.
    """
    groups: list[tuple[str, str, list[Piece]]] = []
    for level in LEVEL_ORDER:
        pieces = sorted((p for p in lesson.pieces if p.level == level),
                        key=lambda p: p.order)
        if pieces:
            groups.append((level, LEVEL_HEADINGS[level], pieces))

    rest = sorted((p for p in lesson.pieces if p.level not in LEVEL_ORDER),
                  key=lambda p: p.order)
    if rest:
        groups.append((OTHER_LEVEL, "All Ages", rest))

    return groups


def _level_filter(groups: list[tuple[str, str, list[Piece]]]) -> list[str]:
    """A row of grade chips that narrows the piece list to one level.

    Links and :target, so this costs no JavaScript and works with it off.
    What it buys beyond the click is that the choice is in the URL: a
    superintendent can send the Intermediate teacher the four pieces she
    teaches rather than the page they are all on.

    The chips carry LEVEL_LABELS, which is the short wording the handouts
    and the app export already use, rather than the long LEVEL_HEADINGS
    the group headings carry. Neither is invented here; a level named two
    ways by two files is how a rename ends up half-done.

    One group needs no filter, so a Sunday with one gets none.
    """
    if len(groups) < 2:
        return []

    chips = [f'<a class="chip" href="#{PIECES_ID}">Show all</a>']
    for key, heading, _pieces in groups:
        label = LEVEL_LABELS.get(key) or heading
        chips.append(
            f'<a class="chip" href="#level-{_esc(key)}">{_esc(label)}</a>')

    return ['<nav class="levelfilter" aria-label="Filter by grade level">',
            *chips,
            "</nav>"]


def render_piece(lesson: Lesson, piece: Piece, source_hash: str,
                 *, draft: bool = False) -> str:
    m = lesson.meta
    heading = piece_heading(lesson, piece)
    title = piece.title or heading

    body = [
        '<div class="masthead">',
        *_masthead(_church(lesson), home="/"),
        f"<h1>{_esc(title)}</h1>",
        '<p class="meta">',
        f"<span>{_esc(heading)}</span>",
        f"<span>{_esc(_day_title(lesson))}</span>",
        f"<span>{_esc(_date_display(lesson))}</span>",
        "</p>",
        "</div>",
        f'<a class="backlink" href="/{_esc(lesson.slug)}/">All twelve pieces for this Sunday</a>',
    ]

    if m.get("theme") and m.get("theme_line_active", True):
        body.append(f'<p class="theme">{_inline(str(m["theme"]))}</p>')

    for section in piece.sections:
        body.append(f'<h2 class="section">{_esc(section.heading)}</h2>')
        body.extend(_render_body(section.body))

    body += _colophon(lesson, source_hash)
    return _shell(f"{title} · {_day_title(lesson)}", body, draft=draft)


def render_sunday(lesson: Lesson, source_hash: str, *, draft: bool = False) -> str:
    m = lesson.meta
    groups = _level_groups(lesson)

    body = [
        '<div class="masthead">',
        *_masthead(_church(lesson), home="/"),
        f"<h1>{_esc(_day_title(lesson))}</h1>",
        '<p class="meta">',
        f"<span>{_esc(_date_display(lesson))}</span>",
    ]
    if m.get("gospel"):
        body.append(f"<span>{_esc(m['gospel'])}</span>")
    if m.get("translation"):
        body.append(f"<span>{_esc(m['translation'])}</span>")
    body += ["</p>", "</div>"]

    # At the top, because it is a way past the reading as well as a
    # filter: the piece list sits below the text and the Law and Gospel
    # notes, and a teacher who opened this to find her own handout should
    # not have to scroll through a lesson to reach it. Each chip is an
    # anchor, so it scrolls to the list and narrows it in one tap.
    body += _level_filter(groups)

    if m.get("theme"):
        body.append(f'<p class="theme">{_inline(str(m["theme"]))}</p>')

    if m.get("gospel_text"):
        label = f"The Text ({m['translation']})" if m.get("translation") else "The Text"
        body.append(f'<h2 class="section">{_esc(label)}</h2>')
        body.append('<blockquote class="scripture">')
        body.append(f"<p>{_paragraph(str(m['gospel_text']))}</p>")
        body.append("</blockquote>")

    lg = m.get("law_and_gospel") or {}
    if isinstance(lg, dict) and (lg.get("law") or lg.get("gospel")):
        body.append('<h2 class="section">Law and Gospel in This Text</h2>')
        body.append('<div class="lawgospel">')
        for key, label in (("law", "The Law"), ("gospel", "The Gospel")):
            if lg.get(key):
                body += [
                    f'<div class="{key}">',
                    f'<span class="label">{label}</span>',
                    f"<p>{_paragraph(str(lg[key]))}</p>",
                    "</div>",
                ]
        body.append("</div>")

    body.append('<h2 class="section">The Twelve Pieces</h2>')

    # The whole week in one file, for a teacher who does not want
    # twenty-four downloads. Named to match what package.write() built.
    zip_name = f"{lesson.slug}-package" + ("-DRAFT" if draft else "") + ".zip"
    body.append(
        f'<p class="package"><a href="{HANDOUT_ROOT}/{_esc(lesson.slug)}/'
        f'{_esc(zip_name)}">Download the whole week</a> '
        f'<span class="note">every handout, PDF and Word, in one archive</span></p>')

    body.append(f'<div class="levels" id="{PIECES_ID}">')
    for key, heading, pieces in groups:
        body += [f'<div class="level" id="level-{_esc(key)}">'
                 f'<h3>{_esc(heading)}</h3>',
                 '<ul class="pieces">']
        for p in pieces:
            stem = f"{p.order:02d}-{p.id}" + ("-DRAFT" if draft else "")
            # Which piece this is, not what the lesson is called. Every
            # piece in a Sunday carries the lesson's title, so keying the
            # link on the title printed one phrase down the whole list and
            # left a teacher unable to tell their guide from the student
            # sheet standing next to it. PIECE_LABELS is the wording
            # handoff.py and appexport.py already use, so all three agree
            # about what a piece is called.
            name = PIECE_LABELS.get(p.type) or p.title or p.id
            body += [
                "<li>",
                f'<span class="name"><a href="/{_esc(lesson.slug)}/pieces/'
                f'{_esc(piece_filename(p))}">{_esc(name)}</a></span>',
                f'<span class="dl"><a href="{HANDOUT_ROOT}/{_esc(lesson.slug)}/'
                f'{_esc(stem)}.pdf">PDF</a></span>',
                f'<span class="dl"><a href="{HANDOUT_ROOT}/{_esc(lesson.slug)}/'
                f'{_esc(stem)}.docx">DOCX</a></span>',
                "</li>",
            ]
        body += ["</ul>", "</div>"]
    body.append("</div>")

    body += _colophon(lesson, source_hash)
    return _shell(_day_title(lesson), body, draft=draft)


def render_index(entries: list[dict], *, as_of: date,
                 church: str = "St. Paul Lutheran Church, Austin") -> str:
    """The site's front page: this week's Sunday, then what is coming,
    then everything already taught.

    `entries` are the `site-entry.json` files written beside each built
    Sunday, so the list is assembled from build output rather than from a
    second read of `content/`.

    WHY THE DATE IS AN ARGUMENT

    `as_of` is passed in and never read from a clock here. Everything
    under render/ has to produce the same bytes from the same inputs, and
    a front page that quietly reordered itself between two builds would
    break that on the one file most likely to be compared. The caller
    decides what day it is; publish_site.py is where that decision lives,
    because that is where the church's timezone is known.

    WHY A SUNDAY STAYS CURRENT ALL WEEK

    Sorting by date alone put a Sunday nobody has taught yet above the
    one being taught now. What a reader wants first is the lesson in use,
    and it stays in use for the whole week after it is taught: the family
    take-home is worked through at home, so demoting it on Monday buries
    a sheet a family is still in the middle of.

    So the current Sunday is the latest one on or before `as_of`, which
    holds it at the top until `as_of` reaches the next one.
    """
    body = [
        '<div class="masthead">',
        *_masthead(church),
        "<h1>Sunday School</h1>",
        '<p class="meta"><span>Lessons and handouts</span></p>',
        "</div>",
    ]

    def key(e: dict) -> tuple[str, str]:
        return (str(e.get("date", "")), str(e.get("slug", "")))

    cutoff = as_of.isoformat()
    dated = [e for e in entries if str(e.get("date", ""))]

    # Ascending, so the last element on or before the cutoff is the one
    # in use and everything before it has already been taught.
    taught = sorted((e for e in dated if str(e["date"]) <= cutoff), key=key)
    coming = sorted((e for e in dated if str(e["date"]) > cutoff), key=key)

    current = taught[-1:]
    earlier = list(reversed(taught[:-1]))

    # A Sunday with no date cannot be placed in the year at all, so it
    # goes last rather than being guessed at.
    undated = sorted((e for e in entries if not str(e.get("date", ""))), key=key)

    ordered = current + coming + earlier + undated

    if not ordered:
        body.append("<p>No lessons have been published yet.</p>")
    else:
        body.append('<ul class="sundays">')
        for e in ordered:
            slug = str(e.get("slug", ""))
            meta = [str(e[k]) for k in ("date_display", "gospel", "translation") if e.get(k)]
            body += [
                "<li>",
                f'<a class="day" href="/{_esc(slug)}/">'
                f'{_esc(e.get("liturgical_day") or slug)}</a>',
                '<p class="meta">' + "".join(f"<span>{_esc(x)}</span>" for x in meta) + "</p>",
            ]
            if e.get("theme"):
                body.append(f'<p class="theme">{_inline(str(e["theme"]))}</p>')
            body.append("</li>")
        body.append("</ul>")

    return _shell("Sunday School", body, draft=False)


def index_entry(lesson: Lesson, source_hash: str) -> dict:
    """What the front page needs to list this Sunday, and nothing more."""
    m = lesson.meta
    return {
        "slug": lesson.slug,
        "date": str(m.get("date", "")),
        "date_display": _date_display(lesson),
        "liturgical_day": m.get("liturgical_day"),
        "gospel": m.get("gospel"),
        "translation": m.get("translation"),
        "theme": m.get("theme"),
        "source_sha256": source_hash,
        "pieces_count": len(lesson.pieces),
    }


def write(lesson: Lesson, out_dir: Path, source_hash: str,
          *, draft: bool = False) -> list[Path]:
    d = out_dir / "site"
    pieces_dir = d / "pieces"
    pieces_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []

    index = d / "index.html"
    index.write_text(render_sunday(lesson, source_hash, draft=draft), encoding="utf-8")
    written.append(index)

    for piece in lesson.pieces:
        p = pieces_dir / piece_filename(piece)
        p.write_text(render_piece(lesson, piece, source_hash, draft=draft), encoding="utf-8")
        written.append(p)

    entry = d / "site-entry.json"
    entry.write_text(
        json.dumps(index_entry(lesson, source_hash), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    written.append(entry)

    return written


# ---------------------------------------------------------------------
# The app shell: manifest, service worker, registration
#
# These make the site installable, which is what a reader gets from the
# Base44 app today: an icon on the home screen and something that opens
# without a browser bar. Android's install prompt wants all three of a
# manifest, icons at 192 and 512, and a service worker with a fetch
# handler, so all three are here.
#
# WHAT THIS COSTS
#
# The pages were entirely free of JavaScript, and the Worker's CSP said
# so. Installability is not reachable without a service worker, so that
# property is traded for it. The trade is kept as small as it can be:
# every page still renders completely with JavaScript disabled, the one
# script is an external file so the CSP needs no 'unsafe-inline', and the
# worker only caches. Nothing on the site depends on it running.
# ---------------------------------------------------------------------

def render_manifest() -> str:
    """The web app manifest."""
    return json.dumps({
        "name": APP_NAME,
        "short_name": APP_SHORT_NAME,
        "description": "Weekly Sunday School lessons and handouts.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": f"#{BACKGROUND_COLOR}",
        "theme_color": f"#{THEME_COLOR}",
        "icons": [
            {"src": "/assets/icon-192.png", "sizes": "192x192",
             "type": "image/png", "purpose": "any"},
            {"src": "/assets/icon-512.png", "sizes": "512x512",
             "type": "image/png", "purpose": "any"},
            {"src": "/assets/icon-maskable-192.png", "sizes": "192x192",
             "type": "image/png", "purpose": "maskable"},
            {"src": "/assets/icon-maskable-512.png", "sizes": "512x512",
             "type": "image/png", "purpose": "maskable"},
        ],
    }, indent=2, ensure_ascii=False) + "\n"


REGISTER_SW = """\
/* Registers the service worker, which is the whole of this site's
   JavaScript. Everything renders without it; it adds offline reading and
   makes the site installable. */
if ("serviceWorker" in navigator) {
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js", { scope: "/" });
  });
}

/* The install offer.

   Chrome stopped showing an add-to-home-screen banner of its own in
   version 76. It fires beforeinstallprompt and leaves the offer to the
   site, so a site that ignores the event is installable only through a
   menu almost nobody opens. That is what the service worker above was
   traded for, and without this it was bought and never spent.

   The button ships hidden and is revealed only when the browser says
   the site can be installed, so it never offers something that would
   do nothing. Safari fires no such event and exposes no install API:
   on iOS the button stays hidden and Share, then Add to Home Screen,
   remains the only path. That is Apple's decision, not a gap here. */
(function () {
  var deferred = null;
  var button = document.getElementById("install");
  if (!button) return;

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    deferred = event;
    button.hidden = false;
  });

  button.addEventListener("click", function () {
    if (!deferred) return;
    deferred.prompt();
    deferred = null;
    button.hidden = true;
  });

  window.addEventListener("appinstalled", function () {
    deferred = null;
    button.hidden = true;
  });
})();
"""


def render_service_worker(version: str, precache: list[str]) -> str:
    """The service worker, versioned by the content it was built from.

    `version` must be derived from the published bytes, never from a
    clock. A cache keyed on build time would evict itself on every
    publish whether or not anything changed, and a cache keyed on nothing
    would serve last week's lesson forever. Keyed on the content, the
    cache turns over exactly when the content does.

    Pages are network-first so a republished Sunday reaches a reader who
    has signal. Handouts are never cached: a year of PDFs would fill a
    phone, and they are what the browser's own download is for.
    """
    return (
        "/* Generated by tools/stpaul/render/site.py. Do not edit. */\n"
        f'const CACHE = "stpaul-{version}";\n'
        f"const PRECACHE = {json.dumps(precache, indent=2)};\n"
        """
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE)
      // Individually, so one missing object cannot fail the whole install.
      .then((c) => Promise.all(PRECACHE.map((u) => c.add(u).catch(() => null))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// Handouts and archives are large and are what a download is for.
const NEVER_CACHE = /\\.(?:pdf|docx|zip)$/i;

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (NEVER_CACHE.test(url.pathname)) return;

  const isPage = req.mode === "navigate" ||
                 (req.headers.get("Accept") || "").includes("text/html");

  if (isPage) {
    // Network first: a reader with signal must see a republished Sunday.
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req).then((hit) => hit || caches.match("/")))
    );
    return;
  }

  // Everything else (the stylesheet, the icons, the manifest) is small,
  // versioned with the cache, and safe to serve from it first.
  event.respondWith(
    caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      if (res && res.ok) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
      }
      return res;
    }))
  );
});
"""
    )
