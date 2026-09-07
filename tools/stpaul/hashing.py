"""Canonical hashing for the approval gate.

The whole freeze line rests on one question: *is the text I am about to
print byte-for-byte the text that was doctrinally reviewed?*  That
question is only meaningful if "byte-for-byte" is computed the same way
on every machine, so this module is deliberately small and boring.

Normalization rules, and why each exists:

  * Line endings collapse to LF.  Windows and Linux checkouts of the same
    commit otherwise hash differently and every build on the other
    machine would look tampered with.
  * A single trailing newline is enforced.  Editors disagree about the
    last byte of a file and that disagreement is not a doctrinal change.
  * Nothing else is touched.  In particular whitespace inside a line is
    significant: "Christ  died" and "Christ died" are different text and
    the gate should notice.

Anything beyond this would be the tool deciding that some edits do not
count, which is exactly the authority this tool must not have.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

# Bumped only if the normalization rules above change.  An approval
# records the algorithm that produced it, so an old approval is never
# silently re-interpreted under new rules.
ALGORITHM = "stpaul-canonical-sha256/1"


def normalize(data: bytes) -> bytes:
    """Apply the canonical normalization described in the module docstring.

    Order matters: CR LF collapses first, then any bare CR, so a file
    written on Windows and the same file written on Linux land on the
    same bytes. Note this is not idempotent over pathological input like
    CR CR LF, which is a genuinely different file and should hash
    differently rather than being quietly repaired.
    """
    data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    data = data.rstrip(b"\n")
    if data:
        data += b"\n"
    return data


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(normalize(data)).hexdigest()


def hash_file(path: Path) -> str:
    return hash_bytes(path.read_bytes())


def content_files(sunday_dir: Path) -> list[Path]:
    """Every file that makes up a Sunday's reviewable content, sorted.

    Sorted by POSIX relative path so the manifest order does not depend
    on the filesystem's directory ordering.
    """
    files = [p for p in sunday_dir.rglob("*") if p.is_file()]
    return sorted(files, key=lambda p: p.relative_to(sunday_dir).as_posix())


def file_manifest(sunday_dir: Path) -> dict[str, str]:
    """Map of relative path -> canonical hash, for one Sunday."""
    return {
        p.relative_to(sunday_dir).as_posix(): hash_file(p)
        for p in content_files(sunday_dir)
    }


def manifest_hash(manifest: dict[str, str]) -> str:
    """One hash standing for an entire Sunday's content.

    Hashing the serialized manifest rather than the concatenated files
    means a file being *renamed* or *removed* changes the result, not
    just a file's contents changing.  Dropping a whole piece is exactly
    the kind of silent change the gate has to catch.
    """
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def content_hash(sunday_dir: Path) -> tuple[str, dict[str, str]]:
    """Return (overall hash, per-file manifest) for a Sunday."""
    manifest = file_manifest(sunday_dir)
    return manifest_hash(manifest), manifest
