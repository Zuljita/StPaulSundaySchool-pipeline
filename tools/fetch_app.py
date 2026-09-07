#!/usr/bin/env python
"""Fetch what the Base44 app is currently serving.

    python tools/fetch_app.py                     # cache to build/app-snapshot.json
    python tools/fetch_app.py --list              # what Sundays does the app have?

The app exposes its Sunday entities on a public endpoint, which is what
makes the sync question answerable at all: without it, "do the app and
the handouts match?" could only be answered by a person reading both.

Output goes to build/ (ignored by git). It is a snapshot of a live system,
not source of truth, and nothing here writes into content/.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stpaul.model import DATA_ROOT  # noqa: E402
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

APP_ID = "6a9a2ee76011a0d7f3878e40"
BASE = "https://stpaulsunday.base44.app"
ENDPOINT = f"{BASE}/api/apps/{APP_ID}/entities/Sunday?sort=-sunday_date&limit=200"


def fetch(url: str = ENDPOINT) -> list[dict]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(DATA_ROOT / "build" / "app-snapshot.json"))
    ap.add_argument("--list", action="store_true", help="summarise and exit")
    args = ap.parse_args()

    data = fetch()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"{len(data)} Sunday record(s) -> {out}\n")
    for s in data:
        docs = s.get("documents") or []
        kinds = {}
        for d in docs:
            kinds[d.get("type", "?")] = kinds.get(d.get("type", "?"), 0) + 1
        print(f"  {s.get('sunday_date','?')}  {s.get('liturgical_day','?'):<22} "
              f"{s.get('gospel_reference','?'):<20} {len(docs):>2} document(s)  "
              f"{', '.join(f'{k}x{v}' for k, v in sorted(kinds.items()))}")
        if s.get("source_sha256"):
            print(f"      source_sha256: {s['source_sha256']}")
        else:
            print("      source_sha256: (absent - cannot be traced to approved content)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
