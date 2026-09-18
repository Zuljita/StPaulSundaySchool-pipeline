#!/usr/bin/env python
"""Fill each Sunday's Scripture in lesson.yml from Crossway's ESV API.

This runs on GitHub Actions, in the data repository's fetch-scripture
workflow, whenever a lesson.yml is pushed. Nobody runs it by hand, and
nobody should be asked to: it needs a Crossway API key, and that key is an
Actions secret in the data repository and lives nowhere else. Off a runner
it refuses unless given --local, which is for working on this tool.

    python tools/fetch_scripture.py 2026-09-27-trinity-17 --write
    python tools/fetch_scripture.py --all --local      # report only

WHAT IT FILLS

Every passage lesson.yml declares, each beside its own text:

    gospel: "Luke 14:1-11"            ->  gospel_text
    memory_verses:
      pre_k:
        - reference: "Luke 14:10"     ->  text
    cross_references:
      - reference: "Mark 2:27"        ->  text

A text that is null is filled. A text whose words are not the publisher's
is replaced, so a hand edit to Scripture does not survive the next push. A
text that already has the publisher's words is left exactly as it is, and
for a memory verse or a cross-reference that includes a phrase trimmed out
of the verse: trimming is an editorial choice, changing a word is not.

WHY

Scripture was the one input with no sanctioned route into the curriculum.
It got retyped, and Trinity 17 showed the cost: an imported draft carried
two different wordings of one phrase in Luke 14:10, neither of them the
ESV's. Now lesson.yml holds the publisher's text, and the
scripture_quotations rule holds every piece to it.

WHAT IT WILL NOT DO

  approved Sunday    An approval on record puts the Sunday below the
                     freeze line. It is reported and never touched.
  other translation  The ESV API serves the ESV. A Sunday that declares
                     another translation, or none, is reported and skipped.
  loose reference    "Luke 14" or "John" is not a passage. A reference
                     must name one passage and its verses.
  oversized passage  More verses than --max-verses, counted in the text
                     Crossway returns, is refused rather than stored.

HOW IT WRITES

lesson.yml's comments record who decided what and when, and a PyYAML
round trip would delete every one of them. So the file is edited in place:
PyYAML finds each value, only those characters change, and the result is
parsed again and compared with what was intended. If the new file does not
read back as the old one with exactly the new passages in it, nothing is
written and the run fails.

Verse numbers are written the way the approved pieces print them, a bare
number before each verse, and a single verse carries none.

It reports references, verse counts and what changed, never the text.
Actions keeps its logs, and Scripture belongs in lesson.yml, not in a log.
--show prints the text, for work on this tool.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from stpaul import runner  # noqa: E402
from stpaul.approval import APPROVED, load_approval  # noqa: E402
from stpaul.model import APPROVALS_DIR, CONTENT_DIR, all_sundays  # noqa: E402
from stpaul.scripture import (VERSE_MARK, Ref, is_excerpt,  # noqa: E402
                              lesson_passages, words)

TRANSLATION = "ESV"
ENDPOINT = "https://api.esv.org/v3/passage/text/"

# Plain text with verse numbers and nothing else. Headings are Crossway's
# editorial layer rather than the text, footnotes would land in a child's
# handout, and the copyright notice travels with each piece, as rules.yml
# requires, rather than glued to the passage. Every indent is zeroed, so
# what comes back is words, verse numbers and paragraph breaks.
PASSAGE_OPTIONS = {
    "include-passage-references": "false",
    "include-verse-numbers": "true",
    "include-first-verse-numbers": "true",
    "include-footnotes": "false",
    "include-footnote-body": "false",
    "include-headings": "false",
    "include-short-copyright": "false",
    "include-copyright": "false",
    "include-passage-horizontal-lines": "false",
    "include-heading-horizontal-lines": "false",
    "include-selahs": "true",
    "indent-paragraphs": "0",
    "indent-poetry": "false",
    "indent-declares": "0",
    "indent-psalm-doxology": "0",
    "line-length": "0",
}

# A run fetches a handful of passages. There is no reason to arrive at
# Crossway with all of them at once.
PACE_SECONDS = 0.5

SLUG = re.compile(r"\d{4}-\d{2}-\d{2}-[a-z0-9-]+")
_BLOCK_HEADER = re.compile(r"[|>][-+0-9]*(?P<comment>[ \t]+#.*)?")


class FetchError(Exception):
    """A passage could not be fetched. The message says what to do about it."""


class MissingKey(FetchError):
    """There is no key, so nothing can be fetched at all."""


class SpliceError(Exception):
    """lesson.yml could not be rewritten safely, so it was not rewritten."""


# ---------------------------------------------------------------------
# Crossway
# ---------------------------------------------------------------------

def fetch_passage(reference: str, key: str, timeout: int = 30) -> str:
    """Crossway's plain text for one reference, as it comes back."""
    query = urllib.parse.urlencode(dict(PASSAGE_OPTIONS, q=reference))
    request = urllib.request.Request(f"{ENDPOINT}?{query}",
                                     headers={"Authorization": f"Token {key}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise FetchError(
                f"api.esv.org refused the key ({e.code}). The ESV_API_KEY secret in the "
                f"data repository is wrong or has been revoked, and replacing it is a "
                f"repository admin's job.") from e
        if e.code == 429:
            raise FetchError("api.esv.org is rate-limiting this key (429). "
                             "Re-run the workflow later.") from e
        raise FetchError(f"api.esv.org answered {e.code} {e.reason}.") from e
    except (urllib.error.URLError, OSError) as e:
        raise FetchError(f"could not reach api.esv.org: {getattr(e, 'reason', e)}.") from e
    except ValueError as e:
        raise FetchError("api.esv.org answered with something that is not JSON.") from e

    passages = [p for p in payload.get("passages") or [] if isinstance(p, str) and p.strip()]
    if not passages:
        raise FetchError(f"Crossway returned no text for {reference!r}. Check the reference.")
    if len(passages) > 1:
        raise FetchError(f"{reference!r} came back as {len(passages)} separate passages. "
                         f"Declare each one on its own line.")
    return passages[0]


class Crossway:
    """What the workflow fetches with: one request per reference per run, paced."""

    def __init__(self, key: str | None, pace: float = PACE_SECONDS):
        self.key = key
        self.pace = pace
        self.cache: dict[str, str] = {}
        self.last = 0.0

    def __call__(self, reference: str) -> str:
        wanted = " ".join(reference.split())
        if wanted not in self.cache:
            if not self.key:
                raise MissingKey(
                    "ESV_API_KEY is not set. On GitHub Actions it comes from the data "
                    "repository's Actions secrets, and adding it is a repository admin's "
                    "job. Nothing else is needed from anyone.")
            wait = self.pace - (time.monotonic() - self.last)
            if self.last and wait > 0:
                time.sleep(wait)
            try:
                self.cache[wanted] = fetch_passage(wanted, self.key)
            finally:
                self.last = time.monotonic()
        return self.cache[wanted]


def shape(raw: str, ref: Ref) -> tuple[str, int]:
    """Crossway's text as lesson.yml stores it, and how many verses it holds."""
    verses = len(VERSE_MARK.findall(raw))
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    for separator in (" ", " ", "\x85"):
        text = text.replace(separator, "\n")
    text = VERSE_MARK.sub("" if ref.single_verse else r"\1", text)
    lines: list[str] = []
    for line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            lines.append(line)
        elif lines and lines[-1]:
            lines.append("")
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines), verses


