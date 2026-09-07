#!/usr/bin/env python
"""Check a Sunday's content against standards/rules.yml.

    python tools/lint.py                      # every Sunday
    python tools/lint.py 2026-09-20-trinity-16
    python tools/lint.py --json               # machine-readable, for the review app
    python tools/lint.py --baseline           # fail only on NEW violations
    python tools/lint.py --update-baseline    # after genuinely fixing some

Exit code is 1 if any error-severity finding exists, so CI and the build
both fail on it. Warnings are reported and do not block.

THE BASELINE, AND WHY IT EXISTS
-------------------------------
The three Sundays imported from the archive carry hundreds of violations
that were already in print before any of this existed. Nobody is fixing
them this afternoon, and several of them are Pastor Wolfmueller's to
decide rather than anyone's to correct.

A check that is red on every commit is a check people stop reading, which
is the same failure as a rule that lives only in prose. So CI compares
against `standards/lint-baseline.json`: known debt is reported and does
not fail, and the build goes red the moment a count goes *up*. The debt
is visible, it can only shrink, and a new mistake still stops the line.

The baseline is per Sunday and per rule, so fixing one violation and
introducing a different one is caught rather than netting out to zero.
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


from stpaul.model import (STANDARDS_DIR, ContentError, all_sundays, load_lesson,
                          load_rules)
from stpaul.rules import ERROR, check_lesson, summarize


# The baseline records the state of the *content*, so it belongs with the
# content. Resolving it against the pipeline checkout instead silently
# found no baseline, made every known violation look new, and turned the
# whole check into noise.
BASELINE_PATH = STANDARDS_DIR / "lint-baseline.json"


def rule_counts(findings) -> dict[str, int]:
    """Error-severity findings per rule family, for baseline comparison."""
    counts: dict[str, int] = {}
    for f in findings:
        if f.severity != ERROR:
            continue
        key = f.rule.split(":")[0]
        counts[key] = counts.get(key, 0) + 1
    return counts


def load_baseline() -> dict:
    if not BASELINE_PATH.is_file():
        return {}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8")).get("sundays", {})


def compare_to_baseline(slug: str, counts: dict[str, int], baseline: dict) -> list[str]:
    """Return a list of regressions: rules that got worse, or are new."""
    known = baseline.get(slug, {})
    out = []
    for rule, n in sorted(counts.items()):
        was = known.get(rule, 0)
        if n > was:
            out.append(f"{rule}: {was} -> {n}" if was else f"{rule}: new, {n}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sunday", nargs="*", help="Sunday slug(s). Default: all.")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of text")
    ap.add_argument("--warnings-as-errors", action="store_true")
    ap.add_argument("--baseline", action="store_true",
                    help="fail only on violations beyond standards/lint-baseline.json")
    ap.add_argument("--update-baseline", action="store_true",
                    help="rewrite the baseline from the current state")
    args = ap.parse_args()

    rules = load_rules()
    slugs = args.sunday or all_sundays()
    if not slugs:
        print("No Sundays found under content/.")
        return 0

    report = {}
    baseline = load_baseline()
    observed: dict[str, dict[str, int]] = {}
    regressions: dict[str, list[str]] = {}
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
        observed[slug] = rule_counts(findings)
        regs = compare_to_baseline(slug, observed[slug], baseline)
        if regs:
            regressions[slug] = regs

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
        if args.baseline:
            known = sum(baseline.get(slug, {}).values())
            if slug in regressions:
                print(f"  -- NEW since baseline ({known} known):")
                for r in regressions[slug]:
                    print(f"       {r}")
            else:
                print(f"  -- no new violations (baseline: {known})")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"\nTotal: {total_errors} error(s), {total_warnings} warning(s) "
              f"across {len(slugs)} Sunday(s).")

    if args.update_baseline:
        BASELINE_PATH.write_text(json.dumps(
            {"note": "Known violations inherited from material produced before this "
                     "pipeline existed. Regenerate with tools/lint.py "
                     "--update-baseline only after genuinely fixing something. "
                     "These counts should only ever go down.",
             "sundays": observed},
            indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"\nBaseline written to standards/{BASELINE_PATH.name}: "
              f"{sum(sum(v.values()) for v in observed.values())} known violation(s).")
        return 0

    if args.baseline:
        if regressions:
            print("\nFAIL: new violations beyond the baseline.")
            for slug, regs in regressions.items():
                for r in regs:
                    print(f"  {slug}  {r}")
            return 1
        known = sum(sum(v.values()) for v in baseline.values())
        print(f"\nOK: no new violations. {known} known violation(s) still outstanding "
              f"(see standards/lint-baseline.json).")
        return 0

    if total_errors:
        return 1
    if args.warnings_as_errors and total_warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
