"""The rule engine.

Reads standards/rules.yml and checks a Sunday's content against it.
Every finding carries the governing document and section it came from,
so a report answers "why is this a problem?" without anyone having to
remember the standards.

This module makes no editorial judgments of its own.  It only applies
what rules.yml says, and rules.yml only restates what the standards
documents already say in prose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .model import Lesson, Piece

ERROR = "error"
WARNING = "warning"


@dataclass
class Finding:
    severity: str
    rule: str
    message: str
    source: str = ""
    piece: str = ""
    line: int = 0
    excerpt: str = ""

    @property
    def location(self) -> str:
        if self.piece and self.line:
            return f"{self.piece}:{self.line}"
        return self.piece or "lesson.yml"

    def __str__(self) -> str:
        tag = "ERROR" if self.severity == ERROR else "warn "
        head = f"  {tag}  {self.location}  [{self.rule}]"
        out = [head, f"         {self.message.strip()}"]
        if self.excerpt:
            out.append(f"         > {self.excerpt}")
        if self.source:
            out.append(f"         source: {self.source}")
        return "\n".join(out)


def _lines(text: str) -> list[str]:
    return text.splitlines()


def _find_pattern(piece: Piece, pattern: str, flags=re.I) -> list[tuple[int, str]]:
    """Locate a regex in a piece's visible body, returning (line no, excerpt)."""
    hits = []
    rx = re.compile(pattern, flags)
    # Offset so reported line numbers match the file as opened in an
    # editor, front matter included.
    offset = len(_lines(piece.raw)) - len(_lines(piece.body))
    for i, line in enumerate(_lines(piece.body), start=1):
        for m in rx.finditer(line):
            start = max(0, m.start() - 35)
            end = min(len(line), m.end() + 35)
            excerpt = ("..." if start else "") + line[start:end].strip() + ("..." if end < len(line) else "")
            hits.append((i + offset, excerpt))
    return hits


def _exempt(rules: dict, level: str, ptype: str, section: str) -> bool:
    ex = (rules.get("section_exemptions") or {}).get(level, {}).get(ptype, [])
    return section in ex


# ---------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------

def check_forbidden_characters(rules: dict, lesson: Lesson) -> list[Finding]:
    out = []
    for spec in rules.get("forbidden_characters", []):
        ch = spec["char"]
        for piece in lesson.pieces:
            for line_no, excerpt in _find_pattern(piece, re.escape(ch)):
                out.append(Finding(
                    severity=spec.get("severity", ERROR),
                    rule=f"forbidden-character:{spec.get('name', ch)}",
                    message=spec.get("message", f"Forbidden character {ch!r}."),
                    source=spec.get("source", ""),
                    piece=piece.path.name, line=line_no, excerpt=excerpt,
                ))
    return out


def check_forbidden_phrases(rules: dict, lesson: Lesson) -> list[Finding]:
    out = []
    for spec in rules.get("forbidden_phrases", []):
        pattern = spec["pattern"]
        for piece in lesson.pieces:
            for line_no, excerpt in _find_pattern(piece, pattern):
                out.append(Finding(
                    severity=spec.get("severity", ERROR),
                    rule=f"forbidden-phrase:{pattern}",
                    message=spec.get("message", "Forbidden phrase."),
                    source=spec.get("source", ""),
                    piece=piece.path.name, line=line_no, excerpt=excerpt,
                ))
    return out


def check_draft_markers(rules: dict, lesson: Lesson) -> list[Finding]:
    spec = rules.get("draft_markers") or {}
    out = []
    for pattern in spec.get("patterns", []):
        for piece in lesson.pieces:
            for line_no, excerpt in _find_pattern(piece, pattern, flags=0):
                out.append(Finding(
                    severity=spec.get("severity", ERROR),
                    rule="draft-marker",
                    message=spec.get("message", "Draft marker would reach a printed page."),
                    source=spec.get("source", ""),
                    piece=piece.path.name, line=line_no, excerpt=excerpt,
                ))
    return out


def check_required_sections(rules: dict, lesson: Lesson) -> list[Finding]:
    spec = rules.get("required_sections") or {}
    severity = spec.get("severity", ERROR)
    source = spec.get("source", "")
    out = []
    for piece in lesson.pieces:
        required = spec.get(piece.type)
        if not required:
            continue
        for name in required:
            if piece.has_section(name):
                continue
            if _exempt(rules, piece.level, piece.type, name):
                continue
            out.append(Finding(
                severity=severity, rule="missing-section",
                message=f'{piece.type.replace("_", " ")} is missing the required section "{name}".',
                source=source, piece=piece.path.name,
            ))
    return out


