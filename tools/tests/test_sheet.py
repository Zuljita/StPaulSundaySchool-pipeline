"""The printed sheets.

Three properties matter more than how a sheet looks, because all three
are things that went wrong before and none of them is visible in a
screenshot.

  * **Nothing is dropped.** Every heading and every block of approved
    text reaches the page. Twelve pieces once went to print and five
    never reached the app.
  * **Nothing is invented.** An unfilled field prints as an absent block.
    The importers leave fields null on purpose and a renderer that fills
    one in has written curriculum.
  * **Nothing is remembered.** The palette, the type scale and the page
    geometry come off disk from design_standards/, which is what Core
    Standards section 5 requires. The renderer that this one replaced
    kept its own copy of all three, and every value in it was wrong by
    the time anyone noticed.

The fixture text here is invented. No verse, hymn stanza or catechism
line appears in this repository, and a test is not a reason to start.
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import fetch_fonts  # noqa: E402
from stpaul.model import load_lesson  # noqa: E402
from stpaul.render import sheet  # noqa: E402
from stpaul.render.blocks import blocks  # noqa: E402

SLUG = "2026-01-04-test"

# Every shared field left null, the way import_legacy.py writes a new
# Sunday. The sheets still have to build.
BARE_LESSON = """\
sunday: 2026-01-04-test
date: 2026-01-04
date_display: "January 4, 2026"
liturgical_day: "Trinity 99"
status: draft
title: null
theme: null
theme_line_active: false
gospel: null
translation: null
gospel_text: null
hymn:
  title: null
  lsb: null
art:
  source: null
  plate_title: null
memory_verses:
  primary: null
copyright:
  teacher_guide_notice: null
  student_facing_notice: null
law_and_gospel:
  law: null
  gospel: null
"""

FILLED_LESSON = """\
sunday: 2026-01-04-test
date: 2026-01-04
date_display: "January 4, 2026"
liturgical_day: "Trinity 99"
status: draft
title: "A title the pastor approved"
theme: "A theme line, identical on every piece."
theme_line_active: true
gospel: "Fakebook 1:1-4"
translation: ESV
gospel_text: "[1] Placeholder words one. [2] Placeholder words two."
hymn:
  title: "A Hymn Title"
  lsb: 578
art:
  source: null
  plate_title: "A Plate Title"
memory_verses:
  primary: "A memory line, invented for this test."
copyright:
  teacher_guide_notice: "Teacher notice."
  student_facing_notice: "Student notice."
law_and_gospel:
  law: null
  gospel: null
"""

TEACHER_GUIDE = """\
---
piece: primary-teacher-guide
type: teacher_guide
level: primary
order: 5
---

# Primary Teacher Guide

## What You Need

- One thing
- Another thing

## For the Teacher

A paragraph of teacher prose that must reach the page.

## Law and Gospel in this Text

Supplied verbatim. Do not improvise this section.

The Law. A first invented sentence about the law.

The Gospel. A second invented sentence about the gospel.

## The Lesson

### 1 · Welcome (4 min)

Say the invented welcome.

### 2 · Read it (8 min)

Read the invented thing.

## An Unexpected Section

Content nobody wrote a slot for.

## Credits

A credit line.
"""

STUDENT_HANDOUT = """\
---
piece: primary-student-handout
type: student_handout
level: primary
order: 6
---

# Primary Student Handout

## Mark Your Page

Circle an invented word.

## Write Your Answer

What do you think? ______________________________________

## From the Small Catechism

An invented catechism gloss.

## Memory Work

"An invented memory line."

Fakebook 1:1 (ESV)

Say it three times.
"""

FAMILY = """\
---
piece: family-take-home
type: family_take_home
level: all
order: 1
---

# Family Take Home

## The Verse to Say this Week

"An invented verse line for the week."

Fakebook 1:1 (ESV)

Say it in the car.

## One Question at Dinner

An invented dinner question?

## Credits

A credit line.
"""

NURSERY = """\
---
piece: nursery-notes
type: nursery_notes
level: nursery
order: 2
---

# Nursery Notes

## The One Thing

One invented sentence.

## Closing Prayer

