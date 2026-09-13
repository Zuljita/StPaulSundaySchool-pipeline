"""Bible references, word comparison, and the quotation rule.

The rule is the gate Trinity 17 lacked: an imported draft carried two
wordings of one phrase in Luke 14:10, neither the ESV's, and nothing
compared them with anything. These tests hold it to catching a changed
word while leaving typography, trimming and quotations of other things
alone.

Every passage here is invented placeholder text. References use real book
names because the parser has to know them, but no verse of any translation
is quoted: this repository holds none, and that is why it can be public.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stpaul.model import load_lesson  # noqa: E402
from stpaul.rules import check_lesson, check_scripture_quotations  # noqa: E402
from stpaul.scripture import (covering, find_references, is_excerpt,  # noqa: E402
                              lesson_passages, parse_exact_reference, parse_reference,
                              words)

SLUG = "2026-01-04-test"


class ReferenceTestCase(unittest.TestCase):

    def test_a_range_within_a_chapter(self):
        ref = parse_exact_reference("Luke 14:1-11")
        self.assertEqual((ref.book, ref.start, ref.end), ("luke", (14, 1), (14, 11)))
        self.assertEqual(ref.verse_count, 11)
        self.assertEqual(str(ref), "Luke 14:1-11")

    def test_dashes_and_partial_verses(self):
        self.assertEqual(parse_exact_reference("Luke 14:1–11"),
                         parse_exact_reference("Luke 14:1-11"))
        self.assertTrue(parse_exact_reference("Luke 14:10b").single_verse)

    def test_numbered_and_multi_word_books(self):
        self.assertEqual(parse_exact_reference("1 Corinthians 15:26").book, "1 corinthians")
        self.assertEqual(parse_exact_reference("Song of Solomon 2:1").book, "song of solomon")
        self.assertEqual(parse_exact_reference("Psalm 23:1-6").book, "psalms")

    def test_a_range_across_chapters_has_no_count(self):
        ref = parse_exact_reference("Luke 14:25-15:3")
        self.assertIsNone(ref.verse_count)
        self.assertEqual(ref.end, (15, 3))

    def test_what_is_not_one_passage(self):
        """The loose references the first fetcher counted as a single verse."""
        for loose in ("John", "Psalm 119", "Luke 14", "Isaiah 40-66", "Luke 14:1-6, 7-11",
                      "Luke 14:11-3", "Hezekiah 1:1", "See John 3:16"):
            with self.subTest(loose=loose):
                self.assertIsNone(parse_exact_reference(loose))

    def test_references_inside_prose(self):
        found = find_references("Write it beside Luke 14:11 and see John 3:16 too.")
        self.assertEqual([str(r) for r, _, _ in found], ["Luke 14:11", "John 3:16"])
        self.assertEqual(str(parse_reference("Read On: Acts 1:1-2")), "Acts 1:1-2")

    def test_coverage(self):
        whole = parse_exact_reference("Luke 14:1-11")
        self.assertTrue(whole.covers(parse_exact_reference("Luke 14:10")))
        self.assertFalse(whole.covers(parse_exact_reference("Luke 14:12")))
        self.assertFalse(whole.covers(parse_exact_reference("Mark 14:10")))


class WordsTestCase(unittest.TestCase):
    PASSAGE = "1 ALPHA BETA GAMMA. 2 DELTA, EPSILON ZETA ETA.\n\n3 THETA IOTA."

    def test_typography_is_not_words(self):
        self.assertEqual(words("“ALPHA,” **beta** _gamma_ delta."),
                         words('"alpha beta gamma delta"'))

    def test_verse_numbers_are_not_words(self):
        self.assertEqual(words("[3] ONE TWO 4 THREE"), ["one", "two", "three"])

    def test_apostrophes_are_one_kind(self):
        self.assertEqual(words("ALPHA’S BETA"), words("alpha's beta"))

    def test_a_trimmed_phrase_is_an_excerpt(self):
        self.assertTrue(is_excerpt("epsilon zeta", self.PASSAGE))

    def test_across_a_verse_number_and_a_paragraph(self):
        self.assertTrue(is_excerpt("zeta eta theta", self.PASSAGE))

    def test_an_ellipsis_stands_for_words_left_out(self):
        self.assertTrue(is_excerpt("alpha beta ... eta", self.PASSAGE))
        self.assertTrue(is_excerpt("alpha beta … eta", self.PASSAGE))

    def test_an_ellipsis_does_not_permit_reordering(self):
        self.assertFalse(is_excerpt("eta ... alpha", self.PASSAGE))

    def test_a_changed_word_is_not_an_excerpt(self):
        self.assertFalse(is_excerpt("delta, epsilon theta", self.PASSAGE))

    def test_an_added_word_is_not_an_excerpt(self):
        self.assertFalse(is_excerpt("alpha beta and gamma", self.PASSAGE))

    def test_nothing_is_not_an_excerpt(self):
        self.assertFalse(is_excerpt("...", self.PASSAGE))

    def test_one_changed_word_mid_paragraph_still_resembles_the_passage(self):
        """Measuring only the longest run once missed exactly this."""
        from stpaul.scripture import overlap
        passage = ("ALPHA BETA GAMMA DELTA EPSILON ZETA ETA THETA IOTA KAPPA "
                   "LAMBDA MU NU XI OMICRON PI RHO SIGMA TAU UPSILON.")
        self.assertGreater(overlap(passage.replace("KAPPA", "OMEGA"), passage), 0.9)

    def test_unrelated_prose_does_not_resemble_the_passage(self):
        from stpaul.scripture import overlap
        self.assertEqual(overlap("Circle every word in the story that names a place.",
                                 self.PASSAGE), 0.0)


class LessonPassagesTestCase(unittest.TestCase):

    def test_every_declared_passage_in_file_order(self):
        meta = {
            "gospel": "Luke 1:1-4", "gospel_text": None,
            "memory_verses": {
                "pre_k": [{"reference": "Luke 1:3", "text": "ALPHA"}],
                "primary": {"reference": "Luke 1:4", "text": ""},
                "intermediate": None,
            },
            "cross_references": [{"reference": "Acts 1:1-2", "text": None}],
        }
        self.assertEqual(
            [(p.field, p.reference, p.text) for p in lesson_passages(meta)],
            [("gospel_text", "Luke 1:1-4", None),
             ("memory_verses.pre_k[0]", "Luke 1:3", "ALPHA"),
             ("memory_verses.primary[0]", "Luke 1:4", None),
             ("cross_references[0]", "Acts 1:1-2", None)])

    def test_a_loose_reference_is_kept_but_not_parsed(self):
        (passage,) = lesson_passages({"gospel": "Luke 14"})
        self.assertIsNone(passage.ref)

    def test_covering_finds_the_passages_containing_a_verse(self):
        passages = lesson_passages({
            "gospel": "Luke 1:1-4",
            "memory_verses": {"pre_k": [{"reference": "Luke 1:3"}]},
        })
        self.assertEqual([p.field for p in covering(passages, parse_exact_reference("Luke 1:3"))],
                         ["gospel_text", "memory_verses.pre_k[0]"])


LESSON = """\
sunday: 2026-01-04-test
date: 2026-01-04
liturgical_day: "Test Sunday"
status: draft
gospel: "Luke 1:1-4"
translation: {translation}
memory_verses:
  primary:
    - reference: "Luke 1:3"
      text: "NU XI OMICRON PI RHO SIGMA TAU."
