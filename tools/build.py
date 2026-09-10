#!/usr/bin/env python
"""Render approved content into handouts, the web site and the app export.

    python tools/build.py 2026-09-20-trinity-16
    python tools/build.py --all
    python tools/build.py 2026-09-27-trinity-17 --draft   # watermarked proof

This is the part of the pipeline below the freeze line. It does not call
a language model, a network service, or anything with an opinion. It is a
pure function of the approved bytes, which is what makes the printed
handouts, the public site and the app export the same text rather than
independent retellings of it.

The site is rendered here, in this pass, for that reason. An export
handed to another system to re-derive is how the handouts and the app
came to disagree; a renderer cannot disagree with its siblings, because
there is only one parse.

By default it refuses to build a Sunday whose content is not currently
approved. --draft builds anyway, into dist-draft/, with DRAFT in every
filename, so a proof can never be mistaken for a releasable set.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):      # Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


from stpaul.approval import verify
from stpaul.hashing import ALGORITHM, content_hash
from stpaul.model import (CONTENT_DIR, DATA_ROOT, DIST_DIR, REPO_ROOT, all_sundays,
                          load_lesson, load_rules)
from stpaul.render import appexport, docx_render, handoff, package, pdf_render, site
from stpaul.rules import check_lesson, summarize


def shown_path(path: Path) -> str:
    """A path to print, relative to whichever root actually contains it.

    A release is written under the data root and a draft under the
    pipeline root, so neither one is reliably inside the other. Making
    every path relative to the pipeline root raised ValueError on every
    real build with $STPAUL_DATA pointing at a separate checkout, which
    is the documented layout: the files were all written, and then the
    line reporting them threw and the build read as ERROR.
    """
    for root in (DATA_ROOT, REPO_ROOT):
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            continue
    return path.as_posix()


# Returned instead of a build result when --approved-only passes over a
# Sunday that is not approved. Distinct from a refusal because it is not
# a failure: an unapproved Sunday is the normal state of most of a year.
SKIPPED = "skipped"


def build_one(slug: str, *, draft: bool, skip_pdf: bool = False,
              approved_only: bool = False) -> tuple[bool | str, str]:
    lesson = load_lesson(slug)
    digest, _ = content_hash(CONTENT_DIR / slug)
    v = verify(slug)

    if not v.ok and not draft:
        if approved_only:
            # Not an error. The publish loop asks for every Sunday and
            # expects most of them to be waiting on a pastor.
            return SKIPPED, f"WAITING  {slug}\n         {v.status}: {v.detail}"
        return False, (
            f"REFUSED  {slug}\n"
            f"         {v.status}: {v.detail}\n"
            f"         Nothing was written. Run tools/verify.py {slug} for detail."
        )

    out_root = (REPO_ROOT / "dist-draft") if draft else DIST_DIR
    out_dir = out_root / slug
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    written += handoff.write(lesson, out_dir, digest)
    written += appexport.write(lesson, out_dir, digest)
    written += site.write(lesson, out_dir, digest, draft=draft)

    handouts = out_dir / "handouts"
    for piece in lesson.pieces:
        stem = f"{piece.order:02d}-{piece.id}" + ("-DRAFT" if draft else "")
        written.append(docx_render.render(lesson, piece, digest, handouts / f"{stem}.docx"))
        if not skip_pdf:
            written.append(pdf_render.render(lesson, piece, digest, handouts / f"{stem}.pdf"))

    # Last, because it archives what the renderers above just wrote.
    zip_path = package.write(out_dir, slug, draft=draft,
                             date_time=package.date_time_for(lesson.date))
    if zip_path:
        written.append(zip_path)

    findings = check_lesson(load_rules(), lesson)
    errors, warnings = summarize(findings)

    provenance = {
        "sunday": slug,
        "source_sha256": digest,
        "algorithm": ALGORITHM,
        "approved": v.ok,
        "approval_status": v.status,
        "approved_by": [
            {"reviewer": r["reviewer"], "role": r["role"], "at": r["at"]}
            for r in (v.approving_reviews or [])
        ],
        "built_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "draft": draft,
        "lint": {"errors": errors, "warnings": warnings},
        "outputs": sorted(p.relative_to(out_dir).as_posix() for p in written),
    }
    (out_dir / "BUILD-PROVENANCE.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        f"{'DRAFT   ' if draft else 'BUILT   '}{slug}",
        f"         source {digest}",
        f"         {len(written)} file(s) -> {shown_path(out_dir)}/",
    ]
    if draft and not v.ok:
        lines.append(f"         NOT APPROVED ({v.status}). Proof only, do not distribute.")
    return True, "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sunday", nargs="*")
    ap.add_argument("--all", action="store_true", help="build every Sunday")
    ap.add_argument("--draft", action="store_true",
                    help="build unapproved content into dist-draft/ as a watermarked proof")
    ap.add_argument("--skip-pdf", action="store_true", help="DOCX only, for a faster loop")
    ap.add_argument("--approved-only", action="store_true",
                    help="build what is approved and pass over what is not, "
                         "without failing. For the publish loop.")
    args = ap.parse_args()

    slugs = all_sundays() if args.all else args.sunday
    if not slugs:
        ap.error("name a Sunday, or pass --all")

    ok = True
    built = skipped = 0
    for slug in slugs:
        try:
            good, msg = build_one(slug, draft=args.draft, skip_pdf=args.skip_pdf,
                                  approved_only=args.approved_only)
        except Exception as e:  # a renderer crash must not look like a refusal
            good, msg = False, f"ERROR    {slug}\n         {type(e).__name__}: {e}"
        if good is SKIPPED:
            skipped += 1
        else:
            ok = ok and good
            built += 1 if good else 0
        print(msg)
        print()

    if args.approved_only:
        print(f"{built} built, {skipped} waiting on approval.")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
