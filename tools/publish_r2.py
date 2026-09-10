#!/usr/bin/env python
"""Upload a staged site to R2.

    python tools\\publish_r2.py --staged D:\\dev\\StPaulSundaySchool\\dist-site
    python tools\\publish_r2.py --staged ... --dry-run

Reads `r2-manifest.json` out of a directory staged by `publish_site.py`
and puts each object at the key the manifest gives it. The key is the URL
path, so what lands in the bucket is what the site serves.

This decides nothing. `publish_site.py` already re-checked, for every
Sunday it staged, that the content still hashes to what was built and
still carries a current approval. A Sunday that should not be published
is not in the staged directory to begin with.

ONE UPLOADER, TWO PLATFORMS

This started as a PowerShell script, because the project is developed on
Windows. Then CI needed to publish too, and CI runs on Linux. Two scripts
doing the same upload is two things that have to agree about key naming
and content types, and this repository has a postmortem about what
happens when two such things stop agreeing. So there is one, in the
language the rest of the pipeline is already written in.

Needs wrangler authenticated against the account holding the bucket:

    npx wrangler login
    # or set CLOUDFLARE_API_TOKEN to a token with Workers R2 Storage: Edit
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from stpaul.model import DATA_ROOT

DEFAULT_STAGED = DATA_ROOT / "dist-site"
DEFAULT_BUCKET = "stpaul-sundayschool"

# Pinned to a major. There is no package.json here, so an unpinned npx
# would take whatever npm published this morning.
WRANGLER = ["wrangler@4"]


def npx() -> list[str]:
    exe = shutil.which("npx") or shutil.which("npx.cmd")
    if not exe:
        raise SystemExit(
            "npx was not found. Install Node, or upload with the Cloudflare "
            "dashboard using the keys in r2-manifest.json.")
    return [exe, "--yes", *WRANGLER]


def load_manifest(staged: Path) -> list[dict]:
    path = staged / "r2-manifest.json"
    if not path.is_file():
        raise SystemExit(
            f"No r2-manifest.json in {staged}. Run: python tools/publish_site.py")
    objects = json.loads(path.read_text(encoding="utf-8")).get("objects") or []
    if not objects:
        raise SystemExit("The manifest lists no objects.")
    return objects


def put(base: list[str], bucket: str, staged: Path, obj: dict) -> None:
    local = staged / obj["key"]
    if not local.is_file():
        raise SystemExit(f"The manifest names a file that is not staged: {obj['key']}")

    # --remote writes to the real bucket rather than a local simulation.
    cmd = [*base, "r2", "object", "put", f"{bucket}/{obj['key']}",
           "--file", str(local),
           "--content-type", obj["content_type"],
           "--remote"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stdout.write(res.stdout)
        sys.stderr.write(res.stderr)
        raise SystemExit(f"Upload failed at {obj['key']}.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--staged", default=str(DEFAULT_STAGED))
    ap.add_argument("--bucket", default=DEFAULT_BUCKET)
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be uploaded and stop")
    args = ap.parse_args()

    staged = Path(args.staged)
    objects = load_manifest(staged)
    total = sum(o["bytes"] for o in objects)

    print(f"{len(objects)} object(s), {total / 1024:.0f} KiB -> r2://{args.bucket}")

    if args.dry_run:
        for o in objects:
            print(f"  {o['content_type']:<52} {o['key']}")
        return 0

    base = npx()
    for i, o in enumerate(objects, 1):
        put(base, args.bucket, staged, o)
        print(f"  [{i}/{len(objects)}] {o['key']}")

    print(f"\nUploaded {len(objects)} object(s).")
    print("The site serves them at the hostname in services\\site\\wrangler.toml.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
