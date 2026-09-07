"""Tests for signed approvals.

The claim being tested: with `require_signed_approvals` on, having write
access to the data repository is not enough to approve doctrine. You need
the signing key, which lives only in the approval service.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# The pipeline is tested against a fixture, never against the private
# data repository, so `python -m unittest` works in a bare checkout.
FIXTURE_STANDARDS = Path(__file__).resolve().parent / "data" / "standards"

from stpaul import approval, hashing, signing

SLUG = "2026-01-04-test"

LESSON_YML = """\
sunday: 2026-01-04-test
date: 2026-01-04
liturgical_day: "Test Sunday"
status: draft
translation: ESV
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
"""

SIGNED_POLICY = {
    "required_approvals": 1,
    "required_roles": ["pastor"],
    "require_signed_approvals": True,
}


class SigningTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="stpaul-sign-"))
        self.content = self.tmp / "content"
        self.approvals = self.tmp / "approvals"
        self.standards = self.tmp / "standards"
        (self.content / SLUG / "pieces").mkdir(parents=True)
        self.approvals.mkdir()
        self.standards.mkdir()
        (self.content / SLUG / "lesson.yml").write_text(LESSON_YML, encoding="utf-8")
        (self.content / SLUG / "pieces" / "01-family-take-home.md").write_text(
            PIECE, encoding="utf-8")

        self.private_pem, self.public_b64 = signing.generate_keypair()
        (self.standards / "approval-key.pub").write_text(
            self.public_b64 + "\n", encoding="utf-8")
        (self.standards / "reviewers.yml").write_text(
            "policy:\n"
            "  required_approvals: 1\n"
            "  required_roles: [pastor]\n"
            "  require_signed_approvals: true\n"
            "reviewers:\n"
            "  - name: Bryan Wolfmueller\n"
            "    role: pastor\n"
            "    email: pastor@example.org\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def digest(self):
        return hashing.content_hash(self.content / SLUG)[0]

    def record(self, *, sign: bool, reviewer="Bryan Wolfmueller", role="pastor",
               tamper=None):
        review = approval.Review.new(
            reviewer=reviewer, role=role, decision=approval.APPROVED,
            content_sha256=self.digest(), method="google",
            verified_identity="google:pastor@example.org")
        d = review.__dict__
        if sign:
            d["signature"] = signing.sign_review(d, SLUG, self.private_pem)
        if tamper:
            d.update(tamper)
        rec = {"sunday": SLUG, "algorithm": hashing.ALGORITHM,
               "content_sha256": self.digest(),
               "files": hashing.content_hash(self.content / SLUG)[1],
               "reviews": [d]}
        approval.save_approval(SLUG, rec, self.approvals)

    def verify(self, policy=SIGNED_POLICY):
        return approval.verify(SLUG, content_dir=self.content,
                               approvals_dir=self.approvals,
                               standards_dir=self.standards, policy=policy)

    # -- the core claim ------------------------------------------------

    def test_signed_approval_passes(self):
        self.record(sign=True)
        v = self.verify()
        self.assertTrue(v.ok, v.detail)

    def test_unsigned_approval_is_rejected_when_policy_requires_signing(self):
        """Repo write alone must not be enough to approve doctrine."""
        self.record(sign=False)
        v = self.verify()
        self.assertFalse(v.ok)
        self.assertIn("unsigned", v.detail)

    def test_unsigned_approval_passes_when_policy_does_not_require_signing(self):
        self.record(sign=False)
        v = self.verify(policy={"required_approvals": 1, "required_roles": ["pastor"]})
        self.assertTrue(v.ok, v.detail)

    # -- tampering -----------------------------------------------------

    def test_changing_the_reviewer_name_breaks_the_signature(self):
        self.record(sign=True, tamper={"reviewer": "Somebody Else"})
        self.assertFalse(self.verify().ok)

    def test_changing_the_role_breaks_the_signature(self):
        self.record(sign=True, tamper={"role": "archbishop"})
        self.assertFalse(self.verify().ok)

    def test_changing_the_decision_breaks_the_signature(self):
        """A changes-requested record must not be editable into an approval."""
        self.record(sign=True, tamper={"decision": approval.APPROVED,
                                       "content_sha256": "0" * 64})
        self.assertFalse(self.verify().ok)

    def test_changing_the_content_hash_breaks_the_signature(self):
        self.record(sign=True, tamper={"content_sha256": "0" * 64})
        self.assertFalse(self.verify().ok)

    def test_editing_a_note_does_not_break_the_signature(self):
        """Commentary is deliberately outside what the signature covers."""
        self.record(sign=True, tamper={"note": "added afterwards"})
        self.assertTrue(self.verify().ok)

    def test_a_signature_from_another_key_is_rejected(self):
        other_pem, _ = signing.generate_keypair()
        review = approval.Review.new(
            reviewer="Bryan Wolfmueller", role="pastor",
            decision=approval.APPROVED, content_sha256=self.digest(),
            method="google", verified_identity="google:pastor@example.org")
        d = review.__dict__
        d["signature"] = signing.sign_review(d, SLUG, other_pem)
        approval.save_approval(SLUG, {
            "sunday": SLUG, "content_sha256": self.digest(),
            "files": hashing.content_hash(self.content / SLUG)[1],
            "reviews": [d]}, self.approvals)
        self.assertFalse(self.verify().ok)

    def test_a_signature_cannot_be_replayed_onto_another_sunday(self):
        """The Sunday is inside the signed payload."""
        review = approval.Review.new(
            reviewer="Bryan Wolfmueller", role="pastor",
            decision=approval.APPROVED, content_sha256=self.digest())
        d = review.__dict__
        d["signature"] = signing.sign_review(d, "2026-02-01-other", self.private_pem)
        self.assertFalse(signing.verify_review(d, SLUG, self.public_b64))

    def test_missing_public_key_fails_closed(self):
        """No key must mean no approval, not an approval nobody checked."""
        self.record(sign=True)
        (self.standards / "approval-key.pub").unlink()
        v = self.verify()
        self.assertFalse(v.ok)
        self.assertIn("approval-key.pub", v.detail)



class CrossImplementationTestCase(unittest.TestCase):
    """The Worker signs; Python verifies. They must agree byte for byte.

    If the two canonical payloads ever drift, every approval the service
    issues silently stops verifying and the gate fails closed on real
    approvals. That is a bad way to find out, so it is checked here.
    """

    REVIEW = {
        "reviewer": "Bryan Wolfmueller",
        "role": "pastor",
        "decision": "approved",
        "at": "2026-09-27T14:03:00+00:00",
        "content_sha256": "40" * 32,
        "verified_identity": "google:pastor@example.org",
        "note": "deliberately outside the signature",
        "method": "google",
    }
    SUNDAY = "2026-09-27-trinity-17"

    def test_worker_and_python_payloads_are_identical(self):
        import base64
        import json
        import shutil
        import subprocess

        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")

        worker = (Path(__file__).resolve().parents[2]
                  / "services" / "approval" / "worker.js")
        if not worker.is_file():
            self.skipTest("worker.js not in this checkout")

        # Pull the two functions out of the Worker rather than restating
        # them, so this test breaks if the Worker's copy changes.
        src = worker.read_text(encoding="utf-8")
        start = src.index("const SIGNED_FIELDS")
        end = src.index("async function signReview")
        snippet = src[start:end]

        script = (
            "const enc = new TextEncoder();\n"
            + snippet
            + "\nconst r = JSON.parse(process.argv[2]);\n"
              "process.stdout.write(Buffer.from(signingPayload(r, process.argv[3]))"
              ".toString('base64'));\n"
        )
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "p.mjs"
            f.write_text(script, encoding="utf-8")
            out = subprocess.run(
                [node, str(f), json.dumps(self.REVIEW), self.SUNDAY],
                capture_output=True, text=True, check=True).stdout.strip()

        expected = base64.b64encode(
            signing.payload(self.REVIEW, self.SUNDAY)).decode()
        self.assertEqual(out, expected)

    def test_note_is_not_covered_by_the_signature(self):
        a = signing.payload(self.REVIEW, self.SUNDAY)
        b = signing.payload({**self.REVIEW, "note": "different"}, self.SUNDAY)
        self.assertEqual(a, b)

if __name__ == "__main__":
    unittest.main(verbosity=2)
