"""The ESV fetcher, minus the network.

What can go wrong here is not the HTTP call. It is the write: lesson.yml
is a heavily commented file whose comments record who decided what and
when, and a careless round-trip through PyYAML would silently delete all
of them. So the splice is text surgery, and these tests are what keep it
honest. The last test is the one that matters most: splice the real
Trinity 17 lesson and confirm the result still parses AND still carries
its comments.

Every fixture below is invented placeholder text. No Scripture is quoted
here, because this repository holds none and that is the only reason it
can be public.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

from fetch_scripture import (  # noqa: E402
    memory_verse_refs, read_lesson_field, splice_block, splice_memory_verses,
    verses_in,
)

SAMPLE = """\
# A comment that must survive.
sunday: 2026-09-27-trinity-17
gospel: "Luke 14:1-11"
translation: "ESV"

# Another load-bearing comment.
memory_verses:
  pre_k:
    - reference: "Luke 14:10"
      text: null
  primary:
    - reference: "Luke 14:10"
      text: null
  high_school:
    - reference: "Luke 14:11"
      text: null

# The comment above gospel_text.
gospel_text: null

law_and_gospel:
  law: null
"""


class SpliceBlockTestCase(unittest.TestCase):

    def test_it_replaces_a_null_with_a_literal_block(self):
        out = splice_block(SAMPLE, "gospel_text", "[1] FIRST VERSE OF THE PASSAGE")
        self.assertIn("gospel_text: |\n  [1] FIRST VERSE OF THE PASSAGE\n", out)
        self.assertEqual(yaml.safe_load(out)["gospel_text"].strip(),
                         "[1] FIRST VERSE OF THE PASSAGE")

    def test_it_keeps_every_comment_and_every_other_key(self):
        out = splice_block(SAMPLE, "gospel_text", "text")
        for comment in ("# A comment that must survive.",
                        "# Another load-bearing comment.",
                        "# The comment above gospel_text."):
            self.assertIn(comment, out)
        self.assertIn("law_and_gospel:", out)
        self.assertIn("  law: null", out)

    def test_it_handles_a_multi_line_passage(self):
        passage = "[1] FIRST VERSE.\n\n[7] SEVENTH VERSE."
        out = splice_block(SAMPLE, "gospel_text", passage)
        self.assertEqual(yaml.safe_load(out)["gospel_text"].strip(), passage)

    def test_a_second_fetch_replaces_the_first(self):
        once = splice_block(SAMPLE, "gospel_text", "first text")
        twice = splice_block(once, "gospel_text", "second text")
        self.assertEqual(yaml.safe_load(twice)["gospel_text"].strip(), "second text")
        self.assertNotIn("first text", twice)
        self.assertIn("law_and_gospel:", twice)

    def test_a_missing_key_is_an_error_not_a_silent_no_op(self):
        with self.assertRaises(Exception):
            splice_block(SAMPLE, "no_such_key", "text")


class MemoryVerseTestCase(unittest.TestCase):

    def test_it_finds_each_reference_once(self):
        self.assertEqual(memory_verse_refs(SAMPLE), ["Luke 14:10", "Luke 14:11"])

    def test_it_fills_every_matching_reference(self):
        out, filled = splice_memory_verses(
            SAMPLE, {"Luke 14:10": "TENTH VERSE TEXT.",
                     "Luke 14:11": "ELEVENTH VERSE TEXT."})
        self.assertEqual(filled, 3)
        loaded = yaml.safe_load(out)["memory_verses"]
        self.assertEqual(loaded["pre_k"][0]["text"], "TENTH VERSE TEXT.")
        self.assertEqual(loaded["primary"][0]["text"], "TENTH VERSE TEXT.")
        self.assertEqual(loaded["high_school"][0]["text"],
                         "ELEVENTH VERSE TEXT.")

    def test_a_reference_we_did_not_fetch_is_left_null(self):
        out, filled = splice_memory_verses(SAMPLE, {"Luke 14:10": "TENTH VERSE TEXT."})
        self.assertEqual(filled, 2)
        self.assertIsNone(yaml.safe_load(out)["memory_verses"]["high_school"][0]["text"])

    def test_filling_nothing_reports_nothing(self):
        out, filled = splice_memory_verses(SAMPLE, {})
        self.assertEqual(filled, 0)
        self.assertEqual(out.strip(), SAMPLE.strip())


class FieldReadingTestCase(unittest.TestCase):

    def test_it_reads_a_quoted_scalar(self):
        self.assertEqual(read_lesson_field(SAMPLE, "gospel"), "Luke 14:1-11")
        self.assertEqual(read_lesson_field(SAMPLE, "translation"), "ESV")

    def test_null_reads_as_absent(self):
        self.assertIsNone(read_lesson_field(SAMPLE, "gospel_text"))

    def test_a_missing_key_reads_as_absent(self):
        self.assertIsNone(read_lesson_field(SAMPLE, "nope"))


class VerseCountTestCase(unittest.TestCase):

    def test_it_counts_a_simple_range(self):
        self.assertEqual(verses_in("Luke 14:1-11"), 11)
        self.assertEqual(verses_in("Luke 14:1–11"), 11)

    def test_a_single_verse_counts_as_one(self):
        self.assertEqual(verses_in("Mark 2:27"), 1)

    def test_a_whole_book_is_large_enough_to_refuse(self):
        self.assertGreater(verses_in("John 1:1-21:25"), 50)


class RealLessonTestCase(unittest.TestCase):
    """The splice, run against the actual Trinity 17 file."""

    def setUp(self):
        from stpaul.model import CONTENT_DIR
        self.path = CONTENT_DIR / "2026-09-27-trinity-17" / "lesson.yml"
        if not self.path.is_file():
            self.skipTest("Trinity 17 is not in this checkout's data root")
        self.source = self.path.read_text(encoding="utf-8")

    def test_the_spliced_file_still_parses_and_keeps_its_notes(self):
        passage = "[1] FIRST VERSE.\n\n[7] SEVENTH VERSE."
        out = splice_block(self.source, "gospel_text", passage)
        out, filled = splice_memory_verses(
            out, {"Luke 14:10": "TENTH VERSE TEXT.",
                  "Luke 14:11": "ELEVENTH VERSE TEXT."})

        before, after = yaml.safe_load(self.source), yaml.safe_load(out)
        self.assertEqual(after["gospel_text"].strip(), passage)
        self.assertEqual(filled, 5)

        # Nothing else moved.
        for key in ("title", "theme", "catechism_link", "hymn", "unit",
                    "production_notes", "needs_input", "copyright"):
            self.assertEqual(before[key], after[key], f"{key} changed")

        # And the comments are still there.
        self.assertEqual(self.source.count("#"), out.count("#"))

    def test_it_does_not_write_during_the_test(self):
        self.assertEqual(self.path.read_text(encoding="utf-8"), self.source)


if __name__ == "__main__":
    unittest.main()