An invented prayer.
"""

PIECES = {
    "05-primary-teacher-guide.md": TEACHER_GUIDE,
    "06-primary-student-handout.md": STUDENT_HANDOUT,
    "01-family-take-home.md": FAMILY,
    "02-nursery-notes.md": NURSERY,
}


def write_fixture(tmp: Path, lesson_yml: str) -> Path:
    content = tmp / "content"
    (content / SLUG / "pieces").mkdir(parents=True, exist_ok=True)
    (content / SLUG / "lesson.yml").write_text(lesson_yml, encoding="utf-8")
    for name, body in PIECES.items():
        (content / SLUG / "pieces" / name).write_text(body, encoding="utf-8")
    return content


def text_of(html: str) -> str:
    """The words a reader would see, with the markup taken out."""
    import html as _html
    stripped = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", _html.unescape(stripped))


class SheetTestCase(unittest.TestCase):
    lesson_yml = FILLED_LESSON

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="stpaul-sheet-"))
        content = write_fixture(self.tmp, self.lesson_yml)
        self.lesson = load_lesson(SLUG, content_dir=content)
        self.out = self.tmp / "handouts"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def render(self, piece_type: str) -> str:
        piece = next(p for p in self.lesson.pieces if p.type == piece_type)
        path = sheet.render(self.lesson, piece, "a" * 64,
                            self.out / sheet.filename(piece))
        return path.read_text(encoding="utf-8")


class NothingIsDropped(SheetTestCase):
    """Every approved block reaches the page, in every skeleton."""

    def test_every_block_of_every_piece_is_on_its_sheet(self):
        for piece in self.lesson.pieces:
            with self.subTest(piece=piece.id):
                html = self.render(piece.type)
                body = text_of(html)
                for section in piece.sections:
                    self.assertIn(section.heading, body,
                                  f"{piece.id}: the heading is missing")
                    for kind, block in blocks(section.body):
                        if kind == "rule":
                            continue
                        probe = self._probe(kind, block)
                        if probe:
                            self.assertIn(probe, body,
                                          f"{piece.id}: dropped a {kind}")

    @staticmethod
    def _probe(kind: str, block: str) -> str:
        """What of a block should survive, given how the design sets it.

        Three components take a block apart rather than printing it whole,
        and each takes a known, fixed prefix off the front. Nothing else
        may go missing.
        """
        text = block
        if kind == "subhead":
            m = sheet._STEP.match(text)
            if m:
                text = m.group("text")
        text = sheet._GOSPEL_LEAD.sub("", sheet._LAW_LEAD.sub("", text))
        text = sheet._WRITE_RULE.sub("", text)
        text = re.sub(r"[*_]", "", text).strip()
        return re.sub(r"\s+", " ", text)[:60]

    def test_a_section_with_no_slot_still_prints(self):
        html = self.render("teacher_guide")
        self.assertIn("An Unexpected Section", text_of(html))
        self.assertIn("Content nobody wrote a slot for", text_of(html))

    def test_the_law_gospel_lead_line_survives_the_split(self):
        """The pair takes two paragraphs. The third is not the pair's."""
        body = text_of(self.render("teacher_guide"))
        self.assertIn("Supplied verbatim", body)
        self.assertIn("A first invented sentence about the law", body)
        self.assertIn("A second invented sentence about the gospel", body)

    def test_the_prose_after_a_memory_verse_survives_the_panel(self):
        body = text_of(self.render("student_handout"))
        self.assertIn("An invented memory line", body)
        self.assertIn("Say it three times", body)


class NothingIsInvented(SheetTestCase):
    lesson_yml = BARE_LESSON

    def test_a_sunday_with_nothing_filled_in_still_builds(self):
        for piece in self.lesson.pieces:
            with self.subTest(piece=piece.id):
                self.assertIn("<section class=", self.render(piece.type))

    def test_no_placeholder_prose_reaches_an_empty_slot(self):
        for piece in self.lesson.pieces:
            body = text_of(self.render(piece.type)).lower()
            for word in ("lorem", "ipsum", "tbd", "todo", "placeholder",
                         "coming soon", "none"):
                self.assertNotIn(word, body,
                                 f"{piece.id}: {word!r} was written into a slot")

    def test_an_absent_plate_leaves_the_panel_empty_rather_than_filled(self):
        """readme.md: 'an absent image leaves the panel empty.'"""
        html = self.render("teacher_guide")
        self.assertIn('class="plate"', html)
        self.assertNotIn("<img class=\"plate\"", html)


class NothingIsRemembered(unittest.TestCase):
    """The design facts live in design_standards/ and are read from there."""

    SOURCE = (ROOT / "tools" / "stpaul" / "render" / "sheet.py").read_text(
        encoding="utf-8")

    def test_the_renderer_names_no_palette_colour(self):
        hexes = set(re.findall(r"#[0-9a-fA-F]{6}\b", self.SOURCE))
        self.assertEqual(
            hexes, {sheet.SCREEN_BACKDROP},
            "A colour is written into the renderer. Core Standards section 5: "
            "'If a design fact is needed, it is read from there, not "
            "remembered.' Use a token from design_standards/tokens/colors.css.")

    def test_the_renderer_names_no_typeface(self):
        for family in ("Instrument Serif", "Source Serif", "Montserrat",
                       "Lora", "Georgia", "Helvetica", "Times"):
            self.assertNotIn(
                f'"{family}', self.SOURCE,
                f"{family} is named in the renderer. The three families are "
                f"declared in design_standards/tokens/typography.css.")

    def test_the_stylesheet_carries_the_design_systems_tokens(self):
        css = sheet.stylesheet()
        tokens = (ROOT / "design_standards" / "tokens" / "colors.css").read_text(
            encoding="utf-8")
        navy = re.search(r"--navy:\s*(#[0-9a-f]{6})", tokens).group(1)
        self.assertIn(navy, css,
                      "the sheet stylesheet does not carry the system's navy")
        self.assertIn("--page-width: 816px", css.replace("  ", " "))

    def test_a_changed_token_reaches_the_sheet(self):
        """The point of reading rather than restating, made checkable."""
        colors = ROOT / "design_standards" / "tokens" / "colors.css"
        original = colors.read_text(encoding="utf-8")
        try:
            colors.write_text(original.replace("--navy: #082858",
                                               "--navy: #010203"),
                              encoding="utf-8", newline="\n")
            self.assertIn("#010203", sheet.stylesheet())
        finally:
            colors.write_text(original, encoding="utf-8", newline="\n")


