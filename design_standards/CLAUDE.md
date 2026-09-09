# St. Paul Lutheran Church — Sunday School handout system

Weekly set of 12 print documents, one Gospel text across every level. Every week
looks identical; only the content changes. This file is the spec. Follow it exactly.

## What lives here, and what does not

This directory holds the design system only: tokens, components, guidelines, the
three skeletons, and `Design Standard.dc.html`. It holds no Scripture, no hymn
text, no prayers, and no lesson prose, because this repository is publishable
precisely on the condition that it holds none. Every specimen on every page here
is Latin filler, which is deliberate: filler that cannot be mistaken for English
cannot ship as curriculum by accident.

The week's content, and the twelve documents built from it, belong with the data
repository under `$STPAUL_DATA`. Do not bring either back into this directory,
and do not write curriculum prose here to fill a slot. Named slots carry
`data-slot` attributes; leave them empty rather than invent text for them.

## Weekly workflow

1. The user supplies the week's content (usually one master document or a set of PDFs,
   one per piece).
2. Duplicate nothing new: edit the existing `.dc.html` files in place, replacing content
   and the date/occasion line. The layout, palette, and type never change week to week.
   Those production files live with the week's content, not here.
3. Rebuild `Weekly Packet.dc.html` (all 24 pages merged, in numbered order) after any
   change to an individual document. It is a snapshot, not a live include.
4. Verify page fit on every page before delivering (procedure below).

## The 12 pieces, in order

| # | File | Pages | Chip text |
|---|------|-------|-----------|
| 01 | `Family Take-Home.dc.html` | 2 | Family Take-Home |
| 02 | `Nursery Notes.dc.html` | 1 | Nursery Notes · Birth–3 |
| 03 | `Pre-K Teachers Guide.dc.html` | 3 | Pre-K / K · Teacher's Guide |
| 04 | `Pre-K Craft Page.dc.html` | 1 | Pre-K / K · Craft Page |
| 05 | `Primary Teachers Guide.dc.html` | 3 | Primary 1–2 · Teacher's Guide |
| 06 | `Primary Student Handout.dc.html` | 1–2 | Primary 1–2 · Student Handout |
| 07 | `Intermediate Teachers Guide.dc.html` | 3 | Intermediate 3–5 · Teacher's Guide |
| 08 | `Intermediate Student Handout.dc.html` | 1–2 | Intermediate 3–5 · Student Handout |
| 09 | `Middle School Teachers Guide.dc.html` | 3 | Middle School · Teacher's Guide |
| 10 | `Middle School Student Handout.dc.html` | 1–2 | Middle School · Student Handout |
| 11 | `High School Teachers Guide.dc.html` | 3 | High School · Teacher's Guide |
| 12 | `High School Student Handout.dc.html` | 1–2 | High School · Student Handout |

Three skeletons only: **teacher's guide**, **student handout**, **family take-home**
(the craft page borrows the student skeleton). Levels differ by name, never by layout.

## The design standard

`Design Standard.dc.html` is the printed, three-page statement of this system: page
geometry, palette, type, the nine components with live specimens, the three skeletons, and
the standing rules. It is the reference for extending the system to any new handout — a new
level, a midweek class, a seasonal piece. Keep it in step: when a rule here changes, change
it there too, and bump its revision number.

## Technical construction

- Every document is a Design Component (`Name.dc.html`), letter portrait, explicitly
  paginated: one `<section class="page">` per printed page inside `<doc-page>`.
- Page box is exactly **816 × 1056 px**. Content that misses it is clipped, not reflowed.
- Each page's inner wrapper: `padding: 0.4in 0.55in 0.34in; height: 100%;
  box-sizing: border-box; display: flex; flex-direction: column;` and the footer carries
  `margin-top: auto` so it pins to the foot of the sheet. Give every direct child of that
  flex column `flex: none` — a squeezed CSS-multicolumn block spills sideways off the page.
- Teacher's guide page 3 uses tighter padding: `0.34in 0.55in 0.3in`.
- Every logic class needs this mount nudge, or `<doc-page>` never applies its page box:

  ```js
  componentDidMount() {
    const kick = () => {
      const el = document.querySelector('doc-page');
      if (el && typeof el._measure === 'function') { try { el._measure(); } catch (e) {} }
    };
    requestAnimationFrame(kick);
    [0, 120, 600, 1500].forEach(function (t) { setTimeout(kick, t); });
  }
  ```

- One tweakable prop: `seasonColor` (color, default `#2e6b4b` green for Trinity). It colors
  the small ■ in the header meta block. Options: `#2e6b4b` green, `#a81818` red,
  `#5b3f8c` violet, `#082858` blue, `#c9a227` gold.
