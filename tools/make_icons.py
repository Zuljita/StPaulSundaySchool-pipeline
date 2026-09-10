#!/usr/bin/env python
"""Cut the app icons out of the church logo.

    python tools\\make_icons.py

The logo is a horizontal lockup: an eight-pointed rosette, then the
wordmark. At 3751x686 it is useless as an app icon, but the rosette
alone is exactly 686x686, so the icon is a crop rather than a new mark.
That matters: an app icon is a piece of the church's identity, and
inventing one is a design decision that is not this tool's to make.

Run it when `design_standards/assets/stpaul-logo.png` changes. The
outputs are committed, so neither the build nor the publish needs
Pillow; only this script does.

    pip install pillow
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - a dev-only dependency
    print("This script needs Pillow:  pip install pillow")
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[1]
LOGO = ROOT / "design_standards" / "assets" / "stpaul-logo.png"
OUT = ROOT / "services" / "site" / "public" / "assets"

# design_standards/CLAUDE.md, Palette: paper, and the navy the mark is
# drawn in. An opaque tile needs a ground, and the print system's paper
# is the one this mark is always seen on.
PAPER = (255, 254, 251, 255)

# A maskable icon is cropped to whatever shape the launcher likes, and
# only the middle 80% is guaranteed to survive. Holding the mark to 62%
# of the tile keeps every point of the rosette inside a circle mask.
MASKABLE_SCALE = 0.62


def mark(logo: Image.Image) -> Image.Image:
    """The rosette, squared off from the left of the lockup."""
    alpha = logo.split()[3]
    box = alpha.getbbox()
    if box is None:
        raise SystemExit("the logo is empty")
    left, top, _, bottom = box
    side = bottom - top
    return logo.crop((left, top, left + side, bottom))


def tile(src: Image.Image, size: int, *, scale: float, ground) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), ground)
    inner = max(1, round(size * scale))
    art = src.resize((inner, inner), Image.LANCZOS)
    off = (size - inner) // 2
    canvas.alpha_composite(art, (off, off))
    return canvas


def main() -> int:
    if not LOGO.is_file():
        print(f"No logo at {LOGO}")
        return 1

    logo = Image.open(LOGO).convert("RGBA")
    m = mark(logo)
    print(f"rosette {m.size[0]}x{m.size[1]} from {logo.size[0]}x{logo.size[1]}")

    OUT.mkdir(parents=True, exist_ok=True)
    written = []

    for size in (192, 512):
        # Transparent ground: Android and Chrome composite these
        # themselves, and a hard white square behind a rounded launcher
        # icon is the usual way that goes wrong.
        p = OUT / f"icon-{size}.png"
        tile(m, size, scale=0.86, ground=(0, 0, 0, 0)).save(p, optimize=True)
        written.append(p)

        p = OUT / f"icon-maskable-{size}.png"
        tile(m, size, scale=MASKABLE_SCALE, ground=PAPER).save(p, optimize=True)
        written.append(p)

    # iOS composites nothing and does not round transparent corners well,
    # so this one is opaque.
    p = OUT / "apple-touch-icon.png"
    tile(m, 180, scale=0.80, ground=PAPER).save(p, optimize=True)
    written.append(p)

    p = OUT / "favicon.png"
    tile(m, 48, scale=0.94, ground=(0, 0, 0, 0)).save(p, optimize=True)
    written.append(p)

    for p in written:
        print(f"  {p.relative_to(ROOT).as_posix()}  {p.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
