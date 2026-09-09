# St. Paul Sunday School Design System

The print system behind St. Paul Lutheran Church's weekly Sunday School handouts: twelve
documents a week, every level studying the same Gospel text, every week looking identical.
This system exists so that only the content changes.

It is a **print** design system. There is no app, no website, no screen product. Every
component is measured for a letter sheet coming out of a color laser printer, and the
foremost constraint is that the page box clips — a sheet that runs long loses its footer
silently.

## Sources

- The church logo, supplied by the user as `StPaul_Logo_H_Solid_Color.png` — the entire
  palette is sampled from it.
- Thirteen source documents for one week: one master review document and twelve per-piece
  PDFs, covering nursery through high school. They are weekly content and are not kept here.
- The twelve production documents built from them. Those are weekly output and are not
  kept here. `Design Standard.dc.html`, the printed three-page statement of this system,
  and `CLAUDE.md`, the production spec, do live here.
- A public-domain painting supplied as the week's artwork, swapped every week.

No Figma file, no codebase, no prior brand guidelines were provided. Where this system makes
a judgment the sources did not settle, it is noted below.

## Content fundamentals

**Voice: plain, declarative, unhurried.** Short sentences carrying one idea. The writing
trusts the reader and refuses to sell. "You have a Father. He knows. Go to sleep."

**Second person, addressed to the person holding the sheet.** Teacher's guides speak to the
teacher ("Ask it out loud today at least four times"). Family pages speak to the parent
("You are probably the ones carrying the anxiety, not them"). Student sheets address the
child directly ("Circle the word *therefore* in verse 25").

**Instructions are imperative and open with a bolded lead phrase.** "**Opening.** Sign of
the cross." — "**The pitfall.** Do not let this become don't worry, God has a plan for you."
The bolded phrase is the scannable handle; the sentence after it does the work.