def check_length(reference: str, ref: Ref, verses: int, max_verses: int) -> None:
    """Refuse a reply that does not hold what the reference asked for."""
    if verses == 0:
        raise FetchError(
            f"Crossway's reply for {reference!r} carried no verse numbers, so what it "
            f"holds cannot be counted. The API's format may have changed. Nothing was "
            f"stored.")
    expected = ref.verse_count
    if expected is not None and verses != expected:
        raise FetchError(f"{reference!r} names {expected} verse(s), but Crossway returned "
                         f"{verses}. Nothing was stored.")
    if verses > max_verses:
        raise FetchError(f"{reference!r} is {verses} verses, over --max-verses "
                         f"({max_verses}). Only what the Sunday prints belongs in the "
                         f"data repository.")


# ---------------------------------------------------------------------
# Writing lesson.yml without losing a comment
# ---------------------------------------------------------------------

def _get(mapping: yaml.Node, key: str):
    if isinstance(mapping, yaml.MappingNode):
        for k, v in mapping.value:
            if isinstance(k, yaml.ScalarNode) and k.value == key:
                return k, v
    return None


def locate(source: str) -> dict[str, tuple[yaml.Node, yaml.Node, yaml.Node]]:
    """Where each passage's text sits: field -> (mapping, key node, value node)."""
    root = yaml.compose(source)
    if not isinstance(root, yaml.MappingNode):
        raise SpliceError("lesson.yml is not a mapping")
    slots = {}
    found = _get(root, "gospel_text")
    if found:
        slots["gospel_text"] = (root, *found)
    verses = _get(root, "memory_verses")
    if verses and isinstance(verses[1], yaml.MappingNode):
        for level, items in verses[1].value:
            seq = items.value if isinstance(items, yaml.SequenceNode) else [items]
            for i, item in enumerate(seq):
                text = _get(item, "text")
                if text:
                    slots[f"memory_verses.{level.value}[{i}]"] = (item, *text)
    cross = _get(root, "cross_references")
    if cross and isinstance(cross[1], yaml.SequenceNode):
        for i, item in enumerate(cross[1].value):
            text = _get(item, "text")
            if text:
                slots[f"cross_references[{i}]"] = (item, *text)
    return slots