cross_references:
  - reference: "Acts 1:1-2"
    text: {cross}
gospel_text: {gospel}
"""

GOSPEL = """|-
  1 ALPHA BETA GAMMA DELTA. 2 EPSILON ZETA ETA THETA.

  3 NU XI OMICRON PI RHO SIGMA TAU. 4 UPSILON PHI CHI PSI."""

CROSS = "|-\n      1 AAA BBB CCC DDD.\n      2 EEE FFF GGG HHH."

PIECE = """\
---
piece: primary-student-handout
type: student_handout
level: primary
order: 6
---

# Student Handout

## The Text

{text}

## Memory Work

{memory}

## Talk About It

{talk}
{extra}"""

TEXT = ("1 ALPHA BETA GAMMA DELTA. 2 EPSILON ZETA ETA THETA. "
        "3 NU XI OMICRON PI RHO SIGMA TAU. 4 UPSILON PHI CHI PSI. (ESV)")
MEMORY = '"NU XI OMICRON PI RHO SIGMA TAU." (Luke 1:3 ESV)'
TALK = "What happened first?"

RULES = {
    "scripture_quotations": {
        "severity": "error",
        "source": "test fixture",
        "translations": ["ESV"],
        "whole_sections": ["The Text", "Read On"],
        "quoted_sections": ["Memory Work", "Memory Work & Hymn", "The Verse to Say This Week"],
        "min_words": 4,
        "near_miss": 0.6,
    }
}


class QuotationRuleTestCase(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="stpaul-quotes-"))
        self.content = self.tmp / "content"
        (self.content / SLUG / "pieces").mkdir(parents=True)
        self.piece = self.content / SLUG / "pieces" / "06-primary-student-handout.md"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def lesson(self, *, translation="ESV", gospel=GOSPEL, cross="null",
               text=TEXT, memory=MEMORY, talk=TALK, extra=""):
        (self.content / SLUG / "lesson.yml").write_text(
            LESSON.format(translation=translation, gospel=gospel, cross=cross),
            encoding="utf-8")
        self.piece.write_text(PIECE.format(text=text, memory=memory, talk=talk, extra=extra),
                              encoding="utf-8")
        return load_lesson(SLUG, content_dir=self.content)

    def findings(self, **kwargs):
        return check_scripture_quotations(RULES, self.lesson(**kwargs))

    def hit(self, **kwargs):
        return [f.rule for f in self.findings(**kwargs)]

    # -- what passes ---------------------------------------------------------

    def test_scripture_copied_from_lesson_yml_passes(self):
        self.assertEqual(self.hit(), [])

    def test_case_punctuation_and_emphasis_are_free(self):
        self.assertEqual(self.hit(
            text=("**1** alpha, beta; gamma delta. 2 EPSILON zeta eta theta.\n\n"
                  "3 nu xi omicron pi rho sigma tau. 4 upsilon phi chi psi."),
            memory="“*NU* xi omicron pi rho sigma tau” (Luke 1:3, ESV)"), [])

    def test_a_verse_trimmed_to_a_phrase_passes(self):
        self.assertEqual(self.hit(memory='"OMICRON PI RHO SIGMA" (Luke 1:3)'), [])

    def test_an_ellipsis_may_leave_words_out(self):
        self.assertEqual(self.hit(memory='"NU XI ... SIGMA TAU" (Luke 1:3)'), [])
        self.assertEqual(self.hit(memory='"NU XI … SIGMA TAU" (Luke 1:3)'), [])

    def test_a_citation_paragraph_is_not_read_as_scripture(self):
        self.assertEqual(self.hit(text="Luke 1:1-4 (ESV)\n\n" + TEXT), [])

    def test_an_instruction_under_the_text_is_left_alone(self):
        """A student handout can set an activity beside the passage.

        The approved Trinity 16 handout does, and the first version of this
        rule called it a misquotation.
        """
        activity = "Circle every word in the story that names a place."
        self.assertEqual(self.hit(text=TEXT + "\n\n" + activity), [])

    def test_nothing_to_check_against_is_one_finding_per_section(self):
        activity = "Circle every word in the story that names a place."
        self.assertEqual(self.hit(gospel="null", text=TEXT + "\n\n" + activity),
                         ["scripture-unverified"])

    def test_a_quotation_of_something_else_is_left_alone(self):
        self.assertEqual(self.hit(memory='Sing "A HYMN WITH A LONG TITLE" together.'), [])

    def test_a_short_quotation_is_not_judged(self):
        self.assertEqual(self.hit(memory='"NU XI OMEGA" (Luke 1:3)'), [])

    def test_an_uncited_quotation_outside_scripture_sections_is_left_alone(self):
        self.assertEqual(self.hit(talk='Say it: "NU XI OMICRON OMEGA".'), [])

    # -- what does not ---------------------------------------------------------

    def test_a_changed_word_in_the_text_is_a_mismatch(self):
        found = self.findings(text=TEXT.replace("ETA THETA", "ETA OMEGA"))
        self.assertEqual([f.rule for f in found], ["scripture-mismatch"])
        self.assertIn('then has "omega"', found[0].message)
        self.assertIn("Luke 1:1-4", found[0].message)

    def test_a_dropped_word_is_a_mismatch(self):
        self.assertEqual(self.hit(text=TEXT.replace("GAMMA DELTA", "DELTA")),
                         ["scripture-mismatch"])

    def test_the_text_with_nothing_fetched_is_unverified(self):
        self.assertEqual(self.hit(gospel="null"), ["scripture-unverified"])

    def test_a_citation_on_its_own_line_counts(self):
        self.assertEqual(self.hit(memory='"NU XI OMICRON PI RHO SIGMA TAU."\n\nLuke 1:3 (ESV)'),
                         [])
        self.assertEqual(self.hit(memory='"NU XI OMICRON PI RHO SIGMA OMEGA."\n\nLuke 1:3 (ESV)'),
                         ["scripture-mismatch"])

    def test_a_near_miss_without_a_citation_is_a_mismatch(self):
        self.assertEqual(self.hit(memory='"NU XI OMICRON PI RHO SIGMA OMEGA."'),
                         ["scripture-mismatch"])

    def test_quoting_an_undeclared_passage_is_unverified(self):
        found = self.findings(memory='"WORDS FROM SOMEWHERE ELSE ENTIRELY" (Mark 2:27)')
        self.assertEqual([f.rule for f in found], ["scripture-unverified"])
        self.assertIn("cross_references", found[0].message)

    def test_a_declared_passage_not_yet_fetched_is_unverified(self):
        self.assertEqual(self.hit(memory='"ANY WORDS AT ALL HERE" (Acts 1:1)'),
                         ["scripture-unverified"])

    def test_a_cited_quotation_is_checked_under_any_heading(self):
        self.assertEqual(self.hit(talk='Say it: "NU XI OMICRON OMEGA" (Luke 1:3).'),
                         ["scripture-mismatch"])

    def test_a_heading_can_carry_its_own_reference(self):
        read_on = "\n## Read On: Acts 1:1-2\n\n1 AAA BBB CCC DDD. 2 EEE FFF GGG HHH.\n"
        self.assertEqual(self.hit(extra=read_on), ["scripture-unverified"])
        self.assertEqual(self.hit(extra=read_on, cross=CROSS), [])
        self.assertEqual(self.hit(extra=read_on.replace("GGG", "ZZZ"), cross=CROSS),
                         ["scripture-mismatch"])

    # -- how it reports --------------------------------------------------------

    def test_a_finding_points_at_its_line_without_reprinting_the_passage(self):
        (found,) = self.findings(text=TEXT.replace("ETA THETA", "ETA OMEGA"))
        lines = self.piece.read_text(encoding="utf-8").splitlines()
        self.assertTrue(lines[found.line - 1].startswith("1 ALPHA BETA"))
        self.assertLessEqual(len(found.excerpt.split()), 9)

    def test_only_the_translations_the_rule_names(self):
        self.assertEqual(self.hit(translation="NKJV", text=TEXT.replace("ETA THETA", "ETA OMEGA")),
                         [])

    def test_nothing_without_the_rules_block(self):
        self.assertEqual(
            check_scripture_quotations({}, self.lesson(text="WRONG WORDS ENTIRELY HERE")), [])

    def test_it_runs_as_part_of_the_lint(self):
        lesson = self.lesson(text=TEXT.replace("ETA THETA", "ETA OMEGA"))
        self.assertIn("scripture-mismatch", {f.rule for f in check_lesson(RULES, lesson)})


PROSE_RULES = {
    **RULES,
    "forbidden_characters": [{"char": "—", "name": "em dash", "severity": "error"}],
    "forbidden_phrases": [{"pattern": "\\bdelve\\b", "severity": "error"}],
    "locked_strings": {"lords_prayer_form": {"severity": "error", "forbidden_pattern": "zeta eta"}},
}

# The same placeholder passage, carrying an em dash, a forbidden word and
# the stand-in Lord's Prayer pattern, the way a real passage can.
DASHED_GOSPEL = ("|-\n  1 ALPHA BETA—GAMMA DELTA. 2 EPSILON ZETA ETA THETA.\n\n"
                 "  3 NU XI OMICRON PI RHO SIGMA TAU DELVE. 4 UPSILON PHI CHI PSI.")
DASHED_TEXT = ("1 ALPHA BETA—GAMMA DELTA. 2 EPSILON ZETA ETA THETA. "
               "3 NU XI OMICRON PI RHO SIGMA TAU DELVE. 4 UPSILON PHI CHI PSI. (ESV)")
PROSE_FAMILIES = {"forbidden-character", "forbidden-phrase", "lords-prayer-form",
                  "scripture-mismatch"}


class ProseRulesTestCase(unittest.TestCase):
    """Verified Scripture is the publisher's text, not the curriculum's prose.

    The rules about prose, the em dash among them, do not read a quotation
    that checks out against lesson.yml. They still read everything else,
    including a quotation that does not check out.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="stpaul-prose-"))
        self.content = self.tmp / "content"
        (self.content / SLUG / "pieces").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def hits(self, rules=PROSE_RULES, *, translation="ESV", text=DASHED_TEXT,
             memory=MEMORY, talk=TALK):
        (self.content / SLUG / "lesson.yml").write_text(
            LESSON.format(translation=translation, gospel=DASHED_GOSPEL, cross="null"),
            encoding="utf-8")
        (self.content / SLUG / "pieces" / "06-primary-student-handout.md").write_text(
            PIECE.format(text=text, memory=memory, talk=talk, extra=""), encoding="utf-8")
        lesson = load_lesson(SLUG, content_dir=self.content)
        return sorted(f.rule.split(":")[0] for f in check_lesson(rules, lesson)
                      if f.rule.split(":")[0] in PROSE_FAMILIES)

    def test_verified_scripture_is_not_read_as_prose(self):
        self.assertEqual(self.hits(), [])

    def test_a_misquotation_is_read_as_prose_too(self):
        self.assertEqual(self.hits(text=DASHED_TEXT.replace("THETA", "OMEGA")),
                         ["forbidden-character", "forbidden-phrase", "lords-prayer-form",
                          "scripture-mismatch"])

    def test_prose_beside_a_verified_quotation_is_still_read(self):
        self.assertEqual(
            self.hits(memory='"ALPHA BETA—GAMMA DELTA" (Luke 1:1 ESV) — say it twice.'),
            ["forbidden-character"])

    def test_the_curriculums_own_words_are_still_read(self):
        self.assertEqual(self.hits(talk="Pray it: zeta eta."), ["lords-prayer-form"])

    def test_without_the_scripture_block_everything_is_read(self):
        rules = {k: v for k, v in PROSE_RULES.items() if k != "scripture_quotations"}
        self.assertEqual(self.hits(rules),
                         ["forbidden-character", "forbidden-phrase", "lords-prayer-form"])

    def test_a_sunday_in_another_translation_is_read_in_full(self):
        self.assertEqual(self.hits(translation="NKJV"),
                         ["forbidden-character", "forbidden-phrase", "lords-prayer-form"])


if __name__ == "__main__":
    unittest.main()
