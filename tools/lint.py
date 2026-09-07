#!/usr/bin/env python
"""Check a Sunday's content against standards/rules.yml.

    python tools/lint.py                      # every Sunday
    python tools/lint.py 2026-09-20-trinity-16
    python tools/lint.py --json               # machine-readable, for the review app

Exit code is 1 if any error-severity finding exists, so CI and the build
both fail on it. Warnings are reported and do not block.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):      # Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


from stpaul.model import ContentError, all_sundays, load_lesson, load_rules
from stpaul.rules import ERROR, check_lesson, summarize


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sunday", nargs="*", help="Sunday slug(s). Default: all.")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    ap.add_argument("--warnings-as-errors", action="store_true")
    args = ap.parse_args()

    rules = load_rules()
    slugs = args.sunday or all_sundays()
    if not slugs:
        print("No Sundays found under content/.")
        return 0

    report = {}
    total_errors = total_warnings = 0

    for slug in slugs:
        try:
            lesson = load_lesson(slug)
        except ContentError as e:
            if args.json:
                report[slug] = {"error": str(e)}
            else:
                print(f"\n{slug}\n  ERROR  {e}")
            total_errors += 1
            continue

        findings = check_lesson(rules, lesson)
        errors, warnings = summarize(findings)
        total_errors += errors
        total_warnings += warnings

        if args.json:
            report[slug] = {
                "status": lesson.status,
                "errors": errors,
                "warnings": warnings,
                "findings": [asdict(f) for f in findings],
            }
            continue

        print(f"\n{slug}   ({len(lesson.pieces)} pieces, status: {lesson.status})")
        if not findings:
            print("  clean")
        for f in findings:
            print(f)
        print(f"  -- {errors} error(s), {warnings} warning(s)")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"\nTotal: {total_errors} error(s), {total_warnings} warning(s) "
              f"across {len(slugs)} Sunday(s).")

    if total_errors:
        return 1
    if args.warnings_as_errors and total_warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