def render(source: str, mapping: yaml.Node, key: yaml.Node, value: yaml.Node,
           text: str) -> tuple[int, int, str]:
    """The replacement for one value, as (start, end, new characters)."""
    start, end = value.start_mark.index, value.end_mark.index
    if mapping.flow_style:
        # Inside {...} a block scalar cannot stand. A JSON string is a valid
        # YAML double-quoted scalar.
        return start, end, json.dumps(text, ensure_ascii=False)

    comment, tail = "", ""
    original = source[start:end]
    if isinstance(value, yaml.ScalarNode) and value.style in ("|", ">"):
        header = _BLOCK_HEADER.match(original.split("\n", 1)[0])
        comment = (header.group("comment") or "") if header else ""
        # A block value's span runs on through the line breaks after its last
        # line. They separate it from the next key, so they stay.
        body = original.rstrip("\n")
        tail = original[len(body):]
    else:
        line_end = source.find("\n", end)
        line_end = len(source) if line_end < 0 else line_end
        rest = source[end:line_end]
        if rest.strip().startswith("#"):
            # A comment after a one-line value would end up inside the new
            # block as text. It moves up beside the block indicator, where it
            # is still a comment.
            comment, end = rest, line_end
    lead = "" if source[start - 1:start] in (" ", "\t", "\n") else " "
    indent = " " * (key.start_mark.column + 2)
    lines = "\n".join(indent + line if line else "" for line in text.split("\n"))
    return start, end, f"{lead}|-{comment}\n{lines}{tail}"


def apply(source: str, texts: dict[str, str]) -> str:
    """`source` with each field's text put in place, and nothing else touched."""
    slots = locate(source)
    edits, append = [], None
    for name, text in texts.items():
        if name in slots:
            edits.append(render(source, *slots[name], text))
        elif name == "gospel_text":
            append = text
        else:
            raise SpliceError(f"{name} has a reference but no text: key beside it")
    out = source
    for start, end, new in sorted(edits, reverse=True):
        out = out[:start] + new + out[end:]
    if append is not None:
        if out and not out.endswith("\n"):
            out += "\n"
        body = "\n".join("  " + line if line else "" for line in append.split("\n"))
        out += f"gospel_text: |-\n{body}\n"
    return out


def _problem(error: yaml.YAMLError) -> str:
    """A YAML error without the lines of the file PyYAML quotes, which may be Scripture."""
    mark = getattr(error, "problem_mark", None)
    where = f" at line {mark.line + 1}" if mark else ""
    return f"{getattr(error, 'problem', None) or type(error).__name__}{where}"


def _put(data: dict, name: str, text: str) -> None:
    if name == "gospel_text":
        data["gospel_text"] = text
        return
    m = re.fullmatch(r"memory_verses\.(.+)\[(\d+)\]", name)
    if m:
        verses = data["memory_verses"]
        items = verses[next(k for k in verses if str(k) == m.group(1))]
        (items if isinstance(items, dict) else items[int(m.group(2))])["text"] = text
        return
    m = re.fullmatch(r"cross_references\[(\d+)\]", name)
    data["cross_references"][int(m.group(1))]["text"] = text


