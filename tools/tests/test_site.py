"""Tests for the public site.

The site is a renderer, not an export, and everything below is a way of
holding it to that. An export is handed to another system that re-derives
a reading of it, and the last time that happened 5 of 12 pieces never
arrived and 0 of the 7 that did matched the print. A renderer cannot
drift from its siblings, but only while three things stay true:

  * it reads the same blocks the DOCX and PDF renderers read,
  * it is a pure function of the approved bytes, and
  * it escapes every one of those bytes before a browser sees them.

The third one is new with this renderer and it is the one with teeth.
DOCX and PDF are read by Word and by a viewer; HTML is read by a browser
on a public origin, and curriculum text has carried raw markup before now
(`import_app.detag` exists because the app served `<sup>` tags inside
verse text). A missed escape there is not a typographic bug.

Run:  python -m unittest discover -s tools/tests -v
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from html import unescape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIXTURE_STANDARDS = Path(__file__).resolve().parent / "data" / "standards"
ROOT = Path(__file__).resolve().parents[2]
RENDER_DIR = ROOT / "tools" / "stpaul" / "render"
WORKER = ROOT / "services" / "site" / "worker.js"

from stpaul import approval, hashing
from stpaul.model import load_lesson
from stpaul.render import blocks as blocks_mod
from stpaul.render import docx_render, pdf_render, site

SLUG = "2026-01-04-test"

LESSON_YML = """\
sunday: 2026-01-04-test
date: 2026-01-04
date_display: "January 4, 2026"
liturgical_day: "Test Sunday"
status: draft
gospel: "Luke 1:1-4"
translation: ESV
theme: "A theme line, identical on every piece."
gospel_text: |-
  Inasmuch as many have taken in hand to set in order a narrative.
law_and_gospel:
  law: "The law accuses."
  gospel: "Christ answers it."
copyright: "Scripture quotations are from the ESV(R) Bible."
attribution: "Built for St. Paul Lutheran Church."
"""

# Deliberately hostile: a heading and a body carrying the characters a
# browser treats as markup, in the shapes curriculum text actually takes.
PIECE = """\
---
piece: family-take-home
type: family_take_home
level: all
order: 1
---

# Family Take-Home

## What They Heard <script>alert(1)</script>

A retelling with <b>tags</b>, an & ampersand, and a "quoted" phrase.

Ask it out loud: <img src=x onerror=alert(1)>

## A Word for the Parents

**Opening.** Sign of the cross.

- First thing
- Second thing

> Quoted Scripture, set apart.

### A subhead inside the section

*Gently*, and then plainly.
"""

SECOND_PIECE = """\
---
piece: prek-teacher-guide
type: teacher_guide
level: pre_k
order: 3
---

# Pre-K Teacher's Guide

## What You Need

