#!/usr/bin/env python
"""Stage the public site for upload to R2.

    python tools\\publish_site.py              # every Sunday that qualifies
    python tools\\publish_site.py 2026-09-20-trinity-16
    python tools\\publish_site.py --out D:\\dev\\StPaulSundaySchool\\dist-site

Takes what `build.py` already rendered and assembles the bucket: the
front page, each Sunday, each piece, the stylesheet, and the printable
handouts. Writes `r2-manifest.json` beside them, which
`services/site/publish.ps1` reads to do the upload.

THE GATE, AGAIN, AT THE LAST MOMENT

A `BUILD-PROVENANCE.json` records what was true when the build ran. It
can be hours old, and content can have moved under it. Publishing is the
act that puts words in front of the congregation, so it re-asks the two
questions rather than trusting the record:

  * Does `content/<sunday>/` still hash to what this build was made from?
    If not the build is stale, and the fix is to rebuild, not to publish.
  * Does that content still carry a current approval?

Either answer wrong and the Sunday is skipped, by name, with the reason.
A draft build is never staged at all.

This tool copies bytes and never writes prose. It reads no content
directly: everything it stages was rendered by `build.py` from approved
text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from stpaul.approval import verify
from stpaul.hashing import content_hash
from stpaul.model import (APPROVALS_DIR, CONTENT_DIR, DATA_ROOT, DIST_DIR,
                          STANDARDS_DIR)
from stpaul.render.site import STYLESHEET, render_index

DEFAULT_OUT = DATA_ROOT / "dist-site"

# The R2 key is the URL path. `/` and `/<slug>/` resolve to index.html,
# which the Worker appends; nothing else is rewritten. One mapping, in
# one place, so a 404 is always a missing object rather than a rule that
# disagrees with another rule.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".pdf": "application/pdf",
    ".docx": ("application/vnd.openxmlformats-officedocument"
              ".wordprocessingml.document"),
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
}


def content_type(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


class Skipped(Exception):
    """This Sunday is not publishable, and why."""


def candidate(slug: str, dist: Path, *,
              content_dir: Path = CONTENT_DIR,
              approvals_dir: Path = APPROVALS_DIR,
              standards_dir: Path = STANDARDS_DIR) -> dict:
    """Read one built Sunday, or refuse it with a reason.

    The directories are arguments for the same reason they are arguments
    on `approval.verify`: this is the last check before publication, and a
    check that cannot be tested is a check nobody should trust.
    """
    prov_path = dist / slug / "BUILD-PROVENANCE.json"
    if not prov_path.is_file():
        raise Skipped("not built; run tools/build.py first")

    prov = json.loads(prov_path.read_text(encoding="utf-8"))

    if prov.get("draft"):
        raise Skipped("draft build; drafts are never published")
    if not prov.get("approved"):
        raise Skipped(f"built unapproved ({prov.get('approval_status', 'unknown')})")

    site_dir = dist / slug / "site"
    if not (site_dir / "index.html").is_file():
        raise Skipped("built before the site renderer existed; rebuild it")

    sunday_dir = content_dir / slug
    if not sunday_dir.is_dir():
        raise Skipped(f"no content at {sunday_dir}")

    current, _ = content_hash(sunday_dir)
    if current != prov.get("source_sha256"):
        raise Skipped("content has changed since this build; rebuild it")

    v = verify(slug, content_dir=content_dir, approvals_dir=approvals_dir,
               standards_dir=standards_dir)
    if not v.ok:
        raise Skipped(f"approval no longer current ({v.status}): {v.detail}")

    entry_path = site_dir / "site-entry.json"
    entry = json.loads(entry_path.read_text(encoding="utf-8")) if entry_path.is_file() else {
        "slug": slug, "date": "", "liturgical_day": slug,
    }
    return {"slug": slug, "site_dir": site_dir, "entry": entry,
            "handouts": dist / slug / "handouts"}


def stage(cands: list[dict], out: Path) -> list[dict]:
    """Copy the bucket into place and return the manifest rows."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    (out / "assets").mkdir(parents=True, exist_ok=True)
    (out / "assets" / "site.css").write_text(STYLESHEET, encoding="utf-8")

    (out / "index.html").write_text(
        render_index([c["entry"] for c in cands]), encoding="utf-8")

    for c in cands:
        slug = c["slug"]
        dest = out / slug
        dest.mkdir(parents=True, exist_ok=True)

        shutil.copy2(c["site_dir"] / "index.html", dest / "index.html")

        pieces_src = c["site_dir"] / "pieces"
        if pieces_src.is_dir():
            shutil.copytree(pieces_src, dest / "pieces")

        # The printables. Kept out of the HTML tree so the Worker's
        # /handouts/ prefix and the bucket agree by construction.
        if c["handouts"].is_dir():
            hdest = out / "handouts" / slug
            hdest.mkdir(parents=True, exist_ok=True)
            for f in sorted(c["handouts"].iterdir()):
                if f.is_file():
                    shutil.copy2(f, hdest / f.name)

    rows = []
    for f in sorted(p for p in out.rglob("*") if p.is_file()):
        if f.name == "r2-manifest.json":
            continue
        rows.append({
            "key": f.relative_to(out).as_posix(),
            "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
            "bytes": f.stat().st_size,
            "content_type": content_type(f),
        })

    (out / "r2-manifest.json").write_text(
        json.dumps({"objects": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sunday", nargs="*", help="default: every built Sunday")
    ap.add_argument("--dist", default=str(DIST_DIR), help="where build.py wrote")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="where to stage the bucket")
    args = ap.parse_args()

    dist = Path(args.dist)
    if not dist.is_dir():
        print(f"Nothing built: {dist} does not exist.")
        return 1

    slugs = args.sunday or sorted(
        d.name for d in dist.iterdir()
        if d.is_dir() and (d / "BUILD-PROVENANCE.json").is_file())

    cands, skipped = [], []
    for slug in slugs:
        try:
            cands.append(candidate(slug, dist))
        except Skipped as e:
            skipped.append((slug, str(e)))
        except Exception as e:
            skipped.append((slug, f"{type(e).__name__}: {e}"))

    for slug, why in skipped:
        print(f"SKIPPED  {slug}\n         {why}")
    if skipped:
        print()

    if not cands:
        print("Nothing to publish.")
        return 1

    out = Path(args.out)
    rows = stage(cands, out)

    total = sum(r["bytes"] for r in rows)
    print(f"STAGED   {len(cands)} Sunday(s), {len(rows)} object(s), "
          f"{total / 1024:.0f} KiB")
    for c in cands:
        print(f"         {c['slug']}")
    print(f"\n         -> {out}")
    print("\nUpload with:")
    print(f"  pwsh services\\site\\publish.ps1 -Staged \"{out}\" -Bucket stpaul-sundayschool")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
