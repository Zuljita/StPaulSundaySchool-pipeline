"""The ESV fetcher, with Crossway replaced by a stand-in.

The HTTP call is not what goes wrong. The write is: lesson.yml is a heavily
commented file, and its comments record who decided what and when. The
fetcher edits it in place, and every write is checked at run time to read
back as the old file with exactly the new passages in it. These tests hold
the splice and that check to each other, over every shape of value a
lesson.yml can take.

Several are named for bugs the first version of the fetcher had: a second
run that wrote a verse into an unrelated key, a multi-line verse that broke
the file, and a re-fetch that kept an old paragraph.

Every passage below is invented placeholder text. No Scripture is quoted:
this repository holds none, and that is the only reason it can be public.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import fetch_scripture as fs  # noqa: E402
from stpaul import approval  # noqa: E402
from stpaul.scripture import lesson_passages, parse_exact_reference  # noqa: E402

SLUG = "2026-01-04-test"

LESSON = """\
# A comment that must survive.
sunday: 2026-01-04-test
gospel: "Luke 1:1-4"
# Another load-bearing comment.
translation: "ESV"

memory_verses:
  pre_k:
    - reference: "Luke 1:3"
      text: null
  primary:
    - reference: "Luke 1:3"
      text: null  # a comment on the value itself
  high_school:
    - reference: "Luke 1:4"
      text: null

cross_references:
  - reference: "Acts 1:1-2"
    text: null

# The comment above gospel_text.
gospel_text: null

hymn:
  number: 1
  text: null

law_and_gospel:
  law: null
