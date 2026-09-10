#!/usr/bin/env python
"""Stage the public site for upload to R2.

    python tools\\publish_site.py              # every Sunday that qualifies
    python tools\\publish_site.py 2026-09-20-trinity-16
    python tools\\publish_site.py --out D:\\dev\\StPaulSundaySchool\\dist-site

Takes what `build.py` already rendered and assembles the bucket: the
front page, each Sunday, each piece, the app shell (manifest, icons,
service worker), the printable handouts and the week's ZIP. Writes
`r2-manifest.json` beside them, which `tools/publish_r2.py` reads to do
the upload.

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
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from stpaul.approval import verify
from stpaul.hashing import content_hash
from stpaul.model import (APPROVALS_DIR, CONTENT_DIR, DATA_ROOT, DIST_DIR,
                          REPO_ROOT, STANDARDS_DIR)
from stpaul.render.site import (REGISTER_SW, STYLESHEET, render_index,
                               render_manifest, render_service_worker)

DEFAULT_OUT = DATA_ROOT / "dist-site"

# Icons and anything else the site serves that is not rendered from
# content. It lives in the pipeline repository because it is chrome,
# not curriculum.
PUBLIC_DIR = REPO_ROOT / "services" / "site" / "public"

# The R2 key is the URL path. `/` and `/<slug>/` resolve to index.html,
# which the Worker appends; nothing else is rewritten. One mapping, in
# one place, so a 404 is always a missing object rather than a rule that
# disagrees with another rule.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".zip": "application/zip",
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
    packages = sorted((dist / slug).glob("*-package*.zip"))
    return {"slug": slug, "site_dir": site_dir, "entry": entry,
            "handouts": dist / slug / "handouts", "packages": packages}


def _manifest_rows(out: Path) -> list[dict]:
    """Every staged file, as manifest rows, in a stable order."""
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
    return rows


CHURCH_TZ = "America/Chicago"

# The week turns at 9pm Saturday, not at midnight.
#
# A family take-home is used at home all week, so the Sunday it belongs
# to stays the lesson in use until the evening before the next one, when
# a teacher is preparing and a family is looking for what comes next.
#
# Shifting the clock forward three hours puts that boundary back onto a
# date line: 21:00 Saturday becomes 00:00 Sunday. "Which Sunday is
# current" stays a question about dates, and the renderer never has to
# know the hour. The shift cannot cross a US daylight-saving change,
# which happens at 2am.
WEEK_TURNS_AT = timedelta(hours=3)


def week_date(local_now: datetime) -> date:
    """The date the front page should treat as today.

    `local_now` must already be in the church's timezone. Kept separate
    from resolving that timezone so the rule itself can be tested on a
    machine with no IANA database, which is every Windows box without
    `tzdata`.
    """
    return (local_now + WEEK_TURNS_AT).date()


def as_of_date(now: datetime | None = None) -> date:
    """`week_date` in the church's timezone."""
    try:
        tz = ZoneInfo(CHURCH_TZ)
    except ZoneInfoNotFoundError as exc:
        # Deliberately fatal. Falling back to UTC would put the week's
        # turn at 00:00 UTC Saturday, which is 7pm Friday in Austin: the
        # lesson a family is still working through would drop off the top
        # of the page two days early, and nothing would report an error.
        raise RuntimeError(
            f"No IANA time zone database, so {CHURCH_TZ} cannot be "
            f"resolved and the week's turn cannot be placed at 9pm "
            f"Central. Install it with:  pip install tzdata"
        ) from exc
    return week_date((now or datetime.now(tz)).astimezone(tz))


def _cache_version(rows: list[dict]) -> str:
    """A cache name derived from the bytes being published.

    Not from a clock. Keyed on build time the service worker would evict
    its cache on every publish whether or not anything changed; keyed on
    nothing it would serve last week's lesson forever. Keyed on the
    content it turns over exactly when the content does, which also makes
    two publishes of the same approved bytes produce the same worker.
    """
    payload = json.dumps([[r["key"], r["sha256"]] for r in rows],
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _precache(cands: list[dict]) -> list[str]:
    """The shell, plus the newest Sunday, for reading with no signal.

    Not every Sunday: a year of them would be megabytes of cache for
    pages nobody is about to open. The week that is coming is the one a
    teacher needs in a room with bad reception, and everything else is
    cached as it is visited.
    """
    urls = [
        "/",
        "/assets/site.css",
        "/manifest.webmanifest",
        "/assets/icon-192.png",
        "/assets/icon-512.png",
    ]
    newest = max(cands, key=lambda c: (str(c["entry"].get("date", "")), c["slug"]),
                 default=None)
    if newest:
        slug = newest["slug"]
        urls.append(f"/{slug}/")
        pieces = newest["site_dir"] / "pieces"
        if pieces.is_dir():
            urls += [f"/{slug}/pieces/{f.name}" for f in sorted(pieces.glob("*.html"))]
    return urls


def stage(cands: list[dict], out: Path) -> list[dict]:
    """Copy the bucket into place and return the manifest rows."""
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    assets = out / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    # Generated from the renderer, so the site's styling and its app
    # metadata have one source each.
    (assets / "site.css").write_text(STYLESHEET, encoding="utf-8")
    (assets / "register-sw.js").write_text(REGISTER_SW, encoding="utf-8")
    (out / "manifest.webmanifest").write_text(render_manifest(), encoding="utf-8")

    # Static chrome: the icons, cut from the church logo by
    # tools/make_icons.py and committed.
    if (PUBLIC_DIR / "assets").is_dir():
        for f in sorted((PUBLIC_DIR / "assets").iterdir()):
            if f.is_file():
                shutil.copy2(f, assets / f.name)

    (out / "index.html").write_text(
        render_index([c["entry"] for c in cands], as_of=as_of_date()),
        encoding="utf-8")

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
        hdest = out / "handouts" / slug
        if c["handouts"].is_dir():
            hdest.mkdir(parents=True, exist_ok=True)
            for f in sorted(c["handouts"].iterdir()):
                if f.is_file():
                    shutil.copy2(f, hdest / f.name)

        # The whole-week archive, which build.py writes beside the
        # Sunday rather than inside the directory it archives.
        for z in c["packages"]:
            hdest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(z, hdest / z.name)

    # The service worker last, and versioned by everything above it. It
    # is excluded from its own version by construction: it does not exist
    # yet when the version is computed.
    version = _cache_version(_manifest_rows(out))
    (out / "sw.js").write_text(
        render_service_worker(version, _precache(cands)), encoding="utf-8")

    rows = _manifest_rows(out)
    (out / "r2-manifest.json").write_text(
        json.dumps({"cache_version": version, "objects": rows},
                   indent=2, ensure_ascii=False) + "\n",
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
    print(f'  python tools\\publish_r2.py --staged "{out}"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
