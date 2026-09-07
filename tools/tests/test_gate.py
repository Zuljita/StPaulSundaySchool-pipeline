"""Tests for the approval gate.

These exist because the gate's whole value is a claim: "approved text
cannot be changed and still ship." A claim like that is worth nothing
unless something proves it on every commit, which is the same mistake
the em-dash rule made when it lived only in prose.

Run:  python -m unittest discover -s tools/tests -v
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stpaul import approval, hashing
from stpaul.model import load_lesson, load_rules
from stpaul.rules import ERROR, check_lesson, summarize

LESSON_YML = """\
sunday: 2026-01-04-test
date: 2026-01-04
liturgical_day: "Test Sunday"
status: draft
gospel: "Luke 1:1-4"
translation: ESV
theme: "A theme line, identical on every piece."
lords_prayer_form: trespasses
attribution: >-
  These Sunday School Lessons are built especially for St. Paul Lutheran
  Church by Pastor Bryan Wolfmueller with Claude AI on the same Sunday
  Gospel Lesson.
"""

PIECE = """\
---
piece: family-take-home
type: family_take_home
level: all
order: 1
---

# Family Take-Home

## What They Heard

A plain retelling.

## A Word for the Parents

A pastoral paragraph.

## The Verse to Say This Week

A verse.

## One Question at Dinner

A question.

## From the Small Catechism

Quoted text.

## Pray This Together

A prayer.

## This Week's Hymn

A stanza.

## Credits