class TheVendoredFaces(unittest.TestCase):
    """The three families are in the repository and are what they claim."""

    def test_every_face_matches_the_manifest(self):
        self.assertEqual(
            fetch_fonts.verify(), 0,
            "A vendored face is missing or has changed. Re-run "
            "tools/fetch_fonts.py --update and commit what it writes.")

    def test_the_stylesheet_points_at_files_that_exist(self):
        css = sheet.stylesheet()
        refs = set(re.findall(r"url\('\.\./assets/fonts/([^']+)'\)", css))
        self.assertTrue(refs, "the stylesheet declares no @font-face src")
        for name in refs:
            self.assertTrue((sheet.FONT_DIR / name).is_file(),
                            f"fonts.css points at {name}, which is not committed")

    def test_the_faces_are_copied_next_to_the_sheets(self):
        tmp = Path(tempfile.mkdtemp(prefix="stpaul-assets-"))
        try:
            written = sheet.write_assets(tmp)
            names = {p.name for p in written}
            self.assertIn(sheet.STYLESHEET_NAME, names)
            self.assertTrue(any(n.endswith(".woff2") for n in names))
            # The stylesheet's own relative paths have to resolve from where
            # it is written, or the browser silently sets the sheet in a
            # fallback and the PDF goes out in Segoe UI.
            css = tmp / sheet.ASSET_DIR / "tokens" / sheet.STYLESHEET_NAME
            for ref in set(re.findall(r"url\('([^']+)'\)",
                                      css.read_text(encoding="utf-8"))):
                self.assertTrue((css.parent / ref).resolve().is_file(),
                                f"{ref} does not resolve from {css.name}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TheSkeletons(SheetTestCase):

    def test_each_piece_type_gets_the_frame_the_design_project_gives_it(self):
        self.assertEqual(sheet.SKELETONS["craft_page"],
                         sheet.SKELETONS["student_handout"],
                         "the craft page borrows the student skeleton")
        guide = self.render("teacher_guide")
        self.assertEqual(guide.count('<section class="page'), 3)
        self.assertIn('class="page lesson"', guide,
                      "page 3 of a guide takes the tighter padding")
        self.assertEqual(self.render("student_handout").count('<section class="page'), 1)
        self.assertEqual(self.render("nursery_notes").count('<section class="page'), 1)

    def test_a_piece_type_nobody_planned_for_still_renders(self):
        piece = next(p for p in self.lesson.pieces if p.type == "student_handout")
        piece.meta["type"] = "midweek_thing"
        html = sheet.render(self.lesson, piece, "b" * 64, self.out / "x.html")
        self.assertIn("Circle an invented word", text_of(html.read_text(encoding="utf-8")))

    def test_the_nursery_chip_carries_its_age_range(self):
        self.assertIn(sheet.NURSERY_CHIP, text_of(self.render("nursery_notes")))


class TheText(SheetTestCase):

    def test_a_typed_rule_becomes_a_ruled_line(self):
        """Forty underscores is one unbreakable word and runs off the sheet."""
        html = self.render("student_handout")
        self.assertNotIn("______", html)
        self.assertIn('class="lines"', html)
        self.assertIn("What do you think?", text_of(html))

    def test_content_is_escaped(self):
        piece = next(p for p in self.lesson.pieces if p.type == "nursery_notes")
        piece.sections[0].body = 'A <script>alert("x")</script> line.'
        html = sheet.render(self.lesson, piece, "c" * 64,
                            self.out / "esc.html").read_text(encoding="utf-8")
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)

    def test_a_verse_number_is_set_as_a_superscript(self):
        html = self.render("student_handout")
        self.assertIn("<sup>1</sup>", html)
        self.assertNotIn("[1]", html)

    def test_the_lesson_steps_carry_their_minutes(self):
        html = self.render("teacher_guide")
        self.assertIn("4 min", text_of(html))
        self.assertIn('class="step"', html)


if __name__ == "__main__":
    unittest.main()