- Inline styles only. No stylesheets, no CSS classes.

## Palette (sampled from the church logo)

| Role | Hex |
|------|-----|
| Navy — display headings, chips, solid panels | `#082858` |
| Blue — section labels, accents, rules | `#2858b8` |
| Light blue — hairlines, tints, panel labels | `#88c8d8` |
| Red — verse numbers, the Law marker | `#a81818` |
| Body ink — near-black, **never navy** (navy prints blue) | `#1c1c19` |
| Secondary body text | `#3b3b36` |
| Muted meta, footers, notes | `#5c5c54` |
| Paper | `#fffefb` |
| Tint panel background | `#eef7fa` |
| Writing rules | `#9fb2c9` |

## Type

- **Instrument Serif** — h1 (38px), section titles (27–30px), pull quotes, memory verses,
  question prompts. Never for body copy.
- **Source Serif 4** — all body copy. Teacher narrative 14.5–15px; sidebars, activities and
  Gospel text 12–13.5px; line-height 1.45–1.55.
- **Montserrat** — chips, section labels, meta, footers, verse numbers. Uppercase,
  letter-spacing 0.1–0.13em, weight 500–600. Labels 10px, meta 9px, footer credits 8.5px.

## Header anatomy (page 1 of every piece)

1. Logo `assets/stpaul-logo.png` at 152px wide, baseline-aligned with the words
   **Sunday School** (Montserrat 13px, 600, navy) — reads "St. Paul Sunday School".
2. Navy chip, white Montserrat 11.5px 600 uppercase, `padding: 4px 10px` — level and
   document type together (see table above).
3. h1 in Instrument Serif 38px navy: the Gospel's title for the week
   Same on every level.
4. Right-aligned meta block, Montserrat 9px uppercase: date / occasion(s) / Gospel
   reference / ■ season. Print both occasions when both apply.
5. 2px navy rule under the whole header.
6. Below the rule: the **Theme Line** in Instrument Serif italic 21–22px blue — the locked
   one-sentence theme for the week, printed under the masthead on all twelve pieces in
   identical wording — followed, on teacher's guides and student handouts, by that level's
   Level Question in small roman type.

Running headers (pages 2+): "St. Paul Sunday School" plus the same chip, left; date and
season right; 1px navy rule.

## Footers

Montserrat 9px uppercase, hairline rule above, pinned to the foot of the sheet:
piece and date left, "Page n of m" right. The ESV / hymn-license / authorship credit line
appears once per document, in 8.5px sentence case under the running line.

## Structure per skeleton

**Teacher's guide (3 pages)**

- Page 1 — sidebar: What You Need (checkbox list), Time Today (tint panel), The Text,
  This Week in the Room. Main column: For the Teacher, Law and Gospel (two columns, Law
  under a red rule, Gospel under a blue rule), Memory Work This Week.
- Page 2 — the Gospel printed in full, two columns with a hairline column rule and red
  superscript verse numbers; then What Children Ask (or Discussion Guardrails for middle
  and high school) beside From the Small Catechism.
- Page 3 — The Lesson: numbered steps in a 78px minute-column grid, each step
  self-contained. Every prayer, hymn stanza, recitation, memory verse, closing prayer and
  the Apostolic Benediction is printed inline in a tint panel at the step where it is used.
  A teacher never turns a page mid-step and never hunts for a text.

**Student handout (1 or 2 pages)**

Any student handout may run to a second page when the week's content needs it. One page is
the default; never crowd a sheet to hold the line at one.

- Sidebar: Hymn stanza, From the Small Catechism, the Collect, then the artwork panel
  (168px tall, `object-fit: cover`, with a small credit line).
- Main column: the Gospel in full (two columns), the navy Memory Work panel, then the
  week's activities side by side with ruled writing lines.

**Family take-home (2 pages)**

