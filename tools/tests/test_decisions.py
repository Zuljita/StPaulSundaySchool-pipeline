"""Tests that one decision means the same thing everywhere.

Three places have an opinion about what a reviewer decided:

  * `tools/stpaul/approval.py` defines the words, and counts them at gate
    time. Only a review whose decision is exactly "approved" is an
    approval.
  * `services/approval/worker.js` records the decision, and signs it.
  * `review/index.html` is where a pastor clicks.

They agreed on paper and not in fact. The app sent "APPROVE" and
"REQUEST_CHANGES"; the Worker compared against "changes_requested" and
sent everything else down an `: "approved"` branch. So "Request changes"
recorded an approval, in the reviewer's name, over content he had just
asked to have changed. It failed in the one direction a doctrinal gate
must never fail.

Nothing caught it because each file was self-consistent. These tests
read the three files and compare them to each other.

The same three files also decide whether a Sunday may be approved at all,
and they drifted there too, so LintGateTestCase below holds them to the
same standard: agree with each other, and when in doubt refuse.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from stpaul import approval

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "services" / "approval" / "worker.js"
APP = ROOT / "review" / "index.html"
MAKE_REVIEW = ROOT / "tools" / "make_review.py"


def worker_decisions() -> set[str]:
    """The decisions the service will accept, read out of the Worker."""
    src = WORKER.read_text(encoding="utf-8")
    m = re.search(r"const DECISIONS = \[([^\]]*)\];", src)
    if not m:
        raise AssertionError(
            "worker.js has no `const DECISIONS = [...]`. It is the list of "
            "decisions the service accepts; if it moved, move this test.")
    return set(re.findall(r'"([^"]+)"', m.group(1)))


class DecisionVocabularyTestCase(unittest.TestCase):
    def setUp(self):
        for f in (WORKER, APP):
            if not f.is_file():
                self.skipTest(f"{f.name} not in this checkout")

    def test_worker_accepts_exactly_what_the_gate_counts(self):
        """The service must not accept a word the gate cannot read."""
        self.assertEqual(
            worker_decisions(),
            {approval.APPROVED, approval.CHANGES_REQUESTED},
            "worker.js accepts a different set of decisions than "
            "tools/stpaul/approval.py counts. A decision the gate does not "
            "recognise is never an approval, so recording one strands the "
            "Sunday; a decision the gate reads as approval but the service "
            "will not accept cannot be given at all.")

    def test_the_app_sends_only_decisions_the_service_accepts(self):
        """The bug itself: the app's words were not the service's words."""
        sent = set(re.findall(r'submit\(\s*\w+\s*,\s*"([^"]+)"',
                              APP.read_text(encoding="utf-8")))
        self.assertTrue(sent, "found no submit() decision literals in the app")
        accepted = worker_decisions()
        self.assertTrue(
            sent <= accepted,
            f"the review app sends {sorted(sent - accepted)}, which the "
            f"service does not accept (it takes {sorted(accepted)}). This is "
            f"exactly the drift that made 'Request changes' record an "
            f"approval.")

    def test_the_app_can_still_ask_for_both(self):
        """Both decisions must remain reachable from the page.

        A page that can only approve is a page that cannot refuse, which
        is a worse gate than none: it would look like review happened.
        """
        sent = set(re.findall(r'submit\(\s*\w+\s*,\s*"([^"]+)"',
                              APP.read_text(encoding="utf-8")))
        self.assertIn(approval.APPROVED, sent)
        self.assertIn(approval.CHANGES_REQUESTED, sent)

    def test_the_worker_has_no_default_decision(self):
        """An unrecognised decision must be refused, never assumed.

        The original line read

            const decision = body.decision === "changes_requested"
              ? "changes_requested" : "approved";

        which turns anything at all, including a typo, a stale client or
        an empty body, into an approval. Guard the shape of the
        replacement: a membership test, and a refusal.
        """
        src = WORKER.read_text(encoding="utf-8")
        self.assertIn(
            "DECISIONS.includes(body.decision)", src,
            "worker.js no longer tests body.decision for membership of "
            "DECISIONS. Whatever replaced it must still refuse a decision "
            "it cannot name, rather than choosing one.")
        self.assertNotRegex(
            src, r'body\.decision\s*===\s*"[^"]*"\s*\n?\s*\?',
            "worker.js is choosing a decision with a ternary again. That is "
            "the shape of the bug: the false branch is a silent approval.")



class LintGateTestCase(unittest.TestCase):
    """The approval gate must block on what is new, and agree with itself.

    Three files decide whether a Sunday may be approved: make_review.py
    writes the counts, worker.js refuses on them, and index.html disables
    the button. They have to mean the same thing. When they did not, the
    service blocked every imported Sunday on debt the baseline exists to
    tolerate, and nothing could be approved at all.
    """

    def setUp(self):
        for f in (WORKER, APP, MAKE_REVIEW):
            if not f.is_file():
                self.skipTest(f"{f.name} not in this checkout")

    def test_make_review_publishes_the_baselined_count(self):
        src = MAKE_REVIEW.read_text(encoding="utf-8")
        self.assertIn(
            '"new_errors": new_errors', src,
            "make_review.py no longer writes new_errors into the lint block. "
            "The service reads that field to decide what blocks approval; "
            "without it every bundle is refused as unreadable.")

    def test_the_service_blocks_on_what_is_new(self):
        src = WORKER.read_text(encoding="utf-8")
        self.assertIn(
            "lint.new_errors", src,
            "worker.js no longer reads lint.new_errors, so it is back to "
            "blocking on the raw count, which no imported Sunday can clear.")
        self.assertNotIn(
            "(review_data.lint?.errors || 0) > 0", src,
            "worker.js is gating on the raw error count again.")

    def test_a_bundle_without_the_field_is_refused_not_waved_through(self):
        """Failing closed is the whole point of the fallback."""
        src = WORKER.read_text(encoding="utf-8")
        self.assertRegex(
            src, r'typeof lint\.new_errors === "number"',
            "worker.js must test for new_errors explicitly. Reading it as a "
            "plain truthy value makes a bundle that lacks it look like a "
            "bundle with zero new violations, which signs an approval over "
            "text nobody counted.")
        self.assertIn(
            "(lint.errors || 0)", src,
            "worker.js must fall back to the raw count when new_errors is "
            "absent. Falling back to zero would be a silent approval.")

    def test_the_button_and_the_service_agree(self):
        src = APP.read_text(encoding="utf-8")
        self.assertIn(
            "blockingErrors(d.lint)", src,
            "the approve button no longer uses blockingErrors, so the page "
            "and the service can now disagree about whether approval is "
            "possible. A button the service then refuses is worse than a "
            "disabled one that says why.")
        self.assertNotRegex(
            src, r"if \(d\.lint\.errors\)",
            "the approve button is gating on the raw error count again.")


if __name__ == "__main__":
    unittest.main()
