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

from .model import FRONT_MATTER, Lesson, Piece, _normalize_heading
from .scripture import (Ref, agreement, covering, find_references, first_words, is_excerpt,
                        lesson_passages, overlap, parse_reference, words)

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


def _find_pattern(piece: Piece, pattern: str, flags=re.I,
                  lines: list[str] | None = None) -> list[tuple[int, str]]:
    """Locate a regex in a piece's visible body, returning (line no, excerpt).

    `lines`, when given, is searched instead of the body, line for line. The
    rules about prose pass the body with verified Scripture blanked out.
    """
    hits = []
    rx = re.compile(pattern, flags)
    # Offset so reported line numbers match the file as opened in an
    # editor, front matter included.
    offset = len(_lines(piece.raw)) - len(_lines(piece.body))
    for i, line in enumerate(_lines(piece.body) if lines is None else lines, start=1):
        for m in rx.finditer(line):
            start = max(0, m.start() - 35)
            end = min(len(line), m.end() + 35)
            excerpt = ("..." if start else "") + line[start:end].strip() + ("..." if end < len(line) else "")
            hits.append((i + offset, excerpt))
    return hits


def _prose_lines(rules: dict, lesson: Lesson, piece: Piece) -> list[str]:
    """A piece's body, line for line, with verified Scripture blanked out.

    Scripture that is the publisher's text, word for word, is not the
    curriculum's prose, so the rules about prose do not read it: the em
    dash, the forbidden phrases, the draft markers and the Lord's Prayer
    form. The ESV prints em dashes, and a passage can use words a rule
    forbids in the curriculum's own voice. Neither is a mistake in a
    quotation.

    Only Scripture that checks out is blanked. A misquotation is read by
    every rule, as well as reported by check_scripture_quotations. Checks
    out means what that rule means: in a lesson whose translation
    scripture_quotations lists, a line that is wholly an excerpt of a
    fetched passage, or a quotation in double quotes that is one. The
    rules that need to see Scripture, the copyright notices among them, do
    not use this and still read everything.
    """
    cached = piece.__dict__.get("_prose_lines")
    if cached and cached[0] == id(rules):
        return cached[1]
    lines = _lines(piece.body)
    spec = rules.get("scripture_quotations") or {}
    translation = (lesson.translation or "").upper()
    texts = [p.text for p in lesson_passages(lesson.meta) if p.text]
    if spec and texts and translation in {str(t).upper() for t in spec.get("translations") or []}:
        min_words = int(spec.get("min_words", 4))

        def checks_out(text: str) -> bool:
            return len(words(text)) >= min_words and any(is_excerpt(text, t) for t in texts)

        blanked = []
        for line in lines:
            if checks_out(_uncited(_MARKUP.sub("", line), translation)):
                line = " " * len(line)
            else:
                for m in _QUOTATION.finditer(line):
                    if checks_out(_MARKUP.sub("", m.group(1))):
                        line = line[:m.start(1)] + " " * (m.end(1) - m.start(1)) + line[m.end(1):]
            blanked.append(line)
        lines = blanked
    piece.__dict__["_prose_lines"] = (id(rules), lines)
    return lines


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
            for line_no, excerpt in _find_pattern(piece, re.escape(ch),
                                                  lines=_prose_lines(rules, lesson, piece)):
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
            for line_no, excerpt in _find_pattern(piece, pattern,
                                                  lines=_prose_lines(rules, lesson, piece)):
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
            for line_no, excerpt in _find_pattern(piece, pattern, flags=0,
                                                  lines=_prose_lines(rules, lesson, piece)):
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
            if _exempt(rules, piece.level, piece.type, name):
                continue
            section = piece.section(name)
            if section is None:
                out.append(Finding(
                    severity=severity, rule="missing-section",
                    message=f'{piece.type.replace("_", " ")} is missing the required section "{name}".',
                    source=source, piece=piece.path.name,
                ))
                continue
            # A heading with nothing under it satisfies the letter of the
            # rule and none of its point. This is the shape a draft takes
            # when text is still owed: Scripture that has not been fetched
            # from the publisher, a hymn stanza not yet licensed-checked,
            # a catechism text nobody has copied out. Leaving the section
            # empty is the honest way to hold that place, and this is what
            # stops it reaching a volunteer's hand. A bracketed placeholder
            # would read as finished text to the renderer and to a reader,
            # which is how "[Insert the week's assigned stanza]" got into
            # a printed piece.
            if not section.body.strip():
                out.append(Finding(
                    severity=severity, rule="empty-section",
                    message=f'{piece.type.replace("_", " ")} has the required section '
                            f'"{name}" but nothing under it. Fill it or remove the piece '
                            f'from this Sunday; a heading alone does not build.',
                    source=source, piece=piece.path.name,
                ))
    return out