- Page 1: header, Theme Line beside the week's verse, the "same Gospel at every level"
  paragraph, then The Question Each Room Was Asked (all six Level Questions in a
  three-column rule-bounded band), then What They Heard in two flowing columns.
- Page 2: A Word for the Parents in two columns, then a three-column band — the navy verse
  panel and the highlighted dinner question; the Catechism and Pray This Together; the hymn
  and For Further Study.

## Terminology

- **Title** — the h1, the Gospel's title for the week.
- **Theme Line** — the locked one-sentence theme under the masthead, identical on all twelve.
- **Collect** — the week's original prayer in the traditional five-part form. Never call it
  the Opening Prayer.
- **Level Question** — the fixed question belonging to a level (below), not a weekly field.

## Level Questions (fixed, never retyped weekly)

Printed on that level's Teacher's Guide and Student Handout, and all six together on the
Family Take-Home.

| Level | Question |
|-------|----------|
| Nursery | none — presence, not instruction |
| Pre-K / K | What happened? |
| Primary 1–2 | What happened, and what does this mean? |
| Intermediate 3–5 | Where is the Law here, and where is the Gospel? |
| Middle School | Is this true? What does it demand of me, and what does it give to me? |
| High School | How do I confess this in a world that denies it? |

## Shared texts — distribution map (fixed)

The week's shared texts are supplied once and distributed as follows.

- **Gospel text** — printed wherever the room reads it: all levels.
- **Hymn stanza** — printed in full on all five Teacher's Guides, all four Student Handouts,
  the Craft Page, and the Family Take-Home.
- **Hymn stanza + Catechism text at the front of the Student Handout** — Primary,
  Intermediate, and Middle School, for live use during the Opening.
- **Catechism recited aloud in the Opening** — Primary, Intermediate, Middle School only.
  Not High School, not Pre-K/K, not Nursery.
- **The Collect** — Primary, Intermediate, Middle School, High School. Not Pre-K/K, not
  Nursery.
- **Pre-K/K and Nursery Opening** — the Invocation and "Jesus Loves Me." Not the week's
  hymn, not the Collect.
- **Prayer requests** — gathered before the Closing Prayer at Nursery, Pre-K/K, and Primary.
  Not at Intermediate, Middle School, or High School. Standing, never a weekly decision.
- **Closing order, every piece** — Closing Prayer, then the Lord's Prayer, then the
  Apostolic Benediction last.

## Scripture setting

- Verse numbers are **small superscript in red `#a81818`**, Montserrat, ~8px.
- The Gospel sets as running prose in two columns — never one verse per line — with a
  hairline column rule.
- ESV throughout; the ESV notice appears once per document in the footer credit line.

## Content rules

- The user's text is verbatim. Format it; never rewrite, tighten, or paraphrase it.
- Never print internal production apparatus (e.g. "Piece Specifications §5b") on a sheet a
  volunteer holds.
- The Lord's Prayer is said from memory and is **never printed**. The Apostolic Benediction
  **is** printed on every piece, positioned last in the Closing, after the Lord's Prayer:
  "The grace of our Lord Jesus Christ, the love of God, and the communion of the Holy Spirit
  be with you all. Amen."
- Levels without a Catechism Recitation (Pre-K/K, High School, Nursery) must not carry the
  sidebar sentence promising one.
- Artwork: a public-domain painting or engraving of the week's text, supplied with the
  week's content and credited in 8px Montserrat under the image. It is swapped every week
  and is not kept here; the panel geometry never changes.

## Print

- Export per file: Export → PDF, then set Destination to "Save as PDF". Scale 100%,
  margins Default or None, Background graphics ON (the navy panels depend on it).
- `Weekly Packet.dc.html` exports the whole 24-page set as one PDF.
- 12pt is the floor for anything a volunteer reads aloud; small labels may go to 10px.

## Fit check before delivering (required)

Open each file and confirm zero overflow on every page:

```js
[...document.querySelectorAll('.page')].map(p =>
  Math.round(p.firstElementChild.scrollHeight - p.firstElementChild.clientHeight))
// every value must be 0
```

Also confirm the footer bottom sits at ~1023 (0.34in inset) rather than past 1056. When a
page runs long, trim in this order: sidebar gaps, body size by 0.5px, artwork panel height,
then move a whole block to the page that has room. Never shrink the Gospel below 12px.