"""

# What Crossway sends back, in the shape it sends it: bracketed verse
# numbers, a blank line between paragraphs, trailing breaks.
REPLIES = {
    "Luke 1:1-4": ("[1] ALPHA BETA GAMMA. [2] DELTA EPSILON ZETA.\n\n"
                   "[3] ETA THETA, IOTA KAPPA LAMBDA. [4] MU NU XI.\n\n"),
    "Luke 1:3": "[3] ETA THETA, IOTA KAPPA LAMBDA.\n\n",
    "Luke 1:4": "[4] MU NU XI.\n\n",
    "Acts 1:1-2": "[1] OMICRON PI RHO,\n[2] SIGMA TAU UPSILON.\n\n",
}

# What lesson.yml should hold afterwards.
STORED = {
    "Luke 1:1-4": ("1 ALPHA BETA GAMMA. 2 DELTA EPSILON ZETA.\n\n"
                   "3 ETA THETA, IOTA KAPPA LAMBDA. 4 MU NU XI."),
    "Luke 1:3": "ETA THETA, IOTA KAPPA LAMBDA.",
    "Luke 1:4": "MU NU XI.",
    "Acts 1:1-2": "1 OMICRON PI RHO,\n2 SIGMA TAU UPSILON.",
}


class FakeCrossway:
    def __init__(self, replies=None, failing=()):
        self.replies = dict(REPLIES if replies is None else replies)
        self.failing = set(failing)
        self.calls: list[str] = []

    def __call__(self, reference: str) -> str:
        self.calls.append(reference)
        if reference in self.failing:
            raise fs.FetchError("api.esv.org answered 500 Internal Server Error.")
        return self.replies[reference]


class ShapeTestCase(unittest.TestCase):

    def ref(self, text):
        return parse_exact_reference(text)

    def test_a_passage_keeps_bare_verse_numbers_and_its_paragraphs(self):
        self.assertEqual(fs.shape(REPLIES["Luke 1:1-4"], self.ref("Luke 1:1-4")),
                         (STORED["Luke 1:1-4"], 4))

    def test_a_single_verse_carries_no_number(self):
        self.assertEqual(fs.shape(REPLIES["Luke 1:3"], self.ref("Luke 1:3")),
                         (STORED["Luke 1:3"], 1))

    def test_line_breaks_inside_a_paragraph_survive(self):
        self.assertEqual(fs.shape(REPLIES["Acts 1:1-2"], self.ref("Acts 1:1-2"))[0],
                         STORED["Acts 1:1-2"])

    def test_stray_spacing_is_tidied(self):
        text, _ = fs.shape("  [1]  ALPHA   BETA  \n\n\n\n[2] GAMMA\t \n", self.ref("Luke 1:1-2"))
        self.assertEqual(text, "1 ALPHA BETA\n\n2 GAMMA")

    def test_the_wrong_number_of_verses_is_refused(self):
        with self.assertRaises(fs.FetchError):
            fs.check_length("Luke 1:1-4", self.ref("Luke 1:1-4"), 3, 50)

    def test_a_reply_without_verse_numbers_is_refused(self):
        with self.assertRaises(fs.FetchError):
            fs.check_length("Luke 1:3", self.ref("Luke 1:3"), 0, 50)

    def test_an_oversized_passage_is_refused(self):
        with self.assertRaises(fs.FetchError):
            fs.check_length("Luke 1:1-80", self.ref("Luke 1:1-80"), 80, 50)


class ProcessTestCase(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="stpaul-fetch-"))
        self.content = self.tmp / "content"
        self.approvals = self.tmp / "approvals"
        (self.content / SLUG).mkdir(parents=True)
        self.approvals.mkdir()
        self.write(LESSON)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, text):
        (self.content / SLUG / "lesson.yml").write_text(text, encoding="utf-8")

    def run_fetch(self, fetch=None, **kwargs):
        fetch = fetch if fetch is not None else FakeCrossway()
        result = fs.process(SLUG, fetch, content_dir=self.content,
                            approvals_dir=self.approvals, **kwargs)
        return result, fetch

    def record(self, *decisions):
        reviews = [{"reviewer": "A Reviewer", "role": "pastor", "decision": d,
                    "at": "2026-01-01T00:00:00+00:00", "content_sha256": "0" * 64}
                   for d in decisions]
        (self.approvals / f"{SLUG}.approval.json").write_text(
            json.dumps({"sunday": SLUG, "reviews": reviews}), encoding="utf-8")

    def statuses(self, result):
        return {l.name: l.status for l in result.lines}

    # -- filling ----------------------------------------------------------

    def test_every_declared_passage_is_filled(self):
        result, _ = self.run_fetch()
        self.assertFalse(result.failed, fs.report(result))
        self.assertEqual(set(self.statuses(result).values()), {"filled"})
        data = yaml.safe_load(result.new_source)
        self.assertEqual(data["gospel_text"], STORED["Luke 1:1-4"])
        self.assertEqual(data["memory_verses"]["pre_k"][0]["text"], STORED["Luke 1:3"])
        self.assertEqual(data["memory_verses"]["primary"][0]["text"], STORED["Luke 1:3"])
        self.assertEqual(data["memory_verses"]["high_school"][0]["text"], STORED["Luke 1:4"])
        self.assertEqual(data["cross_references"][0]["text"], STORED["Acts 1:1-2"])

    def test_nothing_else_moves(self):
        result, _ = self.run_fetch()
        before, after = yaml.safe_load(LESSON), yaml.safe_load(result.new_source)
        for key in ("sunday", "gospel", "translation", "hymn", "law_and_gospel"):
            self.assertEqual(before[key], after[key], key)

    def test_every_comment_survives(self):
        result, _ = self.run_fetch()
        for comment in ("# A comment that must survive.", "# Another load-bearing comment.",
                        "# The comment above gospel_text.", "# a comment on the value itself"):
            self.assertIn(comment, result.new_source)

    def test_it_writes_nothing_itself(self):
        self.run_fetch()
        self.assertEqual((self.content / SLUG / "lesson.yml").read_text(encoding="utf-8"), LESSON)

    def test_a_second_run_changes_nothing(self):
        """The misfiling bug: a second run once wrote a verse into hymn.text."""
        first, _ = self.run_fetch()
        self.write(first.new_source)
        second, _ = self.run_fetch()
        self.assertFalse(second.failed, fs.report(second))
        self.assertEqual(set(self.statuses(second).values()), {"kept"})
        self.assertIsNone(second.new_source)

    def test_a_multi_line_memory_verse_is_written_as_a_block(self):
        """The parse-breaking bug: a verse's second line once landed at column 0."""
        self.write(LESSON.replace('reference: "Luke 1:4"', 'reference: "Acts 1:1-2"'))
        result, _ = self.run_fetch()
        data = yaml.safe_load(result.new_source)
        self.assertEqual(data["memory_verses"]["high_school"][0]["text"], STORED["Acts 1:1-2"])

    # -- what is kept and what is replaced ---------------------------------

    def test_a_memory_verse_trimmed_to_a_phrase_is_kept(self):
        self.write(LESSON.replace('text: null\n  primary', 'text: "IOTA KAPPA LAMBDA"\n  primary'))
        result, _ = self.run_fetch()
        self.assertEqual(self.statuses(result)["memory_verses.pre_k[0]"], "kept")
        self.assertEqual(
            yaml.safe_load(result.new_source)["memory_verses"]["pre_k"][0]["text"],
            "IOTA KAPPA LAMBDA")

    def test_a_changed_word_is_replaced_with_the_publishers(self):
        self.write(LESSON.replace('text: null\n  primary', 'text: "IOTA KAPPA OMEGA"\n  primary'))
        result, _ = self.run_fetch()
        self.assertEqual(self.statuses(result)["memory_verses.pre_k[0]"], "replaced")
        self.assertEqual(
            yaml.safe_load(result.new_source)["memory_verses"]["pre_k"][0]["text"],
            STORED["Luke 1:3"])

    def test_the_gospel_in_another_layout_is_kept(self):
        wrapped = ("gospel_text: |\n  [1] ALPHA BETA\n  GAMMA. [2] DELTA EPSILON ZETA. [3] ETA\n"
                   "  THETA, IOTA KAPPA LAMBDA. [4] MU NU XI.\n")
        self.write(LESSON.replace("gospel_text: null\n", wrapped))
        result, _ = self.run_fetch()
        self.assertEqual(self.statuses(result)["gospel_text"], "kept")
        self.assertIn(wrapped, result.new_source)

    def test_a_gospel_missing_a_verse_is_replaced(self):
        self.write(LESSON.replace("gospel_text: null",
                                  'gospel_text: "ALPHA BETA GAMMA. MU NU XI."'))
        result, _ = self.run_fetch()
        self.assertEqual(self.statuses(result)["gospel_text"], "replaced")

    # -- refusals ----------------------------------------------------------

    def test_an_approved_sunday_is_not_touched(self):
        self.record(approval.APPROVED)
        result, fetch = self.run_fetch()
        self.assertEqual(result.outcome, "skipped")
        self.assertEqual(fetch.calls, [])
        self.assertIsNone(result.new_source)

    def test_an_approval_that_went_stale_still_freezes_it(self):
        """Stale or not, a pastor signed for those words once."""
        self.record(approval.APPROVED, approval.CHANGES_REQUESTED)
        self.assertEqual(self.run_fetch()[0].outcome, "skipped")

    def test_changes_requested_alone_does_not_freeze_it(self):
        """Asking for changes is when a passage most needs fetching again."""
        self.record(approval.CHANGES_REQUESTED)
        self.assertEqual(self.run_fetch()[0].outcome, "checked")

    def test_another_translation_is_not_fetched(self):
        """Including the inline-comment form the first version read as no translation."""
        for line in ('translation: "NKJV"', "translation: NKJV  # per the schedule",
                     "translation: null"):
            with self.subTest(line=line):
                self.write(LESSON.replace('translation: "ESV"', line))
                result, fetch = self.run_fetch()
                self.assertEqual(result.outcome, "skipped")
                self.assertEqual(fetch.calls, [])

    def test_a_loose_reference_is_refused_and_the_rest_still_filled(self):
        self.write(LESSON.replace('gospel: "Luke 1:1-4"', 'gospel: "Luke 1"'))
        result, fetch = self.run_fetch()
        self.assertTrue(result.failed)
        self.assertEqual(self.statuses(result)["gospel_text"], "failed")
        self.assertNotIn("Luke 1", fetch.calls)
        self.assertEqual(self.statuses(result)["memory_verses.pre_k[0]"], "filled")

    def test_a_reference_with_no_text_key_is_reported(self):
        self.write(LESSON.replace('    - reference: "Luke 1:4"\n      text: null\n',
                                  '    - reference: "Luke 1:4"\n'))
        result, _ = self.run_fetch()
        self.assertEqual(self.statuses(result)["memory_verses.high_school[0]"], "failed")

    def test_a_failed_fetch_is_reported_for_that_passage(self):
        result, _ = self.run_fetch(FakeCrossway(failing={"Acts 1:1-2"}))
        self.assertEqual(self.statuses(result)["cross_references[0]"], "failed")
        self.assertIsNone(yaml.safe_load(result.new_source)["cross_references"][0]["text"])

    def test_no_key_fails_the_sunday_once(self):
        result, _ = self.run_fetch(fs.Crossway(None))
        self.assertTrue(result.failed)
        self.assertEqual(result.lines, [])
        self.assertIn("ESV_API_KEY", result.note)

    def test_a_file_that_does_not_parse_is_reported_without_its_contents(self):
        self.write('gospel: "Luke 1:1-4"\ngospel_text: "PLACEHOLDER SENTENCE\n  : [\n')
        result, _ = self.run_fetch()
        self.assertTrue(result.failed)
        self.assertNotIn("PLACEHOLDER", result.note)

    def test_a_missing_gospel_text_key_is_added(self):
        self.write(LESSON.replace("# The comment above gospel_text.\ngospel_text: null\n", ""))
        result, _ = self.run_fetch()
        self.assertEqual(yaml.safe_load(result.new_source)["gospel_text"], STORED["Luke 1:1-4"])

    # -- output ------------------------------------------------------------

    def test_the_report_never_prints_the_text_unless_asked(self):
        result, _ = self.run_fetch()
        self.assertNotIn("ALPHA", fs.report(result))
        self.assertNotIn("ALPHA", fs.summary([result], write=True))
        self.assertIn("ALPHA", fs.report(result, show=True))