def check_manifest(rules: dict, lesson: Lesson) -> list[Finding]:
    spec = rules.get("manifest") or {}
    expected = {p["id"]: p for p in spec.get("pieces", [])}
    present = {p.id for p in lesson.pieces}
    out = []
    for pid in expected:
        if pid not in present:
            out.append(Finding(
                severity=spec.get("severity", ERROR), rule="missing-piece",
                message=f'The Sunday is missing piece "{pid}". '
                        f"All twelve pieces are required before a Sunday can be built.",
                source=spec.get("source", ""),
            ))
    for pid in sorted(present - set(expected)):
        out.append(Finding(
            severity=WARNING, rule="unexpected-piece",
            message=f'Piece "{pid}" is not in the twelve-piece manifest.',
            source=spec.get("source", ""),
        ))
    # Declared type/level must match the manifest, or the renderers and
    # the section checks are working from the wrong template.
    for piece in lesson.pieces:
        want = expected.get(piece.id)
        if not want:
            continue
        for attr in ("type", "level", "order"):
            got = getattr(piece, attr)
            if str(want.get(attr)) != str(got):
                out.append(Finding(
                    severity=ERROR, rule="manifest-mismatch",
                    message=f'{piece.id}: front matter says {attr}="{got}", '
                            f'manifest says "{want.get(attr)}".',
                    source=spec.get("source", ""), piece=piece.path.name,
                ))
    return out


def check_translation(rules: dict, lesson: Lesson) -> list[Finding]:
    spec = rules.get("translation_schedule") or {}
    d = lesson.date
    expected = None
    note = ""
    for r in spec.get("rules", []):
        if "on_date" in r and date.fromisoformat(str(r["on_date"])) == d:
            expected, note = r["translation"], r.get("note", "")
            break
        if "from_date" in r and d >= date.fromisoformat(str(r["from_date"])):
            expected, note = r["translation"], r.get("note", "")
    if expected and lesson.translation and lesson.translation != expected:
        return [Finding(
            severity=spec.get("severity", ERROR), rule="wrong-translation",
            message=f"{lesson.slug} is dated {d} and declares translation "
                    f'"{lesson.translation}", but the schedule requires "{expected}". {note}'.strip(),
            source=spec.get("source", ""),
        )]
    if expected and not lesson.translation:
        return [Finding(
            severity=ERROR, rule="missing-translation",
            message=f'lesson.yml does not declare a translation. Expected "{expected}".',
            source=spec.get("source", ""),
        )]
    return []


