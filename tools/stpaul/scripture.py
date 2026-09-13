"""Bible references, and when two renderings of a passage are the same words.

Two parts of the pipeline have to agree about this. tools/fetch_scripture.py
writes the publisher's text into lesson.yml, and the quotation check in
rules.py holds every piece to that text. They share this module so that
neither can quietly come to a different answer.

Nothing here reads a file, the network or the clock. The rule engine
imports it, and the rule engine sits below the freeze line.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass

_BOOKS = """
genesis exodus leviticus numbers deuteronomy joshua judges ruth
1_samuel 2_samuel 1_kings 2_kings 1_chronicles 2_chronicles ezra nehemiah
esther job psalms proverbs ecclesiastes song_of_solomon isaiah jeremiah
lamentations ezekiel daniel hosea joel amos obadiah jonah micah nahum
habakkuk zephaniah haggai zechariah malachi matthew mark luke john acts
romans 1_corinthians 2_corinthians galatians ephesians philippians
colossians 1_thessalonians 2_thessalonians 1_timothy 2_timothy titus
philemon hebrews james 1_peter 2_peter 1_john 2_john 3_john jude revelation
"""
BOOKS = frozenset(b.replace("_", " ") for b in _BOOKS.split())
_ALIASES = {"psalm": "psalms", "song of songs": "song of solomon"}

# One or two capitalised words, with an optional number in front
# ("1 Corinthians") or "of" in the middle ("Song of Solomon"), then
# chapter:verse and an optional range. Which of the words is really the
# book is settled against BOOKS afterwards, so "See John 3:16" finds John.
REFERENCE = re.compile(
    r"(?P<book>(?:[1-3]\s?)?[A-Z][a-z]+(?:\s(?:of\s)?[A-Z][a-z]+)?)\.?\s+"
    r"(?P<ch>\d+):(?P<v1>\d+)[a-z]?"
    r"(?:\s*[-–—]\s*(?:(?P<ch2>\d+):)?(?P<v2>\d+)[a-z]?)?"
    r"(?![\d:])"
)


@dataclass(frozen=True)
class Ref:
    """A passage: one book and an inclusive (chapter, verse) range."""

    book: str
    start: tuple[int, int]
    end: tuple[int, int]

    def covers(self, other: "Ref") -> bool:
        return (self.book == other.book
                and self.start <= other.start and other.end <= self.end)

    @property
    def single_verse(self) -> bool:
        return self.start == self.end

    @property
    def verse_count(self) -> int | None:
        """Verses in the range, when the reference alone can say.

        A range that crosses a chapter boundary cannot: nothing here knows
        how long a chapter is.
        """
        if self.start[0] != self.end[0]:
            return None
        return self.end[1] - self.start[1] + 1

    def __str__(self) -> str:
        book = " ".join(w if w[0].isdigit() or w == "of" else w.capitalize()
                        for w in self.book.split())
        head = f"{book} {self.start[0]}:{self.start[1]}"
        if self.single_verse:
            return head
        if self.start[0] == self.end[0]:
            return f"{head}-{self.end[1]}"
        return f"{head}-{self.end[0]}:{self.end[1]}"


def _book(name: str, *, strict: bool) -> str | None:
    parts = name.lower().split()
    starts = [0] if strict else range(len(parts))
    for start in starts:
        candidate = " ".join(parts[start:])
        candidate = re.sub(r"^([1-3])(?=[a-z])", r"\1 ", candidate)
        candidate = _ALIASES.get(candidate, candidate)
        if candidate in BOOKS:
            return candidate
    return None


def _ref(m: re.Match, *, strict: bool = False) -> Ref | None:
    book = _book(m.group("book"), strict=strict)
    if book is None:
        return None
    start = (int(m.group("ch")), int(m.group("v1")))
    if m.group("v2") is None:
        end = start
    else:
        end = (int(m.group("ch2")) if m.group("ch2") else start[0], int(m.group("v2")))
    if end < start:
        return None
    return Ref(book, start, end)


def find_references(text: str) -> list[tuple[Ref, int, int]]:
    """Every reference in `text`, with the span it occupies."""
    out = []
    for m in REFERENCE.finditer(text or ""):
        ref = _ref(m)
        if ref:
            out.append((ref, m.start(), m.end()))
    return out


def parse_reference(text: str) -> Ref | None:
    """The first reference anywhere in `text`, or None."""
    found = find_references(text)
    return found[0][0] if found else None


def parse_exact_reference(text: str) -> Ref | None:
    """`text` as exactly one reference and nothing else, or None.

    What lesson.yml declares has to be a single passage that names its
    verses. "Luke 14" and "John" are not one, and neither is
    "Luke 14:1-6, 7-11", which is two.
    """
    m = REFERENCE.fullmatch((text or "").strip())
    return _ref(m, strict=True) if m else None


# ---------------------------------------------------------------------
# Comparing words
# ---------------------------------------------------------------------

_VERSE_MARK = re.compile(r"\[\d+(?::\d+)?\]")
_WORD = re.compile(r"[a-z]+(?:'[a-z]+)*")
_ELLIPSIS = re.compile(r"\.\s?\.\s?\.")
_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'"})


def words(text: str) -> list[str]:
    """The words of a passage, for comparing two renderings of it.

    Case, punctuation, quotation marks, emphasis markup, verse numbers and
    line breaks are not words, so they do not count: "FRIEND, move up
    higher" on a Pre-K craft page is the same words as the verse. A
    changed, added, dropped or reordered word is a different text.
    """
    t = unicodedata.normalize("NFKC", text or "").translate(_APOSTROPHES)
    t = _VERSE_MARK.sub(" ", t)
    return _WORD.findall(t.lower())


def _index(hay: list[str], needle: list[str], start: int = 0) -> int:
    n = len(needle)
    for i in range(start, len(hay) - n + 1):
        if hay[i:i + n] == needle:
            return i
    return -1


def is_excerpt(quoted: str, passage: str) -> bool:
    """Is `quoted` the passage's own words, contiguous and in order?

    An ellipsis may stand for words left out between two runs. Nothing else
    may, so a verse trimmed to a phrase is an excerpt and a verse with one
    word changed is not.
    """
    hay = words(passage)
    parts = _ELLIPSIS.split(unicodedata.normalize("NFKC", quoted or ""))
    runs = [w for w in (words(p) for p in parts) if w]
    if not runs:
        return False
    pos = 0
    for run in runs:
        i = _index(hay, run, pos)
        if i < 0:
            return False
        pos = i + len(run)
    return True


def overlap(quoted: str, passage: str) -> float:
    """How much of `quoted` is recognisably the passage, from 0 to 1.

    The share of the quotation's words that sit in runs it shares, in order,
    with the passage. A run has to be three words long, or two in a short
    quotation, so a shared "of the" is not resemblance. One changed word in
    the middle of a long paragraph leaves nearly all of it in shared runs;
    an instruction printed beside the passage shares almost none.

    It measures runs rather than the single longest run on purpose. The
    longest run halves when a word in the middle changes, and a misquotation
    in the middle of a paragraph then looked like no quotation at all.
    """
    q, hay = words(quoted), words(passage)
    if not q:
        return 0.0
    shortest = 2 if len(q) < 8 else 3
    blocks = difflib.SequenceMatcher(None, q, hay, autojunk=False).get_matching_blocks()
    return sum(b.size for b in blocks if b.size >= shortest) / len(q)


def agreement(quoted: str, passage: str) -> int:
    """How many of the quotation's opening words the passage also has, in a row.

    Tells a person where a misquotation starts to go wrong.
    """
    q, hay = words(quoted), words(passage)
    best = 0
    for i in range(len(hay)):
        n = 0
        while n < len(q) and i + n < len(hay) and hay[i + n] == q[n]:
            n += 1
        best = max(best, n)
    return best


def first_words(text: str, n: int = 8) -> str:
    """The opening words of a quotation, to point at it without reprinting it."""
    w = (text or "").split()
    return " ".join(w[:n]) + (" ..." if len(w) > n else "")


# ---------------------------------------------------------------------
# What a Sunday declares
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class Passage:
    """One passage lesson.yml declares, and its text once fetched."""

    field: str          # where the text lives, e.g. "memory_verses.pre_k[0]"
    reference: str      # as written in lesson.yml
    ref: Ref | None     # None when the reference is not a single passage
    text: str | None    # None until fetched


def _text(value) -> str | None:
    if value is None:
        return None
    s = str(value)
    return s if s.strip() else None


def lesson_passages(meta: dict) -> list[Passage]:
    """Every passage a lesson declares, in file order.

        gospel: "Luke 14:1-11"             text in gospel_text
        memory_verses.<level>[i].reference text beside it
        cross_references[i].reference      text beside it
    """
    out: list[Passage] = []

    gospel = meta.get("gospel")
    if isinstance(gospel, str) and gospel.strip():
        out.append(Passage("gospel_text", gospel, parse_exact_reference(gospel),
                           _text(meta.get("gospel_text"))))

    verses = meta.get("memory_verses")
    if isinstance(verses, dict):
        for level, items in verses.items():
            if isinstance(items, dict):
                items = [items]
            if not isinstance(items, list):
                continue
            for i, item in enumerate(items):
                if isinstance(item, dict) and isinstance(item.get("reference"), str):
                    ref = item["reference"]
                    out.append(Passage(f"memory_verses.{level}[{i}]", ref,
                                       parse_exact_reference(ref), _text(item.get("text"))))

    cross = meta.get("cross_references")
    if isinstance(cross, list):
        for i, item in enumerate(cross):
            if isinstance(item, dict) and isinstance(item.get("reference"), str):
                ref = item["reference"]
                out.append(Passage(f"cross_references[{i}]", ref,
                                   parse_exact_reference(ref), _text(item.get("text"))))
    return out


def covering(passages: list[Passage], ref: Ref) -> list[Passage]:
    """The declared passages whose range contains `ref`."""
    return [p for p in passages if p.ref and p.ref.covers(ref)]