class SpliceTestCase(unittest.TestCase):
    """Every shape of value, put in place and read back."""

    TEXT = "1 FIRST PLACEHOLDER LINE.\n\n2 SECOND PLACEHOLDER LINE."

    def splice(self, source, name="gospel_text", text=None):
        text = self.TEXT if text is None else text
        out = fs.apply(source, {name: text})
        fs.verify_rewrite(source, out, {name: text})
        return out

    def test_a_null_becomes_a_literal_block(self):
        self.assertEqual(
            self.splice("a: 1\ngospel_text: null\n\nb: 2\n"),
            "a: 1\ngospel_text: |-\n  1 FIRST PLACEHOLDER LINE.\n\n"
            "  2 SECOND PLACEHOLDER LINE.\n\nb: 2\n")

    def test_an_inline_comment_moves_beside_the_indicator(self):
        out = self.splice("gospel_text: null  # filled by the runner\nb: 2\n")
        self.assertTrue(out.startswith("gospel_text: |-  # filled by the runner\n"))

    # The old text is STALE rather than OLD, because PLACEHOLDER has OLD in it.

    def test_an_existing_block_is_replaced_and_its_spacing_kept(self):
        out = self.splice("gospel_text: |\n  STALE ONE.\n  STALE TWO.\n\nb: 2\n")
        self.assertTrue(out.endswith("SECOND PLACEHOLDER LINE.\n\nb: 2\n"))
        self.assertNotIn("STALE", out)

    def test_a_block_header_comment_survives(self):
        self.assertIn("# note", self.splice("gospel_text: |-  # note\n  STALE.\nb: 2\n"))

    def test_a_block_with_two_blank_lines_is_replaced_whole(self):
        """The stale-text bug: an old second paragraph once survived a re-fetch."""
        self.assertNotIn("STALE",
                         self.splice("gospel_text: |\n  STALE ONE.\n\n\n  STALE TWO.\nb: 2\n"))

    def test_a_folded_block_at_the_end_of_the_file(self):
        self.assertNotIn("STALE", self.splice("b: 2\ngospel_text: >-\n  STALE\n  TEXT"))

    def test_an_empty_value(self):
        self.splice("gospel_text:\nb: 2\n")

    def test_a_quoted_value_over_two_lines(self):
        self.splice('gospel_text: "STALE\n  TEXT"\nb: 2\n')

    def test_an_item_whose_text_comes_before_its_reference(self):
        source = ("memory_verses:\n  primary:\n    - text: >-\n        STALE WORDS\n"
                  "      reference: \"Luke 1:2\"\n\nnext: 1\n")
        out = self.splice(source, "memory_verses.primary[0]")
        self.assertEqual(yaml.safe_load(out)["memory_verses"]["primary"][0]["reference"],
                         "Luke 1:2")

    def test_a_flow_style_item_gets_a_quoted_string(self):
        out = self.splice('cross_references:\n  - {reference: "Acts 1:1", text: null}\n',
                          "cross_references[0]")
        self.assertIn('text: "1 FIRST PLACEHOLDER LINE.\\n\\n2 SECOND PLACEHOLDER LINE."', out)

    def test_a_level_holding_one_verse_instead_of_a_list(self):
        self.splice('memory_verses:\n  pre_k:\n    reference: "Luke 1:2"\n    text: null\n',
                    "memory_verses.pre_k[0]")

    def test_the_check_catches_a_lost_comment(self):
        with self.assertRaises(fs.SpliceError):
            fs.verify_rewrite("# keep me\ngospel_text: null\n", "gospel_text: TEXT\n",
                              {"gospel_text": "TEXT"})

    def test_the_check_catches_another_key_changing(self):
        with self.assertRaises(fs.SpliceError):
            fs.verify_rewrite("a: 1\ngospel_text: null\n", "a: 2\ngospel_text: TEXT\n",
                              {"gospel_text": "TEXT"})

    def test_the_check_catches_text_that_reads_back_differently(self):
        with self.assertRaises(fs.SpliceError):
            fs.verify_rewrite("gospel_text: null\nb: 2\n", "gospel_text: |-\n  TEXT\n  b: 2\n",
                              {"gospel_text": "TEXT"})