**Sentence case everywhere except labels.** Titles are sentence case ("You cannot serve two
masters"), never title case. All-caps is confined to Montserrat labels, chips, and meta.
Never set a memory verse in caps — it is the hardest setting for a new reader.

**Questions are printed as questions, in quotation marks, in the display face.** "Why does
Jesus talk about birds?" The answer follows in body type, and answers a child's question
without softening it: "Yes, and do not dodge it."

**Named things are named consist.** Title, Theme Line, Level Question, Collect, Catechism
Recitation, Apostolic Benediction. These are terms of art in this system; `CLAUDE.md` holds
the glossary and the terms never drift week to week.

**No emoji, ever.** No exclamation points outside quoted hymn text. No rhetorical
scaffolding ("Here's why this matters"). No em-dash asides where a period will do.

## Visual foundations

**The two-column frame.** Nearly every piece is a `1 : minmax(0, 2.05)` grid with a 26px
gutter and a hairline rule between: a **reference rail** on the left holding what a teacher
reaches for (what you need, the hymn, the Catechism, the prayer, the artwork), and the
**week's substance** on the right. The family take-home is the exception — no rail, flowing
two- and three-column bands instead.

**Color.** Sampled from the logo, and no color is decorative. Navy `#082858` for display
type, chips, and solid panels. Blue `#2858b8` for section labels, accents, and the Gospel
rule. Light blue `#88c8d8` for hairlines, tints, and labels reversed on navy. Red
`#a81818` has exactly two jobs: verse numbers and the Law marker. Body ink is near-black
`#1c1c19` — **never navy**, which reads black on screen and prints visibly blue. Paper is
`#fffefb`, a hair warm of white.

**Type.** Three faces, three jobs, no overlap. Instrument Serif for display only — h1 38px,
section titles 27–30px, pull quotes and memory verses 17–21px, italic for the Theme Line.
Source Serif 4 for all body copy at three sizes: teacher narrative 15px, sidebars 13.5px,
Gospel 12.5–13.5px. Montserrat for labels, meta, footers, and verse numbers — always
uppercase, tracked 0.1–0.13em, weight 500–600, never inside a sentence. 12px is the floor
for anything read aloud.

**Backgrounds.** Flat paper. No gradients, no photographic backgrounds, no textures, no
patterns. Exactly two fills exist: the pale blue tint panel `#eef7fa` for texts spoken
aloud, and the solid navy panel for the one thing the room should leave with. Both depend on
background graphics being enabled at print.

**Corner radii: none.** Every panel, chip, and border is square. The system has no rounded
corners anywhere, deliberately — it reads as a printed church document, not a web card.

**Shadows: none.** No inner shadows, no outer shadows, no elevation. Hierarchy is carried by
rule weight, fill, and type size alone.

**Rules carry the structure.** 2px navy under the page-one masthead; 1px navy under running
headers; 2px red and 2px blue over the Law and Gospel columns; 0.5px light blue for rail
dividers, block separators, and footers; 0.5px `#cfe0ea` for column rules and lesson-step
separators; 0.5px `#9fb2c9` for writing lines. Rule weight is the primary signal of rank.

**Cards, as such, do not exist.** There are panels — a fill, square corners, no border, no
shadow. The only bordered box is the artwork panel (0.5px light blue) and the dashed
specimen frames on the Design Standard, which never appear on a real sheet.

**Transparency and blur: none.** All ink is full-opacity; muted text uses a lighter ink
color, never alpha. Alpha-muted type at these sizes fails on a laser printer.

**Animation and interaction states: none.** This is paper. The system has no hover, press,
focus, or transition behavior, and the component set deliberately declines to invent any.

**Imagery** is public-domain classic religious art — painting or engraving of the week's
text — cropped `object-fit: cover` into a fixed 168px panel at the foot of the student rail,
credited in 8px Montserrat beneath. Warm, dark, figurative, nineteenth century. Never
illustration, never clip art, never a drawn substitute: an absent image leaves the panel
empty.

**Layout is fixed, not fluid.** The page is exactly 816 × 1056 px with 0.4in / 0.55in /
0.34in margins (lesson pages tighten to 0.34 / 0.55 / 0.3). The inner wrapper is a
full-height flex column and the footer takes `margin-top: auto`, so it pins to the foot of
the sheet; every sibling takes `flex: none`, or a squeezed multi-column block spills
sideways off the page.

**Density.** Deliberately high, and earned: a volunteer holding three sheets will read none
of them, so each piece carries everything its room needs. The relief valve is a second page,
never smaller type.

## Iconography

**There is no icon set, and the system does not want one.** No icon font, no SVG sprite, no
CDN library. Two Unicode characters do all the work:

- `□` (U+25A1) in light blue `#88c8d8` — the checkbox in every What You Need list.
- `■` (U+25A0) in the current season color — the church-year marker in the meta block.

Both are set in the body face at body size, inline, with no wrapper. No emoji appear
anywhere in this system, and none should be introduced.

Raster assets, both supplied by the church:

- `assets/stpaul-logo.png` — the horizontal solid-color logo. Locked up at 152px wide,
  baseline-aligned with the words **Sunday School** so it reads "St. Paul Sunday School."
  In running headers the whole thing becomes 9.5px text instead.

Never draw, reconstruct, or approximate the church's mark. If the file is unavailable, set
the church name in plain type.

## Index

| Path | What it is |
|---|---|
| `styles.css` | The entry point. `@import` lines only. |
| `tokens/fonts.css` | The three Google-hosted families. |
| `tokens/colors.css` | Base, season, and semantic color tokens. |
| `tokens/typography.css` | Families, sizes, line-heights, tracking, weights. |
| `tokens/geometry.css` | Page box, margins, the rail grid, stacks, panel and chip padding. |
| `components/masthead/` | Masthead, IdentityChip, RunningHeader, ThemeLine. |
| `components/content/` | SectionLabel, Scripture, LawGospelPair, TintPanel, NavyPanel, LessonStep. |
| `components/worksheet/` | CheckList, WritingLines, ArtworkPanel. |
| `components/sheet/` | Sheet, SheetFooter. |
| `guidelines/` | Fifteen specimen cards: colors, type, spacing, brand, standing rules. |
| `ui_kits/handouts/` | A complete printed sheet, token-driven, registered as a Starting Point. |
| `assets/` | Logo and weekly artwork. |
| `SKILL.md` | Agent-Skills wrapper, for use in Claude Code. |

## Intentional additions

The sources define nine components on the printed Design Standard. This system ships
fifteen, splitting three of those nine into their constituent parts so each has its own props
contract:

- **IdentityChip** split out of Masthead — it also appears alone in running headers.
- **SectionLabel** split out as its own component — it opens every block on every sheet and
  is the most-reused element in the system.
- **TintPanel** and **NavyPanel** separated, where the Standard treats panels as one
  component — their rules of use differ sharply (many per sheet vs. exactly one).
- **Sheet** and **SheetFooter** added — the page box and footer pinning are described as page
  geometry on the Standard rather than as components, but every piece needs them and getting
  the flex column wrong is the single most common way a sheet breaks.

Nothing here has no counterpart on a printed sheet. No general-purpose UI primitives
(Button, Input, Dialog) exist or should be added: nothing in this system is interactive.

## Caveats

- **Fonts are Google-hosted.** No desktop or self-hosted binaries were supplied, so
  `tokens/fonts.css` links Google Fonts rather than declaring local `@font-face` rules.
  If the church licenses desktop cuts, drop them in `assets/fonts/` and swap that import.
- **The palette is sampled from a solid-color logo**, not from a brand guide. The hexes are
  the ones in production use, but no official brand values were provided to check them
  against.