A card and a crayon.
"""


def build_lesson(tmp: Path) -> tuple[Path, str]:
    """Write the fixture Sunday and return (content_dir, hash)."""
    content = tmp / "content"
    (content / SLUG / "pieces").mkdir(parents=True)
    (content / SLUG / "lesson.yml").write_text(LESSON_YML, encoding="utf-8")
    (content / SLUG / "pieces" / "01-family-take-home.md").write_text(
        PIECE, encoding="utf-8")
    (content / SLUG / "pieces" / "03-prek-teacher-guide.md").write_text(
        SECOND_PIECE, encoding="utf-8")
    digest, _ = hashing.content_hash(content / SLUG)
    return content, digest


class SiteRenderTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="stpaul-site-"))
        self.content, self.digest = build_lesson(self.tmp)
        self.lesson = load_lesson(SLUG, content_dir=self.content)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def written(self, *, draft=False) -> dict[str, str]:
        out = self.tmp / ("draft" if draft else "dist")
        paths = site.write(self.lesson, out, self.digest, draft=draft)
        return {p.relative_to(out).as_posix(): p.read_text(encoding="utf-8")
                for p in paths}

    # -- escaping ------------------------------------------------------

    def test_markup_in_a_body_never_reaches_the_page_as_markup(self):
        """The one failure mode a print renderer does not have."""
        html = self.written()["site/pieces/01-family-take-home.html"]
        self.assertNotIn("<script>", html)
        self.assertNotIn("<b>tags</b>", html)
        self.assertNotIn("<img src=x", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;b&gt;tags&lt;/b&gt;", html)
        self.assertIn("&amp;", html)

    def test_markup_in_a_heading_never_reaches_the_page_as_markup(self):
        """Headings go through a different path than bodies, so test both."""
        html = self.written()["site/pieces/01-family-take-home.html"]
        heading = re.search(r'<h2 class="section">(.*?)</h2>', html, re.S)
        self.assertIsNotNone(heading, "no section heading was rendered")
        self.assertNotIn("<script>", heading.group(1))
        self.assertIn("&lt;script&gt;", heading.group(1))

    def test_every_page_escapes_every_angle_bracket_it_did_not_write(self):
        """Count tags rather than trust a spot check.

        Every `<` in the output must open a tag this renderer emitted.
        Anything else is content that got through unescaped.
        """
        allowed = re.compile(
            r"</?(?:!doctype|html|head|meta|title|link|body|div|p|h1|h2|h3|"
            r"a|span|ul|li|strong|em|br|blockquote|footer)\b[^<]*?>",
            re.I)
        for name, html in self.written().items():
            if not name.endswith(".html"):
                continue
            stripped = allowed.sub("", html)
            self.assertNotIn("<", stripped,
                             f"{name} carries a '<' this renderer did not emit")

    # -- the hash ------------------------------------------------------

    def test_every_page_carries_the_source_hash(self):
        """The colophon is how a page and a sheet are compared."""
        for name, html in self.written().items():
            if name.endswith(".html"):
                self.assertIn(self.digest, html,
                              f"{name} carries no source hash")

    def test_the_hash_is_the_one_the_handouts_carry(self):
        """Not a hash of the page: a hash of the approved content."""
        html = self.written()["site/index.html"]
        current, _ = hashing.content_hash(self.content / SLUG)
        self.assertIn(current, html)

    # -- determinism ---------------------------------------------------

    def test_two_renders_are_byte_identical(self):
        a = site.render_sunday(self.lesson, self.digest)
        b = site.render_sunday(self.lesson, self.digest)
        self.assertEqual(a, b)

        piece = self.lesson.pieces[0]
        self.assertEqual(site.render_piece(self.lesson, piece, self.digest),
                         site.render_piece(self.lesson, piece, self.digest))

    def test_two_writes_are_byte_identical(self):
        first = self.written()
        second = {k: v for k, v in self.written().items()}
        self.assertEqual(first, second)

    def test_piece_order_does_not_depend_on_the_filesystem(self):
        """Reversing the on-disk order must not reorder the page."""
        html = self.written()["site/index.html"]
        lesson = load_lesson(SLUG, content_dir=self.content)
        lesson.pieces.reverse()
        again = site.render_sunday(lesson, self.digest)
        self.assertEqual(html, again)

    # -- drafts --------------------------------------------------------

    def test_a_draft_says_so_on_every_page(self):
        for name, html in self.written(draft=True).items():
            if name.endswith(".html"):
                self.assertIn("draft-banner", html, f"{name} is not marked draft")
                self.assertIn("Not approved", html)

    def test_a_release_carries_no_draft_marking(self):
        for name, html in self.written().items():
            if name.endswith(".html"):
                self.assertNotIn("draft-banner", html)

    def test_a_draft_links_at_the_files_the_build_actually_wrote(self):
        """build.py suffixes draft handouts with -DRAFT; the links must too."""
        html = self.written(draft=True)["site/index.html"]
        self.assertIn("01-family-take-home-DRAFT.pdf", html)
        release = self.written()["site/index.html"]
        self.assertIn("01-family-take-home.pdf", release)
        self.assertNotIn("-DRAFT", release)

    # -- structure -----------------------------------------------------

    def test_a_page_exists_for_every_piece(self):
        names = set(self.written())
        for piece in self.lesson.pieces:
            self.assertIn(f"site/pieces/{site.piece_filename(piece)}", names)

    def test_the_index_entry_carries_what_the_front_page_lists(self):
        entry = json.loads(self.written()["site/site-entry.json"])
        self.assertEqual(entry["slug"], SLUG)
        self.assertEqual(entry["source_sha256"], self.digest)
        self.assertEqual(entry["pieces_count"], len(self.lesson.pieces))

    def test_the_front_page_orders_sundays_newest_first(self):
        html = site.render_index([
            {"slug": "2026-01-04-a", "date": "2026-01-04", "liturgical_day": "Older"},
            {"slug": "2026-02-15-b", "date": "2026-02-15", "liturgical_day": "Newer"},
        ])
        self.assertLess(html.index("Newer"), html.index("Older"))

    def test_an_empty_front_page_says_so_rather_than_breaking(self):
        self.assertIn("No lessons", site.render_index([]))

    def test_no_artwork_credit_is_invented(self):
        """A missing credit gets no line, not one this renderer wrote."""
        self.assertIsNone(site._art_credit(None))
        self.assertIsNone(site._art_credit({}))
        self.assertEqual(site._art_credit({"title": "Sower", "artist": "van Gogh"}),
                         "Sower, van Gogh")


class OneBlockParserTestCase(unittest.TestCase):
    """Every renderer must read a body the same way.

    This is the drift the whole project is about, in miniature. If the
    site decided a line was a paragraph while the DOCX decided it was a
    bullet, both would be self-consistent, both would look fine, and the
    handout in a teacher's hand would differ from the page on their phone
    with nothing to say so.
    """

    def test_all_renderers_share_one_function(self):
        self.assertIs(docx_render.blocks, blocks_mod.blocks)
        self.assertIs(pdf_render.blocks, blocks_mod.blocks)
        self.assertIs(site.blocks, blocks_mod.blocks)

    def test_the_parser_still_classifies_what_the_standard_names(self):
        body = ("A paragraph.\n\n"
                "- a bullet\n- another\n\n"
                "> quoted scripture\n\n"
                "### a subhead\n\n"
                "---")
        self.assertEqual(
            [kind for kind, _ in blocks_mod.blocks(body)],
            ["body", "bullet", "bullet", "scripture", "subhead", "rule"])

    def test_a_soft_wrap_is_not_a_line_break(self):
        """The bug this test was written for.

        A newline inside a Markdown paragraph is a soft wrap. reportlab
        collapses it inside a Paragraph and a newline inside a Word run is
        not a break either, so both printed handouts set the paragraph as
        flowing prose. The site emitted <br> and broke the line where the
        author's editor happened to wrap, which is the same approved
        sentence laid out two ways.
        """
        html = "\n".join(site._render_body(
            "Jesus was twelve. His parents lost Him for three days\n"
            "and found Him in the temple."))
        self.assertNotIn("<br", html)
        self.assertIn("for three days and found Him", html)

    def test_emphasis_survives_a_soft_wrap(self):
        html = "\n".join(site._render_body("A **bold phrase\nacross a wrap** here."))
        self.assertIn("<strong>bold phrase across a wrap</strong>", html)

    def test_the_site_sets_the_same_words_the_print_renderers_set(self):
        """Compare against the block text itself, not against a fixture.

        Every renderer is handed the same (kind, text) pairs. Whatever the
        site does to that text, the words and their order must come out
        the way the print renderers lay them out: soft wraps collapsed to
        single spaces, nothing dropped and nothing added.
        """
        tmp = Path(tempfile.mkdtemp(prefix="stpaul-site-"))
        try:
            content, digest = build_lesson(tmp)
            lesson = load_lesson(SLUG, content_dir=content)
            for piece in lesson.pieces:
                html = site.render_piece(lesson, piece, digest)
                plain = re.sub(r"<[^>]+>", "", html)
                plain = re.sub(r"\s+", " ", unescape(plain))
                for section in piece.sections:
                    for kind, text in blocks_mod.blocks(section.body):
                        if kind == "rule":
                            continue
                        # What reportlab and Word both make of this block.
                        want = re.sub(r"\s+", " ", re.sub(r"\*+", "", text)).strip()
                        self.assertIn(want, plain,
                                      f"the site does not set this block the way "
                                      f"the handouts do: {want!r}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_horizontal_rules_reach_no_renderer_output(self):
        """§6: no horizontal rules anywhere, including Markdown's."""
        html = "\n".join(site._render_body("A line.\n\n---\n\nAnother line."))
        self.assertNotIn("<hr", html)
        self.assertIn("A line.", html)
        self.assertIn("Another line.", html)