class RealLessonsTestCase(unittest.TestCase):
    """The splice over every lesson.yml in the data root, in memory only.

    Skipped without a data checkout, which is how CI runs. With one, every
    declared passage is filled with placeholder text, and the result has to
    read back exactly, keep every comment, and come out the same on a
    second pass. It asserts nothing about what a lesson currently holds, so
    fetching real text into a lesson does not break it.
    """

    def test_every_lesson_splices_cleanly(self):
        from stpaul.model import CONTENT_DIR, all_sundays
        slugs = all_sundays(CONTENT_DIR)
        if not slugs:
            self.skipTest("no data checkout")
        for slug in slugs:
            with self.subTest(slug=slug):
                path = CONTENT_DIR / slug / "lesson.yml"
                source = path.read_text(encoding="utf-8")
                slots = fs.locate(source)
                texts = {p.field: f"PLACEHOLDER FOR {p.field}.\n\nA SECOND PLACEHOLDER PARAGRAPH."
                         for p in lesson_passages(yaml.safe_load(source) or {})
                         if p.field == "gospel_text" or p.field in slots}
                if not texts:
                    continue
                out = fs.apply(source, texts)
                fs.verify_rewrite(source, out, texts)
                self.assertEqual(fs.apply(out, texts), out)
                self.assertEqual(path.read_text(encoding="utf-8"), source)


if __name__ == "__main__":
    unittest.main()