def _comments(source: str) -> Counter:
    return Counter(line.strip() for line in source.splitlines()
                   if line.lstrip().startswith("#"))


def verify_rewrite(before: str, after: str, texts: dict[str, str]) -> None:
    """Refuse unless `after` reads as `before` with exactly `texts` put in."""
    try:
        old, new = yaml.safe_load(before), yaml.safe_load(after)
    except yaml.YAMLError as e:
        raise SpliceError(f"the rewritten file does not parse ({_problem(e)})") from e
    if not isinstance(new, dict):
        raise SpliceError("the rewritten file is not a mapping")
    want = copy.deepcopy(old)
    for name, text in texts.items():
        _put(want, name, text)
    if new != want:
        differ = sorted(str(k) for k in set(want) | set(new) if want.get(k) != new.get(k))
        raise SpliceError(f"the rewritten file does not read back as intended "
                          f"(it differs at {', '.join(differ)})")
    lost = _comments(before) - _comments(after)
    if lost:
        raise SpliceError(f"the rewrite would lose {sum(lost.values())} comment line(s)")


# ---------------------------------------------------------------------
# One Sunday
# ---------------------------------------------------------------------

@dataclass
class Line:
    name: str
    reference: str
    verses: int = 0
    status: str = ""        # filled, replaced, kept or failed
    note: str = ""
    text: str = ""


@dataclass
class Result:
    slug: str
    outcome: str = "checked"    # checked, skipped or failed
    note: str = ""
    lines: list[Line] = field(default_factory=list)
    new_source: str | None = None
    path: Path | None = None

    @property
    def failed(self) -> bool:
        return self.outcome == "failed" or any(l.status == "failed" for l in self.lines)


def approved(slug: str, approvals_dir: Path = APPROVALS_DIR) -> bool:
    """Does this Sunday's record hold an approval, current or not?

    A record holding only requests for changes freezes nothing: that is
    exactly when a passage may need fetching again.
    """
    record = load_approval(slug, approvals_dir) or {}
    return any(r.get("decision") == APPROVED for r in record.get("reviews", []))


def keeps(name: str, current: str, fetched: str) -> bool:
    """Does the text already there have the publisher's words?

    The Gospel must be the whole pericope, in any layout. A memory verse or a
    cross-reference may be a phrase trimmed out of the verse.
    """
    if name == "gospel_text":
        return words(current) == words(fetched)
    return is_excerpt(current, fetched)


def process(slug: str, fetch: Callable[[str], str], *, content_dir: Path = CONTENT_DIR,
            approvals_dir: Path = APPROVALS_DIR, max_verses: int = 50) -> Result:
    """Work out what one Sunday's lesson.yml should hold. Writes nothing."""
    path = content_dir / slug / "lesson.yml"
    result = Result(slug, path=path)
    if not path.is_file():
        result.outcome, result.note = "failed", "there is no lesson.yml"
        return result
    source = path.read_text(encoding="utf-8")
    try:
        meta = yaml.safe_load(source)
        slots = locate(source)
    except yaml.YAMLError as e:
        result.outcome, result.note = "failed", f"lesson.yml does not parse ({_problem(e)})"
        return result
    except SpliceError as e:
        result.outcome, result.note = "failed", str(e)
        return result

    if approved(slug, approvals_dir):
        result.outcome = "skipped"
        result.note = "has an approval on record, so it is below the freeze line and is not touched"
        return result
    declared = str(meta.get("translation") or "").strip()
    if declared.upper() != TRANSLATION:
        result.outcome = "skipped"
        result.note = (f"declares {declared}, and the ESV API serves only the ESV" if declared
                       else "declares no translation, so there is nothing to fetch")
        return result
    passages = lesson_passages(meta)
    if not passages:
        result.outcome, result.note = "skipped", "declares no passages"
        return result

    texts: dict[str, str] = {}
    for passage in passages:
        line = Line(passage.field, passage.reference)
        result.lines.append(line)
        if passage.ref is None:
            line.status = "failed"
            line.note = 'does not name one passage and its verses, like "Luke 14:1-11"'
            continue
        if passage.field != "gospel_text" and passage.field not in slots:
            line.status, line.note = "failed", "has no text: beside its reference; add text: null"
            continue
        try:
            text, verses = shape(fetch(passage.reference), passage.ref)
            check_length(passage.reference, passage.ref, verses, max_verses)
        except MissingKey as e:
            result.outcome, result.note, result.lines = "failed", str(e), []
            return result
        except FetchError as e:
            line.status, line.note = "failed", str(e)
            continue
        line.verses, line.text = verses, text
        if passage.text is None:
            line.status = "filled"
        elif keeps(passage.field, passage.text, text):
            line.status = "kept"
            continue
        else:
            line.status = "replaced"
        texts[passage.field] = text

    if texts:
        try:
            new_source = apply(source, texts)
            verify_rewrite(source, new_source, texts)
        except (SpliceError, yaml.YAMLError) as e:
            detail = _problem(e) if isinstance(e, yaml.YAMLError) else str(e)
            result.outcome, result.note = "failed", f"lesson.yml was not rewritten: {detail}"
            return result
        result.new_source = new_source
    return result


