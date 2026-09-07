"""The approval gate.

An approval is a statement about *specific bytes*: "I, a named reviewer,
approved the text whose canonical hash is <h>."  It is not a statement
about a Sunday in general.  That distinction is the entire mechanism.

If one comma of the reviewed text changes afterwards, the recomputed
hash no longer matches the hash the reviewer signed, every review
attached to the old hash stops counting, and the build refuses.  There
is no way for an editor of any kind, human or model, to change approved
text and have it ship quietly.  It does not depend on anyone remembering
to re-check.

Approvals live in approvals/<sunday>.approval.json and are committed, so
"who approved what, and when" is answerable from git history alone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .hashing import ALGORITHM, content_hash
from .model import APPROVALS_DIR, CONTENT_DIR, STANDARDS_DIR

APPROVED = "approved"
CHANGES_REQUESTED = "changes_requested"

# Status values reported by verify()
OK = "approved"
NO_APPROVAL_FILE = "no-approval-file"
STALE = "stale"
INSUFFICIENT = "insufficient"


@dataclass
class Review:
    reviewer: str
    role: str
    decision: str
    at: str
    content_sha256: str
    note: str = ""
    github: str = ""

    @classmethod
    def new(cls, reviewer: str, role: str, decision: str,
            content_sha256: str, note: str = "", github: str = "") -> "Review":
        return cls(
            reviewer=reviewer, role=role, decision=decision,
            at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            content_sha256=content_sha256, note=note, github=github,
        )


def reviewer_roster(standards_dir: Path = STANDARDS_DIR) -> dict:
    """Who may review, and in what role.

    Keeping the roster in the repo means adding an approver is itself a
    reviewable commit, rather than something that happens in a tool's
    private state.
    """
    p = standards_dir / "reviewers.yml"
    if not p.is_file():
        return {"reviewers": [], "policy": {"required_approvals": 1, "required_roles": ["pastor"]}}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def approval_path(slug: str, approvals_dir: Path = APPROVALS_DIR) -> Path:
    return approvals_dir / f"{slug}.approval.json"


def load_approval(slug: str, approvals_dir: Path = APPROVALS_DIR) -> dict | None:
    p = approval_path(slug, approvals_dir)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save_approval(slug: str, record: dict, approvals_dir: Path = APPROVALS_DIR) -> Path:
    approvals_dir.mkdir(parents=True, exist_ok=True)
    p = approval_path(slug, approvals_dir)
    p.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def record_review(slug: str, review: Review, *,
                  content_dir: Path = CONTENT_DIR,
                  approvals_dir: Path = APPROVALS_DIR,
                  standards_dir: Path = STANDARDS_DIR) -> dict:
    """Append a review to a Sunday's approval record."""
    digest, manifest = content_hash(content_dir / slug)
    record = load_approval(slug, approvals_dir) or {
        "sunday": slug,
        "algorithm": ALGORITHM,
        "reviews": [],
    }
    roster = reviewer_roster(standards_dir)
    record["algorithm"] = ALGORITHM
    record["content_sha256"] = digest
    record["files"] = manifest
    record["policy"] = roster.get("policy", {"required_approvals": 1, "required_roles": ["pastor"]})
    record.setdefault("reviews", []).append(asdict(review))
    save_approval(slug, record, approvals_dir)
    return record


@dataclass
class Verification:
    status: str
    slug: str
    current_hash: str
    approved_hash: str = ""
    changed_files: list[str] = None
    approving_reviews: list[dict] = None
    required: int = 0
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == OK


def verify(slug: str, *,
           content_dir: Path = CONTENT_DIR,
           approvals_dir: Path = APPROVALS_DIR,
           standards_dir: Path = STANDARDS_DIR,
           policy: dict | None = None) -> Verification:
    """Does this Sunday's content on disk carry a valid, current approval?

    The policy applied is the *current* roster's, not the one captured
    when the review was recorded. Tightening the roster (adding a second
    required approval, say) therefore takes effect immediately on
    everything not yet built, rather than only on Sundays reviewed after
    the change. A Sunday that was passing can start failing because of a
    roster edit, which is the safe direction for that surprise to run.
    """
    digest, manifest = content_hash(content_dir / slug)
    record = load_approval(slug, approvals_dir)

    if record is None:
        return Verification(
            status=NO_APPROVAL_FILE, slug=slug, current_hash=digest,
            detail="No approval record exists for this Sunday. It has never been reviewed.",
        )

    approved_hash = record.get("content_sha256", "")
    if approved_hash != digest:
        old = record.get("files", {})
        changed = sorted(
            set(k for k in set(old) | set(manifest) if old.get(k) != manifest.get(k))
        )
        return Verification(
            status=STALE, slug=slug, current_hash=digest, approved_hash=approved_hash,
            changed_files=changed,
            detail=("Content has changed since it was reviewed. Every review on record "
                    "applies to the previous text and no longer counts."),
        )

    if policy is None:
        policy = reviewer_roster(standards_dir).get("policy") or record.get("policy") or {}
    required = int(policy.get("required_approvals", 1))
    required_roles = set(policy.get("required_roles") or [])

    valid = [
        r for r in record.get("reviews", [])
        if r.get("decision") == APPROVED and r.get("content_sha256") == digest
    ]
    # A later "changes requested" from the same reviewer at the same hash
    # withdraws their approval.
    rejected_by = {
        r.get("reviewer") for r in record.get("reviews", [])
        if r.get("decision") == CHANGES_REQUESTED and r.get("content_sha256") == digest
    }
    valid = [r for r in valid if r.get("reviewer") not in rejected_by]

    # Deduplicate: one reviewer approving twice is still one approval.
    by_reviewer = {r.get("reviewer"): r for r in valid}
    valid = list(by_reviewer.values())

    roles_present = {r.get("role") for r in valid}
    missing_roles = required_roles - roles_present

    if len(valid) < required or missing_roles:
        bits = []
        if len(valid) < required:
            bits.append(f"{len(valid)} of {required} required approvals")
        if missing_roles:
            bits.append(f"missing required role(s): {', '.join(sorted(missing_roles))}")
        return Verification(
            status=INSUFFICIENT, slug=slug, current_hash=digest, approved_hash=approved_hash,
            approving_reviews=valid, required=required,
            detail="Content matches the reviewed text, but " + "; ".join(bits) + ".",
        )

    return Verification(
        status=OK, slug=slug, current_hash=digest, approved_hash=approved_hash,
        approving_reviews=valid, required=required,
        detail=f"Approved by {', '.join(sorted(r['reviewer'] for r in valid))}.",
    )
