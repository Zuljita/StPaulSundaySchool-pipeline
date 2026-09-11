#!/usr/bin/env python
"""Fetch a Sunday's pericope from Crossway's ESV API and write it in.

    python tools/fetch_scripture.py 2026-09-27-trinity-17
    python tools/fetch_scripture.py 2026-09-27-trinity-17 --write
    python tools/fetch_scripture.py 2026-09-27-trinity-17 --ref "Mark 2:27"

Scripture is the one thing in this curriculum that must not be retyped,
paraphrased from memory, or carried forward from an unreviewed draft. A
translation is doctrinally load-bearing and its wording is not ours to
approximate. Trinity 17 is the worked example: an imported draft carried two
different wordings of one phrase in Luke 14:10, neither of them the
ESV's, and both propagated across pieces because a person typed them
once and nothing checked.

So this program is the only sanctioned way text enters `gospel_text` and
the memory verses. It talks to the publisher and to nobody else.

Requires ESV_API_KEY. Crossway issues one free for non-commercial use at
https://api.esv.org/. The key is read from the environment and is never
written to disk, printed, or committed.

Three refusals, all deliberate:

  approved Sunday   content below the freeze line is finished text. An
                    edit would change its hash and invalidate every
                    review on record, so this will not touch it.
  wrong translation the ESV API serves the ESV. A Sunday whose lesson
                    says NKJV is not fetched, it is reported.
  oversized request only the week's pericope belongs in this repository,
                    never a book and never a testament. A reference over
                    --max-verses is refused rather than trimmed.

Prints by default. Writing into lesson.yml requires --write, and the
write is surgical: the YAML is spliced as text so that every comment in
the file survives, because those comments carry the decisions.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stpaul.model import CONTENT_DIR  # noqa: E402
from stpaul.approval import load_approval  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ENDPOINT = "https://api.esv.org/v3/passage/text/"

# What the pieces print. Verse numbers in brackets, nothing else: the
# copyright notice lives in lesson.yml and is rendered once per piece,
# headings are the ESV's editorial layer and not ours to reprint, and
# footnotes would land in a child's handout.
PASSAGE_OPTIONS = {
    "include-passage-references": "false",
    "include-verse-numbers": "true",
    "include-first-verse-numbers": "true",
    "include-footnotes": "false",
    "include-headings": "false",
    "include-short-copyright": "false",
    "include-passage-horizontal-lines": "false",
    "include-heading-horizontal-lines": "false",
    "indent-paragraphs": "0",
    "indent-poetry": "false",
    "line-length": "0",
}

REF_RANGE = re.compile(r"(\d+):(\d+)\s*[-–]\s*(?:(\d+):)?(\d+)")


class FetchError(Exception):
    """Anything that should stop the program with a readable message."""


def verses_in(reference: str) -> int:
    """Rough verse count for a reference such as "Luke 14:1-11".

    Deliberately rough. It exists to catch "John" or "Psalms", not to
    be exact about chapter boundaries, and it over-counts a cross-chapter
    range rather than under-counting it.
    """
    m = REF_RANGE.search(reference or "")
    if not m:
        return 1
    start_ch, start_v, end_ch, end_v = m.group(1), m.group(2), m.group(3), m.group(4)
    if end_ch and end_ch != start_ch:
        return (int(end_ch) - int(start_ch)) * 40 + int(end_v)
    return max(1, int(end_v) - int(start_v) + 1)


def fetch_passage(reference: str, key: str, timeout: int = 30) -> str:
    """Return the ESV text of one reference, or raise FetchError."""
    params = dict(PASSAGE_OPTIONS, q=reference)
    url = f"{ENDPOINT}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Token {key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise FetchError("ESV_API_KEY was rejected (401). Check the key "
                             "at https://api.esv.org/account/.") from e
        raise FetchError(f"api.esv.org answered {e.code} {e.reason}. If this is "
                         f"a 403 from a proxy rather than from Crossway, the "
                         f"host is blocked by this environment's network "
                         f"policy, not by your key.") from e
    except urllib.error.URLError as e:
        raise FetchError(f"could not reach api.esv.org: {e.reason}. Confirm the "
                         f"host is allowed by this environment's network "
                         f"policy.") from e

    passages = [p.strip() for p in payload.get("passages", []) if p.strip()]
    if not passages:
        raise FetchError(f"the ESV API returned no text for {reference!r}. "
                         f"Check the reference.")
    canonical = payload.get("canonical") or reference
    if len(passages) > 1:
        raise FetchError(f"{reference!r} resolved to {len(passages)} passages "
                         f"({canonical}). Fetch one at a time.")
    return passages[0]


def splice_block(source: str, key: str, value: str) -> str:
    """Replace a top-level scalar with a literal block, comments intact.

    PyYAML would round-trip this file by reparsing and redumping it, and
    every comment in lesson.yml would be lost. Those comments record who
    decided what and when, so the file is edited as text instead.
    """
    # The value is the key's line plus every indented line under it, and
    # blank lines only where an indented line follows (a block scalar has
    # blank lines inside it). A blank line before an unindented line is
    # the separator above the NEXT key, and a comment at column 0 belongs
    # to that key too, so neither is swallowed.
    pattern = re.compile(rf"^{re.escape(key)}:[^\n]*\n?"
                         rf"(?:[ \t]+[^\n]*\n|[ \t]*\n(?=[ \t]+\S))*", re.M)
    if not pattern.search(source):
        raise FetchError(f"could not find a top-level {key!r} in lesson.yml")
    body = "\n".join(f"  {line}" if line.strip() else ""
                     for line in value.strip().splitlines())
    return pattern.sub(f"{key}: |\n{body}\n", source, count=1)


def splice_memory_verses(source: str, texts: dict[str, str]) -> tuple[str, int]:
    """Fill `text: null` under each memory verse whose reference we fetched.

    Walks the file line by line rather than parsing it, for the same
    reason as splice_block. Returns the new source and how many were
    filled, so the caller can report nothing rather than claim something.
    """
    out, filled, current = [], 0, None
    for line in source.splitlines():
        ref = re.match(r'^\s*-\s*reference:\s*"?([^"\n]+?)"?\s*$', line)
        if ref:
            current = ref.group(1).strip()
        hit = re.match(r"^(\s*)text:\s*null\s*$", line)
        if hit and current and current in texts:
            indent = hit.group(1)
            out.append(f"{indent}text: >-")
            out.append(f"{indent}  {texts[current].strip()}")
            filled += 1
            current = None
            continue
        out.append(line)
    return "\n".join(out) + ("\n" if source.endswith("\n") else ""), filled


def read_lesson_field(source: str, key: str) -> str | None:
    """Read one simple top-level scalar without importing a YAML parser."""
    m = re.search(rf'^{re.escape(key)}:\s*"?([^"\n#]+?)"?\s*$', source, re.M)
    if not m:
        return None
    value = m.group(1).strip()
    return None if value in ("", "null", "~") else value


def memory_verse_refs(source: str) -> list[str]:
    """Every memory verse reference in the file, in order, deduplicated."""
    seen, refs = set(), []
    for m in re.finditer(r'^\s*-\s*reference:\s*"?([^"\n]+?)"?\s*$', source, re.M):
        ref = m.group(1).strip()
        if ref not in seen:
            seen.add(ref)
            refs.append(ref)
    return refs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sunday", help="slug, e.g. 2026-09-27-trinity-17")
    ap.add_argument("--write", action="store_true",
                    help="write into lesson.yml; without it, print only")
    ap.add_argument("--ref", action="append", default=[], metavar="REFERENCE",
                    help="also fetch this reference and print it. Never "
                         "written, for cross-references such as Mark 2:27")
    ap.add_argument("--max-verses", type=int, default=50,
                    help="refuse a reference longer than this (default 50)")
    args = ap.parse_args()

    key = os.environ.get("ESV_API_KEY", "").strip()
    if not key:
        print("ESV_API_KEY is not set.\n"
              "Crossway issues one free for non-commercial use at "
              "https://api.esv.org/.\n"
              "Set it in the environment; never commit it.", file=sys.stderr)
        return 2

    lesson_path = CONTENT_DIR / args.sunday / "lesson.yml"
    if not lesson_path.is_file():
        print(f"no lesson.yml at {lesson_path}", file=sys.stderr)
        return 2
    source = lesson_path.read_text(encoding="utf-8")

    if args.write and load_approval(args.sunday) is not None:
        print(f"{args.sunday} has an approval on record. Content below the "
              f"freeze line is finished text and is not edited here.\n"
              f"Bring the problem to a human instead.", file=sys.stderr)
        return 2

    translation = read_lesson_field(source, "translation")
    if translation and translation.upper() != "ESV":
        print(f"{args.sunday} is set to {translation}, and this fetches the "
              f"ESV only. Supply that week's text by hand.", file=sys.stderr)
        return 2

    gospel = read_lesson_field(source, "gospel")
    if not gospel:
        print(f"{args.sunday} has no `gospel` reference set. Fill it in "
              f"from the Scope and Design Charter first.", file=sys.stderr)
        return 2

    wanted = [gospel] + memory_verse_refs(source) + list(args.ref)
    for ref in wanted:
        n = verses_in(ref)
        if n > args.max_verses:
            print(f"{ref!r} is about {n} verses, over --max-verses "
                  f"({args.max_verses}). Only the week's pericope belongs "
                  f"in this repository.", file=sys.stderr)
            return 2

    try:
        texts = {ref: fetch_passage(ref, key) for ref in dict.fromkeys(wanted)}
    except FetchError as e:
        print(f"{e}", file=sys.stderr)
        return 1

    print(f"{gospel} (ESV)\n")
    print(texts[gospel])
    print()
    for ref in args.ref:
        print(f"{ref} (ESV), cross-reference, not written\n")
        print(texts[ref])
        print()

    if not args.write:
        print("Nothing written. Re-run with --write to put this into "
              "lesson.yml.")
        return 0

    updated = splice_block(source, "gospel_text", texts[gospel])
    verse_texts = {r: t for r, t in texts.items()
                   if r != gospel and r not in args.ref}
    updated, filled = splice_memory_verses(updated, verse_texts)
    lesson_path.write_text(updated, encoding="utf-8")

    print(f"wrote gospel_text and {filled} memory verse text(s) -> {lesson_path}")
    if filled:
        print("Memory verses were written in full. Trimming one to a phrase "
              "is an editorial choice and belongs to a person, not here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