def _in_force(entry: dict, on: date) -> bool:
    """Whether a dated rules.yml entry applies to a Sunday on this date.

    `from_date` and `until_date` are inclusive. An entry with neither is
    always in force. This is how a piece or a label is added going forward
    without reaching back into a Sunday that was approved before it
    existed.
    """
    lo, hi = entry.get("from_date"), entry.get("until_date")
    if lo and on < date.fromisoformat(str(lo)):
        return False
    if hi and on > date.fromisoformat(str(hi)):
        return False
    return True


def check_manifest(rules: dict, lesson: Lesson) -> list[Finding]:
    spec = rules.get("manifest") or {}
    expected = {p["id"]: p for p in spec.get("pieces", []) if _in_force(p, lesson.date)}
    present = {p.id for p in lesson.pieces}
    out = []
    for pid in expected:
        if pid not in present:
            out.append(Finding(
                severity=spec.get("severity", ERROR), rule="missing-piece",
                message=f'The Sunday is missing piece "{pid}". '
                        f"Every piece in the manifest is required before a Sunday can be built.",
                source=spec.get("source", ""),
            ))
    for pid in sorted(present - set(expected)):
        out.append(Finding(
            severity=WARNING, rule="unexpected-piece",
            message=f'Piece "{pid}" is not in the manifest for this date.',
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
        for line_no, excerpt in _find_pattern(piece, spec["forbidden_pattern"],
                                              lines=_prose_lines(rules, lesson, piece)):
            out.append(Finding(
                severity=spec.get("severity", ERROR), rule="lords-prayer-form",
                message=spec.get("message", ""), source=spec.get("source", ""),
                piece=piece.path.name, line=line_no, excerpt=excerpt,
            ))
    return out


def check_level_labels(rules: dict, lesson: Lesson) -> list[Finding]:
    """Level labels are printed text and must appear exactly as specified."""
    spec = rules.get("level_labels") or {}
    canonical = dict(spec.get("canonical", {}))
    # A label that has since changed still governs the Sundays printed
    # under it, so an approved piece is not reported against a label that
    # did not exist yet.
    for old in spec.get("earlier") or []:
        if _in_force(old, lesson.date):
            canonical[old["level"]] = old["label"]
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


def check_scripture_copyright(rules: dict, lesson: Lesson) -> list[Finding]:
    """Does every piece printing Scripture carry the required acknowledgement?

    Neither translation in use is public domain. Both publishers permit
    quotation up to a limit without written permission, and both require
    a specific notice. Crossway exempts non-saleable media from the full
    notice provided the short mark appears, which is why student-facing
    pieces are allowed the mark alone.
    """
    spec = rules.get("scripture_copyright") or {}
    if not spec or not lesson.translation:
        return []
    tr = lesson.translation.upper()
    cfg = (spec.get("translations") or {}).get(tr)
    if not cfg:
        return []

    full_on = set(spec.get("full_notice_required_on") or [])
    mark_ok = set(cfg.get("short_mark_ok_on") or [])
    mark = cfg.get("short_mark", f"({tr})")
    out = []

    # A piece needs a notice if it quotes Scripture at all, not only if it
    # has a "The Text" section. Rally Day's pieces carry memory verses and
    # a family verse without one, and those are quotations too.
    quotes_scripture = re.compile(
        r"\b(Genesis|Exodus|Leviticus|Numbers|Deuteronomy|Joshua|Judges|Ruth|"
        r"Samuel|Kings|Chronicles|Ezra|Nehemiah|Esther|Job|Psalm|Psalms|Proverbs|"
        r"Ecclesiastes|Song|Isaiah|Jeremiah|Lamentations|Ezekiel|Daniel|Hosea|Joel|"
        r"Amos|Obadiah|Jonah|Micah|Nahum|Habakkuk|Zephaniah|Haggai|Zechariah|Malachi|"
        r"Matthew|Mark|Luke|John|Acts|Romans|Corinthians|Galatians|Ephesians|"
        r"Philippians|Colossians|Thessalonians|Timothy|Titus|Philemon|Hebrews|James|"
        r"Peter|Jude|Revelation)\s+\d+[:.]\d+", re.I)

    for piece in lesson.pieces:
        body = piece.body
        if not (piece.section("The Text") or quotes_scripture.search(body)):
            continue

        has_full = bool(re.search(cfg.get("notice_pattern", tr), body))
        has_mark = mark.lower() in body.lower()

        if piece.type in full_on and not has_full:
            out.append(Finding(
                severity=spec.get("severity", ERROR), rule="missing-copyright-notice",
                message=f"This piece prints Scripture but carries no {tr} copyright "
                        f"notice. {cfg.get('holder','')} requires: "
                        f"\"{re.sub(r'[ ]+', ' ', cfg.get('notice','')).strip()}\"",
                source=spec.get("source", ""), piece=piece.path.name,
            ))
        elif piece.type in mark_ok and not (has_full or has_mark):
            out.append(Finding(
                severity=spec.get("severity", ERROR), rule="missing-copyright-mark",
                message=f"This piece prints Scripture but carries neither the full {tr} "
                        f"notice nor the short mark {mark}. Non-saleable media may use "
                        f"the mark, but not nothing.",
                source=spec.get("source", ""), piece=piece.path.name,
            ))

    out.extend(_scripture_share_of_work(cfg, spec, lesson))
    return out


def _scripture_share_of_work(cfg: dict, spec: dict, lesson: Lesson) -> list[Finding]:
    """Crossway's share-of-work test, measured the way the work is printed.

    The work is the Sunday: every piece, handed off and printed together.
    The numerator is the Scripture that Sunday prints, each passage
    counted once however many pieces repeat it. The Gospel printed on
    eight pieces is still eleven verses of the ESV, and a memory verse
    that falls inside the pericope is already counted with it.

    The Scripture is what lesson.yml declares, since the Sunday prints
    nothing else. Every declared passage is counted whole, even one a
    piece only trims to a phrase or sends students to look up, so the
    figure errs high. Where nothing has been fetched yet, the distinct
    "The Text" sections stand in for it. Words, not characters, on both
    sides, since a publisher counts what is read.

    Advisory. A publisher measuring the printed page may count otherwise.
    """
    limit = cfg.get("max_share_of_work")
    if not limit or not lesson.pieces:
        return []
    total = sum(len(words(p.body)) for p in lesson.pieces)
    if not total:
        return []

    fetched = [p for p in lesson_passages(lesson.meta) if p.text]
    texts: list[str] = []
    for p in fetched:
        inside = p.ref and any(q is not p and q.ref and q.ref != p.ref and q.ref.covers(p.ref)
                               for q in fetched)
        if not inside:
            texts.append(p.text)
    if not texts:
        texts = [sec.body for sec in (pc.section("The Text") for pc in lesson.pieces) if sec]
    distinct = {" ".join(words(t)) for t in texts} - {""}
    scripture = sum(len(t.split()) for t in distinct)

    share = scripture / total
    if share <= limit:
        return []
    return [Finding(
        severity=WARNING, rule="scripture-share-of-work",
        message=f"Scripture is roughly {share:.0%} of this Sunday's pieces taken "
                f"together, counting each passage once ({scripture} of {total} "
                f"words); {cfg.get('holder', 'the publisher')} sets the threshold "
                f"at {limit:.0%} of the work quoting it. Worth confirming before "
                f"this goes out at scale.",
        source=spec.get("source", ""),
    )]


def check_hymn_copyright(rules: dict, lesson: Lesson) -> list[Finding]:
    """A reprint licence covers a stanza only if the notice travels with it.

    Naming a hymn needs no notice. Printing its words does, and the
    licence's conditions are the whole reason the reproduction is
    permitted, so a missing notice is not a formatting nit. Two Rally Day
    pieces went to print without one.
    """
    spec = rules.get("hymn_copyright") or {}
    if not spec:
        return []
    markers = spec.get("quoted_markers") or []
    required = spec.get("required") or []
    out = []
    for piece in lesson.pieces:
        body = piece.body
        if not any(re.search(re.escape(m), body, re.I) for m in markers):
            continue
        missing = [r["name"] for r in required
                   if not re.search(r["pattern"], body, re.I)]
        if missing:
            out.append(Finding(
                severity=spec.get("severity", ERROR), rule="hymn-copyright-notice",
                message=f"Quotes a hymn stanza but is missing: {', '.join(missing)}. "
                        + spec.get("message", ""),
                source=spec.get("source", ""), piece=piece.path.name,
            ))
    return out


def check_benediction(rules: dict, lesson: Lesson) -> list[Finding]:
    """Is the Apostolic Benediction printed, on the pieces that need it?

    Two standards documents disagreed about this for weeks, one saying
    printed in full and the other saying named only, and the result was
    that it appeared on none of the twelve Trinity 16 pieces. Pastor
    Wolfmueller settled it on Sept 7 2026: printed, in the closing, on the
    Teacher's Guide and the student piece of every lesson.

    Naming it is specifically not enough, so the check looks for the text
    rather than the title.
    """
    spec = rules.get("benediction") or {}
    if not spec:
        return []
    marker = spec.get("printed_marker") or ""
    # The wording has changed once, and a Sunday printed before the change
    # is held to the wording it was approved under.
    for old in spec.get("earlier") or []:
        if _in_force(old, lesson.date):
            marker = old.get("printed_marker") or marker
    marker = marker.lower()
    applies = set(spec.get("applies_to") or [])
    out = []
    for piece in lesson.pieces:
        if piece.type not in applies:
            continue
        body = piece.body.lower()
        if marker and marker in body:
            continue
        named = "apostolic benediction" in body
        out.append(Finding(
            severity=spec.get("severity", ERROR), rule="benediction",
            message=("Names the Apostolic Benediction but does not print it. "
                     if named else
                     "The Apostolic Benediction is missing from the closing. ")
                    + spec.get("message", ""),
            source=spec.get("source", ""), piece=piece.path.name,
        ))
    return out


def check_teacher_guide_ladder(rules: dict, lesson: Lesson) -> list[Finding]:
    """Each Teacher's Guide carries its own rung and every rung beneath it.

    Pre-K has one, High School has five. This is what makes the guides
    grow in complexity by level rather than all carrying one fixed
    skeleton.
    """
    spec = rules.get("teacher_guide_ladder") or {}
    if not spec:
        return []
    order = spec.get("order") or []
    rungs = spec.get("rungs") or {}
    out = []
    for piece in lesson.pieces:
        if piece.type != "teacher_guide" or piece.level not in order:
            continue
        # Its own rung, and everything below it on the ladder.
        wanted = [rungs[lv] for lv in order[: order.index(piece.level) + 1]
                  if lv in rungs]
        missing = [w for w in wanted if not piece.has_section(w)]
        if missing:
            out.append(Finding(
                severity=spec.get("severity", ERROR), rule="ladder-rung",
                message=f"{piece.level.replace('_', ' ')} asks "
                        f"{len(wanted)} rung(s) and is missing "
                        f"{len(missing)}: " + "; ".join(f'"{m}"' for m in missing)
                        + ". " + spec.get("message", ""),
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


# ---------------------------------------------------------------------
# Scripture, in the publisher's words
# ---------------------------------------------------------------------

_QUOTATION = re.compile(r"[\"“]([^\"“”]+)[\"”]")
_PARENTHETICAL = re.compile(r"\(([^()]*)\)")
_CITATION_AFTER = re.compile(r"\s*[.,;:]?\s*\(([^()]*)\)")
_MARKUP = re.compile(r"\*\*|__|[*_`]")
_LIST_MARK = re.compile(r"^(?:[-*+]\s+|\d+[.)]\s+|>\s*)")


def _paragraphs(piece: Piece):
    """(heading, line number, text) for every paragraph under a `##` heading.

    Line numbers count from the top of the file, front matter included, so
    they match the file as opened in an editor.
    """
    m = FRONT_MATTER.match(piece.raw)
    skip = piece.raw[:m.end()].count("\n") if m else 0
    heading, start, buf = None, 0, []
    for n, line in enumerate(piece.raw.splitlines()[skip:], start=skip + 1):
        stripped = line.strip()
        if line.startswith("## "):
            if heading is not None and buf:
                yield heading, start, " ".join(buf)
            heading, buf = line[3:].strip(), []
        elif heading is None:
            continue
        elif not stripped or stripped.startswith("#"):
            if buf:
                yield heading, start, " ".join(buf)
            buf = []
        else:
            if not buf:
                start = n
            buf.append(_LIST_MARK.sub("", stripped))
    if heading is not None and buf:
        yield heading, start, " ".join(buf)


def _citation(inner: str, translation: str) -> tuple[bool, Ref | None]:
    """Is a parenthetical a citation, like "(Luke 7:14 ESV)" or "(ESV)"?"""
    rest, ref = inner, None
    found = find_references(inner)
    if found:
        ref, start, end = found[0]
        rest = inner[:start] + inner[end:]
    rest = re.sub(rf"\b{re.escape(translation)}\b", " ", rest, flags=re.I)
    return not words(rest), ref


def _bare_citation(text: str, translation: str) -> Ref | None:
    """The reference, when a whole paragraph is only a citation: "Luke 7:14 (ESV)"."""
    found = find_references(text)
    if len(found) != 1:
        return None
    ref, start, end = found[0]
    rest = re.sub(rf"\b{re.escape(translation)}\b", " ", text[:start] + text[end:], flags=re.I)
    return None if words(rest) else ref


def _uncited(text: str, translation: str) -> str:
    """A paragraph without its citations and translation marks."""
    return _PARENTHETICAL.sub(
        lambda m: " " if _citation(m.group(1), translation)[0] else m.group(0), text)


def check_scripture_quotations(rules: dict, lesson: Lesson) -> list[Finding]:
    """Scripture in a piece is the publisher's words, word for word.

    lesson.yml holds each passage a Sunday quotes, fetched from the
    publisher by tools/fetch_scripture.py on a runner. This holds every piece
    to that text. It is the check Trinity 17 needed: an imported draft
    carried two wordings of one phrase in Luke 14:10, neither of them the
    ESV's, and nothing compared either one with anything.

    Words are compared, not typography. Case, punctuation, emphasis, verse
    numbers and line breaks are free, and a quotation may be trimmed to a
    phrase or elided with an ellipsis. An added, dropped, changed or
    reordered word is not free.

    Three places are read, as rules.yml names them:

      whole_sections   the passage is printed here. A paragraph that is
                       recognisably the Sunday's Gospel, or the passage
                       the heading names, has to be it word for word
      quoted_sections  every quotation in double quotes is Scripture
      anywhere else    a quotation followed by a citation, "..." (Luke 14:11)

    Recognisably means near_miss: at least that share of a paragraph's
    words, or of an uncited quotation's, sit in runs it shares, in order,
    with a fetched passage. One changed word leaves nearly all of a
    paragraph in such runs, and an activity a student handout sets under
    "The Text" leaves almost none, so the one is judged and the other is
    not. A cited quotation is always judged.

    Punctuation is deliberately left out of the comparison. The ESV uses em
    dashes and the Voice Guide forbids them, and which of the two gives way
    inside a quotation is not this rule's decision to make.
    """
    spec = rules.get("scripture_quotations") or {}
    translation = (lesson.translation or "").upper()
    if not spec or translation not in {str(t).upper() for t in spec.get("translations") or []}:
        return []

    severity = spec.get("severity", ERROR)
    source = spec.get("source", "")
    min_words = int(spec.get("min_words", 4))
    near_miss = float(spec.get("near_miss", 0.6))
    whole = [_normalize_heading(h) for h in spec.get("whole_sections") or []]
    quoted = [_normalize_heading(h) for h in spec.get("quoted_sections") or []]
    passages = lesson_passages(lesson.meta)
    fetched = [p for p in passages if p.text]
    gospel = next((p for p in passages if p.field == "gospel_text"), None)

    def under(heading: str, names: list[str]) -> bool:
        h = _normalize_heading(heading)
        return any(h == n or h.startswith(n + " ") for n in names)

    def verdict(text: str, heading: str, *, cited: Ref | None = None,
                pericope: bool = False, near: bool = False) -> tuple[str, str] | None:
        where = f'under "{heading}"'
        if pericope:
            if gospel is None:
                return ("scripture-unverified",
                        f"Everything {where} is read as the Sunday's Gospel, but lesson.yml "
                        f"declares no gospel reference to check it against.")
            if not gospel.text:
                return ("scripture-unverified",
                        f"Everything {where} is read as {gospel.reference}, but lesson.yml "
                        f"has no fetched gospel_text yet. The fetch-scripture workflow fills "
                        f"it when lesson.yml is pushed. Leave this section empty until then "
                        f"rather than typing the passage.")
            candidates = [gospel]
        elif cited is not None:
            declared = covering(passages, cited)
            if not declared:
                return ("scripture-unverified",
                        f"Quotes {cited} {where}, but lesson.yml declares no passage that "
                        f"covers it, so nothing can check it. Declare it under "
                        f"cross_references with text: null, and the fetch-scripture "
                        f"workflow fills it from the publisher.")
            candidates = [p for p in declared if p.text]
            if not candidates:
                return ("scripture-unverified",
                        f"Quotes {cited} {where}, but lesson.yml has no fetched text for it "
                        f"yet. The fetch-scripture workflow fills it when lesson.yml is "
                        f"pushed. Leave the quotation out until then rather than typing it.")
        else:
            candidates = fetched
            if not candidates:
                return None
        if any(is_excerpt(text, p.text) for p in candidates):
            return None
        best = max(candidates, key=lambda p: overlap(text, p.text))
        if near and overlap(text, best.text) < near_miss:
            return None
        said, n = words(text), agreement(text, best.text)
        detail = (f'It follows that text for {n} word(s), then has "{said[n]}".'
                  if n < len(said) else "Its words are all there, but not in that order.")
        return ("scripture-mismatch",
                f"This is not the {translation} text of {best.reference} that lesson.yml "
                f"holds. {detail} Copy Scripture from lesson.yml rather than typing it: a "
                f"verse may be trimmed to a phrase, but no word may change.")

    out: list[Finding] = []
    for piece in lesson.pieces:
        paragraphs = list(_paragraphs(piece))
        unverifiable: set[str] = set()
        for i, (heading, line, raw) in enumerate(paragraphs):
            text = _MARKUP.sub("", raw)
            judged: list[tuple[str, tuple[str, str] | None]] = []
            if under(heading, whole):
                if _bare_citation(text, translation) is None:
                    body = _uncited(text, translation)
                    if len(words(body)) >= min_words:
                        own = parse_reference(heading)
                        found = (verdict(body, heading, cited=own, near=True) if own
                                 else verdict(body, heading, pericope=True, near=True))
                        # Nothing to check against is one problem per section,
                        # however many paragraphs sit under the heading.
                        if found and found[0] == "scripture-unverified":
                            if heading in unverifiable:
                                found = None
                            unverifiable.add(heading)
                        judged.append((body, found))
            else:
                scripture = under(heading, quoted)
                for m in _QUOTATION.finditer(text):
                    quote = m.group(1)
                    if len(words(quote)) < min_words:
                        continue
                    cited, marked = None, False
                    after = _CITATION_AFTER.match(text, m.end())
                    if after:
                        is_citation, ref = _citation(after.group(1), translation)
                        if is_citation:
                            cited, marked = ref, True
                    if (not marked and scripture and i + 1 < len(paragraphs)
                            and paragraphs[i + 1][0] == heading
                            and not words(text[:m.start()] + text[m.end():])):
                        cited = _bare_citation(_MARKUP.sub("", paragraphs[i + 1][2]), translation)
                        marked = cited is not None
                    if not (scripture or marked):
                        continue
                    judged.append((quote, verdict(quote, heading, cited=cited,
                                                  near=cited is None)))
            for quotation, found in judged:
                if found:
                    out.append(Finding(severity=severity, rule=found[0], message=found[1],
                                       source=source, piece=piece.path.name, line=line,
                                       excerpt=first_words(quotation)))
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
    check_scripture_copyright,
    check_scripture_quotations,
    check_hymn_copyright,
    check_benediction,
    check_teacher_guide_ladder,
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