These Sunday School Lessons are built especially for St. Paul Lutheran
Church by Pastor Bryan Wolfmueller with Claude AI on the same Sunday
Gospel Lesson.
"""

SLUG = "2026-01-04-test"


class GateTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="stpaul-test-"))
        self.content = self.tmp / "content"
        self.approvals = self.tmp / "approvals"
        (self.content / SLUG / "pieces").mkdir(parents=True)
        self.approvals.mkdir()
        (self.content / SLUG / "lesson.yml").write_text(LESSON_YML, encoding="utf-8")
        self.piece_path = self.content / SLUG / "pieces" / "01-family-take-home.md"
        self.piece_path.write_text(PIECE, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def approve(self, reviewer="Bryan Wolfmueller", role="pastor"):
        digest, _ = hashing.content_hash(self.content / SLUG)
        review = approval.Review.new(reviewer=reviewer, role=role,
                                     decision=approval.APPROVED,
                                     content_sha256=digest)
        return approval.record_review(SLUG, review, content_dir=self.content,
                                      approvals_dir=self.approvals,
                                      standards_dir=Path(__file__).resolve().parents[2] / "standards")

    def verify(self, policy=None):
        return approval.verify(SLUG, content_dir=self.content,
                               approvals_dir=self.approvals, policy=policy)

    # -- hashing -------------------------------------------------------

    def test_hash_is_stable_across_line_endings(self):
        """A Windows checkout and a Linux checkout must agree."""
        lf_bytes = PIECE.replace("\r\n", "\n").encode("utf-8")
        self.piece_path.write_bytes(lf_bytes)
        lf, _ = hashing.content_hash(self.content / SLUG)

        self.piece_path.write_bytes(lf_bytes.replace(b"\n", b"\r\n"))
        crlf, _ = hashing.content_hash(self.content / SLUG)
        self.assertEqual(lf, crlf)

    def test_hash_ignores_a_trailing_newline(self):
        """Editors disagree about the last byte; that is not a doctrinal edit."""
        base = PIECE.replace("\r\n", "\n").encode("utf-8").rstrip(b"\n")
        self.piece_path.write_bytes(base)
        a, _ = hashing.content_hash(self.content / SLUG)
        self.piece_path.write_bytes(base + b"\n\n\n")
        b, _ = hashing.content_hash(self.content / SLUG)
        self.assertEqual(a, b)

    def test_hash_notices_whitespace_inside_a_line(self):
        """Christ died and Christ  died are different text."""
        a, _ = hashing.content_hash(self.content / SLUG)
        text = self.piece_path.read_text(encoding="utf-8")
        self.piece_path.write_text(text.replace("A verse.", "A  verse."), encoding="utf-8")
        b, _ = hashing.content_hash(self.content / SLUG)
        self.assertNotEqual(a, b)

    def test_hash_changes_on_one_character(self):
        before, _ = hashing.content_hash(self.content / SLUG)
        text = self.piece_path.read_text(encoding="utf-8")
        self.piece_path.write_text(text.replace("A verse.", "A verse!"), encoding="utf-8")
        after, _ = hashing.content_hash(self.content / SLUG)
        self.assertNotEqual(before, after)

    def test_hash_changes_when_a_piece_is_deleted(self):
        """Dropping a whole piece must not look like no change at all."""
        before, _ = hashing.content_hash(self.content / SLUG)
        self.piece_path.unlink()
        after, _ = hashing.content_hash(self.content / SLUG)
        self.assertNotEqual(before, after)

    # -- the gate ------------------------------------------------------

    def test_unreviewed_content_is_not_approved(self):
        v = self.verify()
        self.assertFalse(v.ok)
        self.assertEqual(v.status, approval.NO_APPROVAL_FILE)

    def test_approval_makes_it_pass(self):
        self.approve()
        v = self.verify()
        self.assertTrue(v.ok, v.detail)
        self.assertEqual(v.status, approval.OK)

    def test_editing_after_approval_invalidates_it(self):
        """The property the whole pipeline rests on."""
        self.approve()
        self.assertTrue(self.verify().ok)

        text = self.piece_path.read_text(encoding="utf-8")
        self.piece_path.write_text(
            text.replace("A pastoral paragraph.",
                         "A pastoral paragraph, subtly altered."), encoding="utf-8")

        v = self.verify()
        self.assertFalse(v.ok)
        self.assertEqual(v.status, approval.STALE)
        self.assertIn("pieces/01-family-take-home.md", v.changed_files)

    def test_reverting_the_edit_restores_approval(self):
        """The gate tracks bytes, not events, so an undo really is an undo."""
        self.approve()
        original = self.piece_path.read_text(encoding="utf-8")
        self.piece_path.write_text(original + "\nAdded.\n", encoding="utf-8")
        self.assertFalse(self.verify().ok)
        self.piece_path.write_text(original, encoding="utf-8")
        self.assertTrue(self.verify().ok)

    def test_changes_requested_withdraws_an_approval(self):
        self.approve()
        self.assertTrue(self.verify().ok)
        digest, _ = hashing.content_hash(self.content / SLUG)
        approval.record_review(
            SLUG,
            approval.Review.new(reviewer="Bryan Wolfmueller", role="pastor",
                                decision=approval.CHANGES_REQUESTED,
                                content_sha256=digest),
            content_dir=self.content, approvals_dir=self.approvals,
            standards_dir=Path(__file__).resolve().parents[2] / "standards")
        v = self.verify()
        self.assertFalse(v.ok)
        self.assertEqual(v.status, approval.INSUFFICIENT)

    def test_one_reviewer_approving_twice_is_one_approval(self):
        self.approve()
        self.approve()   # same reviewer, same content
        two_needed = {"required_approvals": 2, "required_roles": []}
        v = self.verify(policy=two_needed)
        self.assertFalse(v.ok)
        self.assertEqual(v.status, approval.INSUFFICIENT)

    def test_two_distinct_reviewers_satisfy_a_two_approval_policy(self):
        self.approve(reviewer="Bryan Wolfmueller", role="pastor")
        self.approve(reviewer="A Second Pastor", role="pastor")
        v = self.verify(policy={"required_approvals": 2, "required_roles": ["pastor"]})
        self.assertTrue(v.ok, v.detail)

    def test_tightening_the_policy_unapproves_a_passing_sunday(self):
        """Raising the bar must apply to work already sitting approved."""
        self.approve()
        self.assertTrue(self.verify().ok)
        v = self.verify(policy={"required_approvals": 2, "required_roles": ["pastor"]})
        self.assertFalse(v.ok)

    def test_required_role_is_enforced(self):
        self.approve(reviewer="An Elder", role="elder")
        v = self.verify(policy={"required_approvals": 1, "required_roles": ["pastor"]})
        self.assertFalse(v.ok)
        self.assertIn("pastor", v.detail)

    def test_approval_does_not_transfer_between_sundays(self):
        """An approval is about bytes, so it cannot be reused elsewhere."""
        self.approve()
        other = self.content / "2026-01-11-test"
        shutil.copytree(self.content / SLUG, other)
        (other / "pieces" / "01-family-take-home.md").write_text(
            PIECE.replace("A plain retelling.", "Different text."), encoding="utf-8")
        v = approval.verify("2026-01-11-test", content_dir=self.content,
                            approvals_dir=self.approvals)
        self.assertFalse(v.ok)


class RuleTestCase(unittest.TestCase):
    """The linter must actually catch what shipped in Trinity 16."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="stpaul-rules-"))
        self.content = self.tmp / "content"
        (self.content / SLUG / "pieces").mkdir(parents=True)
        (self.content / SLUG / "lesson.yml").write_text(LESSON_YML, encoding="utf-8")
        self.piece_path = self.content / SLUG / "pieces" / "01-family-take-home.md"
        self.rules = load_rules()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def findings_for(self, body: str):
        self.piece_path.write_text(body, encoding="utf-8")
        lesson = load_lesson(SLUG, content_dir=self.content)
        return check_lesson(self.rules, lesson)

    def rules_hit(self, body: str) -> set[str]:
        return {f.rule.split(":")[0] for f in self.findings_for(body)}

    def test_clean_piece_has_no_errors(self):
        findings = self.findings_for(PIECE)
        errors = [f for f in findings if f.severity == ERROR]
        self.assertEqual([str(f) for f in errors if f.piece], [])

    def test_em_dash_is_an_error(self):
        findings = self.findings_for(PIECE.replace("A verse.", "A verse — here."))
        hits = [f for f in findings if f.rule.startswith("forbidden-character")]
        self.assertTrue(hits)
        self.assertEqual(hits[0].severity, ERROR)

    def test_retired_was_ist_das_is_an_error(self):
        self.assertIn("forbidden-phrase",
                      self.rules_hit(PIECE.replace("A question.", "Was ist das?")))

    def test_decision_theology_is_an_error(self):
        self.assertIn("forbidden-phrase", self.rules_hit(
            PIECE.replace("A prayer.", "Ask Jesus into your heart.")))

    def test_draft_marker_is_an_error(self):
        self.assertIn("draft-marker", self.rules_hit(
            PIECE.replace("A stanza.", "[Insert stanza text here]")))

    def test_missing_section_is_an_error(self):
        body = PIECE.replace("## Pray This Together\n\nA prayer.\n\n", "")
        self.assertIn("missing-section", self.rules_hit(body))

    def test_wrong_catechism_heading_is_caught(self):
        self.assertIn("wrong-catechism-heading", self.rules_hit(
            PIECE.replace("## From the Small Catechism", "## Catechism Connection")))

    def test_lords_prayer_debts_form_is_an_error(self):
        self.assertIn("lords-prayer-form", self.rules_hit(
            PIECE.replace("A prayer.", "Forgive us our debts.")))

    def test_attribution_missing_from_family_take_home(self):
        body = PIECE.replace(
            "These Sunday School Lessons are built especially for St. Paul Lutheran\n"
            "Church by Pastor Bryan Wolfmueller with Claude AI on the same Sunday\n"
            "Gospel Lesson.\n", "No credit line.\n")
        self.assertIn("missing-attribution", self.rules_hit(body))

    def test_open_conflicts_are_always_reported(self):
        self.assertIn("open-conflict", self.rules_hit(PIECE))


if __name__ == "__main__":
    unittest.main(verbosity=2)