class DeterminismTestCase(unittest.TestCase):
    """No renderer may consult a clock, a network or a random source.

    CLAUDE.md states this as a rule. A rule enforced by remembering it is
    the exact failure this repository was built after, so it is enforced
    here instead: two builds of the same approved bytes produce the same
    files, and that is only true if nothing under render/ can vary.

    `brand.py` imports `datetime.date` legitimately, because which palette
    a piece uses is a function of the *lesson's* date. The calls below are
    what is forbidden, not the import.
    """

    FORBIDDEN = [
        (r"\.now\s*\(", "a wall clock"),
        (r"\.today\s*\(", "today's date"),
        (r"\btime\.time\s*\(", "a wall clock"),
        (r"\brandom\.", "a random source"),
        (r"\buuid\b", "a random source"),
        (r"\burllib\b", "the network"),
        (r"\brequests\b", "the network"),
        (r"\bsocket\b", "the network"),
        (r"\bsubprocess\b", "another program"),
    ]

    def test_no_renderer_reads_a_clock_a_network_or_a_random_source(self):
        for path in sorted(RENDER_DIR.glob("*.py")):
            src = path.read_text(encoding="utf-8")
            # Prose about the rule is not a violation of it.
            code = "\n".join(l for l in src.splitlines()
                             if not l.lstrip().startswith("#"))
            code = re.sub(r'""".*?"""', "", code, flags=re.S)
            for pattern, what in self.FORBIDDEN:
                self.assertIsNone(
                    re.search(pattern, code),
                    f"{path.name} reaches for {what}. Renderers run below the "
                    f"freeze line and must be a pure function of the approved "
                    f"bytes; build.py records the build time in "
                    f"BUILD-PROVENANCE.json, outside the rendered files.")

    def test_the_site_renderer_emits_no_script(self):
        """The pages carry no JavaScript, which is what lets the Worker's
        Content-Security-Policy forbid scripting outright.

        Checked inside real tags only. The fixture deliberately contains
        the text `<img src=x onerror=alert(1)>`, and finding that string
        in the output is the *correct* result: it means the escaping
        worked and a browser will print it rather than run it. What must
        not exist is an event handler in a tag this renderer emitted.
        """
        handler = re.compile(r"\son\w+\s*=", re.I)
        tmp = Path(tempfile.mkdtemp(prefix="stpaul-site-"))
        try:
            content, digest = build_lesson(tmp)
            lesson = load_lesson(SLUG, content_dir=content)
            for path in site.write(lesson, tmp / "dist", digest):
                if path.suffix != ".html":
                    continue
                html = path.read_text(encoding="utf-8")
                self.assertNotIn("<script", html.lower())

                # Content is escaped, so every surviving "<" opens a tag
                # this renderer wrote.
                for tag in re.findall(r"<[^>]*>", html):
                    self.assertIsNone(handler.search(tag),
                                      f"{path.name} emits an event handler: {tag}")
                    self.assertNotIn("javascript:", tag.lower())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class WorkerKeyTestCase(unittest.TestCase):
    """The Worker maps a URL path onto an R2 key, and nothing else.

    Run against the real file rather than a copy of the logic, because a
    copy is how two things that must agree stop agreeing.
    """

    def setUp(self):
        if not WORKER.is_file():
            self.skipTest("services/site/worker.js not in this checkout")
        if shutil.which("node") is None:
            self.skipTest("node is not available")

    def key_for(self, paths: list[str]) -> list[str | None]:
        script = f"""
        import {{ readFileSync }} from 'node:fs';
        const src = readFileSync({json.dumps(str(WORKER))}, 'utf8');
        const mod = await import(
          'data:text/javascript;base64,' +
          Buffer.from(src + '\\nexport {{ keyFor }};').toString('base64'));
        const out = {json.dumps(paths)}.map((p) => mod.keyFor(p));
        process.stdout.write(JSON.stringify(out));
        """
        res = subprocess.run([sys.executable and "node", "--input-type=module",
                              "-e", script],
                             capture_output=True, text=True)
        if res.returncode != 0:
            raise AssertionError(
                "could not evaluate keyFor out of worker.js. It must stay a "
                f"top-level `function keyFor`.\n{res.stderr}")
        return json.loads(res.stdout)

    def test_paths_map_onto_the_keys_publish_site_writes(self):
        got = self.key_for([
            "/", "/index.html",
            "/2026-01-04-test", "/2026-01-04-test/",
            "/2026-01-04-test/pieces/01-family-take-home.html",
            "/assets/site.css",
            "/handouts/2026-01-04-test/01-family-take-home.pdf",
        ])
        self.assertEqual(got, [
            "index.html", "index.html",
            "2026-01-04-test/index.html", "2026-01-04-test/index.html",
            "2026-01-04-test/pieces/01-family-take-home.html",
            "assets/site.css",
            "handouts/2026-01-04-test/01-family-take-home.pdf",
        ])

    def test_nothing_climbs_out_of_the_bucket(self):
        got = self.key_for([
            "/../secret", "/a/../../secret", "/%2e%2e/secret",
            "/%2E%2E%2Fsecret", "/a/./../../b",
        ])
        self.assertTrue(all(k is None for k in got),
                        f"a traversal produced a key: {got}")


