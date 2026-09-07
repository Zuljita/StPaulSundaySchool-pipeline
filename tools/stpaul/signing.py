"""Signatures over approvals.

Without this, an approval is a JSON file, and anyone who can commit to
the data repository can write one. That is a weak thing to rest a
doctrinal gate on. With it, forging an approval needs the signing key,
which lives only in the approval service and never in the repository.

**What is signed is one review, not the whole file.** A reviewer's
approval is then independently verifiable, it can be moved between files
or re-recorded without becoming invalid, and a second reviewer signing
later does not disturb the first.

The payload is canonical JSON over exactly the fields that carry
meaning: who approved, verified how, in what role, for which Sunday, of
which content, when. Anything not in that list is commentary and is not
covered, so changing a note cannot invalidate a signature and forging one
cannot hide in a note.

Ed25519 is used because the keys and signatures are short enough to sit
in a JSON file without being unreadable, and because Cloudflare Workers
can produce them with Web Crypto, so the service needs no crypto library.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)

ALGORITHM = "ed25519"

# Exactly the fields a signature covers. Order is fixed here rather than
# taken from the dict, so two implementations cannot disagree about it.
SIGNED_FIELDS = (
    "sunday",
    "reviewer",
    "verified_identity",
    "role",
    "decision",
    "content_sha256",
    "at",
)


class SigningError(Exception):
    pass


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def unb64(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def payload(review: dict, sunday: str) -> bytes:
    """The exact bytes a signature covers.

    Missing fields become empty strings rather than being omitted, so a
    signature cannot be replayed onto a record that simply drops one.
    """
    data = {"sunday": sunday}
    for f in SIGNED_FIELDS:
        if f == "sunday":
            continue
        data[f] = str(review.get(f) or "")
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


# ---------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------

def generate_keypair() -> tuple[str, str]:
    """Return (private key PEM, public key base64)."""
    private = Ed25519PrivateKey.generate()
    pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    raw_pub = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return pem, b64(raw_pub)


def load_private(pem: str) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SigningError("not an Ed25519 private key")
    return key


def load_public(b64_key: str) -> Ed25519PublicKey:
    try:
        return Ed25519PublicKey.from_public_bytes(unb64(b64_key.strip()))
    except Exception as e:
        raise SigningError(f"bad public key: {e}") from e


def read_public_key(standards_dir: Path) -> str | None:
    """The public half, committed to the data repository.

    Its presence in git is the point: the key everyone verifies against
    is reviewable, and changing it is a visible commit.
    """
    p = standards_dir / "approval-key.pub"
    if not p.is_file():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return None


# ---------------------------------------------------------------------
# Sign and verify
# ---------------------------------------------------------------------

def sign_review(review: dict, sunday: str, private_pem: str) -> str:
    key = load_private(private_pem)
    return f"{ALGORITHM}:{b64(key.sign(payload(review, sunday)))}"


def verify_review(review: dict, sunday: str, public_b64: str) -> bool:
    sig = review.get("signature") or ""
    if not sig.startswith(f"{ALGORITHM}:"):
        return False
    try:
        load_public(public_b64).verify(unb64(sig.split(":", 1)[1]),
                                       payload(review, sunday))
        return True
    except (InvalidSignature, SigningError, ValueError):
        return False