def check_attribution(rules: dict, lesson: Lesson) -> list[Finding]:
    spec = (rules.get("locked_strings") or {}).get("attribution") or {}
    if not spec:
        return []
    # Compare on words alone: the printed line wraps, and YAML folds.
    def squash(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip().lower()

    needle = squash(spec.get("value", ""))
    out = []
    for piece in lesson.pieces:
        has = needle in squash(piece.body)
        if piece.type in spec.get("applies_to", []) and not has:
            out.append(Finding(
                severity=spec.get("severity", ERROR), rule="missing-attribution",
                message=f"{piece.type.replace('_',' ')} must carry the attribution line. "
                        + spec.get("message", ""),
                source=spec.get("source", ""), piece=piece.path.name,
            ))
        if piece.type in spec.get("forbidden_on", []) and has:
            out.append(Finding(
                severity=spec.get("severity", ERROR), rule="unexpected-attribution",
                message=f"{piece.type.replace('_',' ')} must not carry the attribution line. "
                        + spec.get("message", ""),
                source=spec.get("source", ""), piece=piece.path.name,
            ))
    return out


def check_catechism_heading(rules: dict, lesson: Lesson) -> list[Finding]:
    spec = (rules.get("locked_strings") or {}).get("catechism_heading") or {}
    if not spec:
        return []
    wrong = re.compile(r"^\s*#{1,6}\s*(catechism connection|the catechism|catechism link)\b", re.I | re.M)
    out = []
    for piece in lesson.pieces:
        for m in wrong.finditer(piece.body):
            line_no = piece.body[:m.start()].count("\n") + 1
            out.append(Finding(
                severity=spec.get("severity", ERROR), rule="wrong-catechism-heading",
                message=spec.get("message", ""), source=spec.get("source", ""),
                piece=piece.path.name, line=line_no, excerpt=m.group(0).strip(),
            ))
    return out


def check_lords_prayer(rules: dict, lesson: Lesson) -> list[Finding]:
    spec = (rules.get("locked_strings") or {}).get("lords_prayer_form") or {}
    if not spec or not spec.get("forbidden_pattern"):
        return []
    out = []
    for piece in lesson.pieces:
        for line_no, excerpt in _find_pattern(piece, spec["forbidden_pattern"]):
            out.append(Finding(
                severity=spec.get("severity", ERROR), rule="lords-prayer-form",
                message=spec.get("message", ""), source=spec.get("source", ""),
                piece=piece.path.name, line=line_no, excerpt=excerpt,
            ))
    return out


def check_level_labels(rules: dict, lesson: Lesson) -> list[Finding]:
    """Level labels are printed text and must appear exactly as specified."""
    spec = rules.get("level_labels") or {}
    canonical = spec.get("canonical", {})
    out = []
    for piece in lesson.pieces:
        want = canonical.get(piece.level)
        if not want or piece.level == "all":
            continue
        if want.lower() not in piece.body.lower() and want.lower() not in piece.title.lower():
            out.append(Finding(
                severity=WARNING, rule="level-label",
                message=f'Could not find the canonical level label "{want}" in this piece. '
                        + spec.get("message", ""),
                source=spec.get("source", ""), piece=piece.path.name,
            ))
    return out


def check_translation_consistency(rules: dict, lesson: Lesson) -> list[Finding]:
    """Does the copyright notice a piece carries match the declared translation?

    Written after the Rally Day discovery: the printed pieces carry ESV
    text and an ESV notice, the app serves NKJV text with an NKJV notice,
    and Core Standards describes the Sunday as NKJV. Nothing compared
    them, so all three stayed wrong at once.
    """
    spec = rules.get("translation_consistency") or {}
    if not spec or not lesson.translation:
        return []
    declared = lesson.translation.upper()
    notices = spec.get("notices", {})
    out = []
    for piece in lesson.pieces:
        body = piece.body
        claimed = {name for name, pat in notices.items() if re.search(pat, body)}
        if claimed and declared not in claimed:
            out.append(Finding(
                severity=spec.get("severity", ERROR), rule="translation-notice-mismatch",
                message=f'This piece carries a {"/".join(sorted(claimed))} copyright notice, '
                        f'but the Sunday declares "{declared}". ' + spec.get("message", ""),
                source=spec.get("source", ""), piece=piece.path.name,
            ))
    return out


def check_open_conflicts(rules: dict, lesson: Lesson) -> list[Finding]:
    """Surface unresolved contradictions between the standards documents.

    These are not content defects.  They are reported against every
    Sunday because a drafter cannot comply with two contradictory rules,
    and because leaving them unreported is how they stayed unresolved.
    """
    out = []
    for c in rules.get("open_conflicts", []):
        positions = "  |  ".join(
            f"{p['source']}: {re.sub(r'[\s]+', ' ', p['says']).strip()}"
            for p in c.get("positions", [])
        )
        msg = f"Unresolved governance conflict: {c['question']}\n         {positions}"
        if c.get("observed"):
            msg += f"\n         observed: {re.sub(r'[\s]+', ' ', c['observed']).strip()}"
        out.append(Finding(
            severity=c.get("severity", WARNING),
            rule=f"open-conflict:{c['id']}", message=msg,
        ))
    return out


CHECKS = [
    check_manifest,
    check_required_sections,
    check_forbidden_characters,
    check_forbidden_phrases,
    check_draft_markers,
    check_translation,
    check_attribution,
    check_catechism_heading,
    check_lords_prayer,
    check_translation_consistency,
    check_level_labels,
    check_open_conflicts,
]


def check_lesson(rules: dict, lesson: Lesson) -> list[Finding]:
    findings: list[Finding] = []
    for check in CHECKS:
        findings.extend(check(rules, lesson))

    # Several patterns can match the same words: "[full text as
    # originally printed, NKJV]" trips two placeholder patterns at once.
    # A reviewer should see one problem per problem, so collapse
    # findings that point at the same text for the same reason.
    seen: set[tuple] = set()
    unique: list[Finding] = []
    for f in findings:
        key = (f.rule.split(":")[0], f.piece, f.line, f.excerpt, f.message[:60])
        if key in seen:
            continue
        seen.add(key)
        unique.append(f)

    order = {ERROR: 0, WARNING: 1}
    unique.sort(key=lambda f: (order.get(f.severity, 2), f.piece, f.line))
    return unique


def summarize(findings: list[Finding]) -> tuple[int, int]:
    errors = sum(1 for f in findings if f.severity == ERROR)
    warnings = sum(1 for f in findings if f.severity == WARNING)
    return errors, warnings