class PublishGateTestCase(unittest.TestCase):
    """Publishing re-asks the two questions the build already asked.

    A BUILD-PROVENANCE.json is a record of what was true when the build
    ran, and publishing can happen much later. These are the cases where
    trusting that record would put the wrong words in front of the
    congregation.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="stpaul-publish-"))
        self.content, self.digest = build_lesson(self.tmp)
        self.approvals = self.tmp / "approvals"
        self.approvals.mkdir()
        self.dist = self.tmp / "dist"

        import publish_site
        self.publish_site = publish_site

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, *, approved=True, draft=False, source=None):
        out = self.dist / SLUG
        (out / "handouts").mkdir(parents=True, exist_ok=True)
        lesson = load_lesson(SLUG, content_dir=self.content)
        site.write(lesson, out, source or self.digest, draft=draft)
        (out / "BUILD-PROVENANCE.json").write_text(json.dumps({
            "sunday": SLUG,
            "source_sha256": source or self.digest,
            "approved": approved,
            "approval_status": "ok" if approved else "unapproved",
            "draft": draft,
        }), encoding="utf-8")

    def approve(self):
        review = approval.Review.new(reviewer="Bryan Wolfmueller", role="pastor",
                                     decision=approval.APPROVED,
                                     content_sha256=self.digest)
        approval.record_review(SLUG, review, content_dir=self.content,
                               approvals_dir=self.approvals,
                               standards_dir=FIXTURE_STANDARDS)

    def candidate(self):
        return self.publish_site.candidate(
            SLUG, self.dist, content_dir=self.content,
            approvals_dir=self.approvals, standards_dir=FIXTURE_STANDARDS)

    def test_an_approved_current_build_publishes(self):
        self.build()
        self.approve()
        self.assertEqual(self.candidate()["slug"], SLUG)

    def test_a_draft_is_never_published(self):
        self.build(draft=True)
        self.approve()
        with self.assertRaises(self.publish_site.Skipped) as e:
            self.candidate()
        self.assertIn("draft", str(e.exception))

    def test_an_unapproved_build_is_never_published(self):
        self.build(approved=False)
        with self.assertRaises(self.publish_site.Skipped):
            self.candidate()

    def test_a_stale_build_is_never_published(self):
        """Content moved after the build. The fix is to rebuild."""
        self.build()
        self.approve()
        (self.content / SLUG / "pieces" / "01-family-take-home.md").write_text(
            PIECE.replace("A retelling", "A different retelling"), encoding="utf-8")
        with self.assertRaises(self.publish_site.Skipped) as e:
            self.candidate()
        self.assertIn("changed", str(e.exception))

    def test_a_build_whose_approval_was_withdrawn_is_not_published(self):
        """The provenance still says approved. The approvals directory does not."""
        self.build()
        with self.assertRaises(self.publish_site.Skipped) as e:
            self.candidate()
        self.assertIn("approval", str(e.exception).lower())


if __name__ == "__main__":
    unittest.main()