# ---------------------------------------------------------------------
# Reporting, without the text
# ---------------------------------------------------------------------

def report(result: Result, *, write: bool = False, show: bool = False) -> str:
    out = [result.slug]
    name_w = max((len(l.name) for l in result.lines), default=0)
    ref_w = max((len(l.reference) for l in result.lines), default=0)
    for l in result.lines:
        count = f"{l.verses} verse{'' if l.verses == 1 else 's'}" if l.verses else ""
        note = f": {l.note}" if l.note else ""
        out.append(f"  {l.name:<{name_w}}  {l.reference:<{ref_w}}  {count:>9}  {l.status}{note}")
    if result.note:
        out.append(f"  {result.outcome}: {result.note}")
    if result.new_source is not None:
        out.append("  -> wrote lesson.yml" if write else "  -> would write lesson.yml; pass --write")
    if show:
        for l in result.lines:
            if l.text:
                out += ["", f"  {l.reference} ({TRANSLATION})"]
                out += [f"    {t}" for t in l.text.split("\n")]
    return "\n".join(out)


def summary(results: list[Result], write: bool) -> str:
    """The run as a Markdown table, for the Actions job summary."""
    rows = ["### Scripture from Crossway", "",
            "| Sunday | Passage | Reference | Verses | Result |",
            "|---|---|---|---|---|"]
    for r in results:
        for l in r.lines:
            note = f": {l.note}" if l.note else ""
            rows.append(f"| {r.slug} | `{l.name}` | {l.reference} | {l.verses or ''} "
                        f"| {l.status}{note} |")
        if r.note:
            rows.append(f"| {r.slug} | | | | {r.outcome}: {r.note} |")
        if r.new_source is not None:
            rows.append(f"| {r.slug} | | | | {'wrote' if write else 'would write'} lesson.yml |")
    return "\n".join(rows) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sunday", nargs="*", help="Sunday slug(s)")
    ap.add_argument("--all", action="store_true", help="every Sunday under content/")
    ap.add_argument("--write", action="store_true",
                    help="write lesson.yml; without it, report only")
    ap.add_argument("--show", action="store_true",
                    help="print the fetched text, for work on this tool")
    ap.add_argument("--max-verses", type=int, default=50,
                    help="refuse a passage longer than this (default 50)")
    runner.add_local_flag(ap)
    args = ap.parse_args(argv)

    refused = runner.refusal(
        "fetch_scripture.py",
        "The data repository's fetch-scripture workflow runs it on every push that "
        "changes a lesson.yml.", args.local)
    if refused:
        print(refused, file=sys.stderr)
        return 2
    if bool(args.sunday) == args.all:
        ap.error("name one or more Sundays, or pass --all")
    slugs = all_sundays() if args.all else args.sunday
    bad = [s for s in slugs if not SLUG.fullmatch(s)]
    if bad:
        ap.error(f"not a Sunday: {', '.join(bad)}")

    fetch = Crossway(os.environ.get("ESV_API_KEY", "").strip() or None)
    results = []
    for slug in slugs:
        result = process(slug, fetch, max_verses=args.max_verses)
        if args.write and result.new_source is not None:
            result.path.write_text(result.new_source, encoding="utf-8", newline="\n")
        print(report(result, write=args.write, show=args.show) + "\n")
        results.append(result)

    job_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if job_summary:
        with open(job_summary, "a", encoding="utf-8") as f:
            f.write(summary(results, args.write))
    return 1 if any(r.failed for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
