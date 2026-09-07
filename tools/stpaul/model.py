"""Loading a Sunday's content off disk.

One Sunday is a directory under content/:

    content/2026-09-20-trinity-16/
        lesson.yml                     shared front matter for all twelve pieces
        pieces/05-primary-teacher-guide.md

Each piece is Markdown with YAML front matter.  `##` headings are the
piece's sections, and the section *names* are what the linter checks
against the required-section lists in standards/rules.yml.

Everything here is a reader.  Nothing in this module writes to content/.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _data_root() -> Path:
    """Where the curriculum lives.

    The pipeline and the curriculum are separate repositories. The
    pipeline holds templates, rules-engine code and the review app, and
    carries no Scripture, no hymn text and no lesson content, so it can
    be public. The data repository holds the standards, the weekly
    content, and the approvals, and stays private.

    Resolution order:
      1. $STPAUL_DATA, if set.
      2. A sibling directory named StPaulSundaySchool-data, or
         StPaulSundaySchool, next to this checkout.
      3. This repository itself, which is how the two lived before the
         split and how the test fixtures still work.
    """
    env = os.environ.get("STPAUL_DATA")
    if env:
        return Path(env).expanduser().resolve()

    for sibling in ("StPaulSundaySchool-data", "StPaulSundaySchool"):
        candidate = REPO_ROOT.parent / sibling
        if candidate != REPO_ROOT and (candidate / "content").is_dir():
            return candidate

    return REPO_ROOT


DATA_ROOT = _data_root()
CONTENT_DIR = DATA_ROOT / "content"
APPROVALS_DIR = DATA_ROOT / "approvals"
STANDARDS_DIR = DATA_ROOT / "standards"
ARCHIVE_DIR = DATA_ROOT / "archive"
# Build output belongs beside the data it was built from, never in the
# pipeline checkout, so a released set is stored with its own source.
DIST_DIR = DATA_ROOT / "dist"

FRONT_MATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)


class ContentError(Exception):
    """Content on disk is malformed. Distinct from a rule violation."""


@dataclass
class Section:
    heading: str
    body: str

    @property
    def text(self) -> str:
        return f"{self.heading}\n{self.body}"


@dataclass
class Piece:
    path: Path
    meta: dict
    title: str
    sections: list[Section]
    raw: str

    @property
    def id(self) -> str:
        return self.meta.get("piece", self.path.stem)

    @property
    def type(self) -> str:
        return self.meta.get("type", "")

    @property
    def level(self) -> str:
        return self.meta.get("level", "")

    @property
    def order(self) -> int:
        return int(self.meta.get("order", 0))

    @property
    def body(self) -> str:
        """Everything a reader would see, front matter excluded."""
        return FRONT_MATTER.sub("", self.raw).strip()

    def section(self, name: str) -> Section | None:
        want = _normalize_heading(name)
        for s in self.sections:
            if _normalize_heading(s.heading) == want:
                return s
        return None

    def has_section(self, name: str) -> bool:
        return self.section(name) is not None


@dataclass
class Lesson:
    slug: str
    dir: Path
    meta: dict
    pieces: list[Piece] = field(default_factory=list)

    @property
    def date(self) -> date:
        d = self.meta.get("date")
        if isinstance(d, date):
            return d
        return date.fromisoformat(str(d))

    def _str(self, key: str, default: str = "") -> str:
        """A YAML null is an absent value, not the four-character string "None".

        Every field in the import stubs starts as null, so without this a
        missing translation reads back as "None" and the linter reports a
        mismatch against a value nobody wrote.
        """
        v = self.meta.get(key)
        return default if v is None else str(v)

    @property
    def status(self) -> str:
        return self._str("status", "draft")

    @property
    def translation(self) -> str:
        return self._str("translation")

    @property
    def liturgical_day(self) -> str:
        return self._str("liturgical_day")

    def piece(self, piece_id: str) -> Piece | None:
        for p in self.pieces:
            if p.id == piece_id:
                return p
        return None


def _normalize_heading(h: str) -> str:
    """Compare headings on their words, not their decoration.

    Print headings are set in caps, sometimes carry a trailing period,
    and the middot separator drifts between "·" and "-".  None of that is
    a doctrinal difference, so it should not make a required-section
    check fail.
    """
    h = h.strip().lower()
    h = h.replace("·", " ").replace("&", "and")
    h = re.sub(r"[^a-z0-9 ]+", " ", h)
    return re.sub(r"\s+", " ", h).strip()


def parse_front_matter(raw: str) -> tuple[dict, str]:
    m = FRONT_MATTER.match(raw)
    if not m:
        return {}, raw
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        raise ContentError("front matter must be a mapping")
    return meta, raw[m.end():]


def parse_piece(path: Path) -> Piece:
    raw = path.read_text(encoding="utf-8")
    meta, body = parse_front_matter(raw)

    title = ""
    sections: list[Section] = []
    current: str | None = None
    buf: list[str] = []

    for line in body.splitlines():
        if line.startswith("# ") and not title:
            title = line[2:].strip()
            continue
        if line.startswith("## "):
            if current is not None:
                sections.append(Section(current, "\n".join(buf).strip()))
            current = line[3:].strip()
            buf = []
            continue
        buf.append(line)

    if current is not None:
        sections.append(Section(current, "\n".join(buf).strip()))

    return Piece(path=path, meta=meta, title=title, sections=sections, raw=raw)


def load_lesson(slug: str, content_dir: Path = CONTENT_DIR) -> Lesson:
    d = content_dir / slug
    if not d.is_dir():
        raise ContentError(f"no such Sunday: {slug} (looked in {d})")

    lesson_yml = d / "lesson.yml"
    if not lesson_yml.is_file():
        raise ContentError(f"{slug}: missing lesson.yml")

    meta = yaml.safe_load(lesson_yml.read_text(encoding="utf-8")) or {}
    lesson = Lesson(slug=slug, dir=d, meta=meta)

    pieces_dir = d / "pieces"
    if pieces_dir.is_dir():
        for p in sorted(pieces_dir.glob("*.md")):
            lesson.pieces.append(parse_piece(p))
    lesson.pieces.sort(key=lambda p: (p.order, p.path.name))
    return lesson


def all_sundays(content_dir: Path = CONTENT_DIR) -> list[str]:
    if not content_dir.is_dir():
        return []
    return sorted(
        d.name for d in content_dir.iterdir()
        if d.is_dir() and (d / "lesson.yml").is_file()
    )


def load_rules(standards_dir: Path = STANDARDS_DIR) -> dict:
    return yaml.safe_load((standards_dir / "rules.yml").read_text(encoding="utf-8"))
