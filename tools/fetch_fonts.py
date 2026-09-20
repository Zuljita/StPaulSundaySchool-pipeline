#!/usr/bin/env python
"""Vendor the three design-system faces into the repository.

    python tools/fetch_fonts.py            # verify what is committed
    python tools/fetch_fonts.py --update   # re-fetch and rewrite the manifest

The design system names three families and `design_standards/tokens/fonts.css`
originally reached for them over the network, which is fine in a browser and
wrong in a build. A handout is typeset once and printed by a volunteer, so the
faces have to be in the repository: a build that fetches its own fonts produces
different bytes on a bad network day, and a runner with no route to
fonts.gstatic.com silently sets the whole system in Georgia.

So the files are committed and the build reads them off disk. This tool is how
they got there and how they are checked. It is not part of any workflow: it
touches the network, and nothing below the freeze line may. `--update` is a
maintenance action, run by hand when the design system changes a face, and the
diff it produces is font binaries plus a manifest, which a reviewer can see.

Without `--update` it verifies: every file named in the manifest exists and
hashes to what the manifest records. `tools/tests/test_sheet.py` runs that
check, so a corrupted or half-committed face fails CI rather than printing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "design_standards" / "assets" / "fonts"
MANIFEST = FONT_DIR / "fonts.manifest.json"
FONTS_CSS = ROOT / "design_standards" / "tokens" / "fonts.css"

# Static cuts, one file per weight.
#
# Montserrat and Source Serif 4 ship as variable fonts, and Chrome will lay a
# page out with a variable instance but will not embed one in a PDF. The file
# then looks right on the machine that made it and substitutes everywhere
# else: the descriptors come out named "Montserrat-Thin-SemiBold" and
# "Source-Serif-4-14pt" with no font program attached. Instrument Serif has no
# variable cut, which is the only reason it embedded while the other two did
# not, and the only reason the fault was visible at all.
#
# Google serves static cuts to a browser too old to know what a variable font
# is, which is why UA below is Chrome 60. Same families, same foundry, same
# weights the design system names; one file each, and Chrome embeds them.
FONT_QUERY = (
    "https://fonts.googleapis.com/css2"
    "?family=Instrument+Serif:ital@0;1"
    "&family=Montserrat:wght@400;500;600"
    "&family=Source+Serif+4:ital,wght@0,400;0,600;1,400"
    "&display=block"
)


# Google serves a face per subset. The curriculum is English and the page box
# is fixed, so every subset carried is weight the PDF has to embed: keep the
# two that cover the copy and drop cyrillic, greek and vietnamese.
KEEP_SUBSETS = ("latin", "latin-ext")

# All three families are under the SIL Open Font License, which permits
# bundling on the condition that the licence and its copyright notice travel
# with the files. Redistributing the binaries without these would be a licence
# breach in a repository meant to be publishable, so they are fetched with the
# fonts rather than left to be remembered.
LICENSES = {
    "Instrument Serif": "https://raw.githubusercontent.com/google/fonts/main/ofl/instrumentserif/OFL.txt",
    "Montserrat": "https://raw.githubusercontent.com/google/fonts/main/ofl/montserrat/OFL.txt",
    "Source Serif 4": "https://raw.githubusercontent.com/google/fonts/main/ofl/sourceserif4/OFL.txt",
}

# Asking as Python gets the truetype fallback, four times the size for the
# same glyphs, so this asks as a browser. Chrome 60 specifically: it predates
# variable-font support, so Google answers it with static cuts. See above.
UA = ("Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/60.0.3112.113 Safari/537.36")

FACE = re.compile(r"/\*\s*(?P<subset>[\w-]+)\s*\*/\s*@font-face\s*\{(?P<body>[^}]*)\}")
PROP = re.compile(r"(?P<key>[\w-]+)\s*:\s*(?P<value>[^;]+);")
SRC_URL = re.compile(r"url\((?P<url>https://[^)]+\.woff2)\)")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _slug(family: str, style: str, weight: str, subset: str) -> str:
    """A filename that says what the face is, so a diff is readable."""
    fam = family.strip("'\"").replace(" ", "")
    return f"{fam}-{weight}-{style}-{subset}.woff2"


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def _parse_faces(css: str) -> list[dict]:
    faces = []
    for m in FACE.finditer(css):
        subset = m.group("subset")
        if subset not in KEEP_SUBSETS:
            continue
        props = {p.group("key"): p.group("value").strip()
                 for p in PROP.finditer(m.group("body"))}
        url = SRC_URL.search(props.get("src", ""))
        if not url:
            continue
        faces.append({
            "family": props["font-family"].strip("'\""),
            "style": props.get("font-style", "normal"),
            "weight": props.get("font-weight", "400"),
            "stretch": props.get("font-stretch", ""),
            "unicode_range": props.get("unicode-range", ""),
            "subset": subset,
            "url": url.group("url"),
        })
    return faces


def update() -> int:
    css = _fetch(FONT_QUERY).decode("utf-8")
    faces = _parse_faces(css)
    if not faces:
        print("No faces parsed out of the stylesheet. Nothing written.", file=sys.stderr)
        return 1

    # Two subsets of one weight are two files, but a family whose cuts are
    # identical across subsets would otherwise be committed twice. Group by
    # content: one file on disk, and as many @font-face rules pointing at it
    # as there are faces that really share those bytes.
    downloaded: dict[str, bytes] = {}
    for f in faces:
        if f["url"] not in downloaded:
            downloaded[f["url"]] = _fetch(f["url"])
        f["sha256"] = _sha256(downloaded[f["url"]])

    FONT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in FONT_DIR.glob("*.woff2"):
        stale.unlink()

    names: dict[str, str] = {}      # sha256 -> filename
    taken: dict[str, str] = {}      # filename -> sha256
    files: list[dict] = []
    for f in faces:
        if f["sha256"] in names:
            continue
        base = _slug(f["family"], f["style"], f["weight"], f["subset"])
        if taken.get(base, f["sha256"]) != f["sha256"]:
            # Two genuinely different cuts want one name. Nothing should reach
            # here now that the weight is in the slug; a counter keeps it from
            # overwriting a face rather than trusting that.
            n = 2
            while taken.get(f"{base[:-6]}-{n}.woff2", f["sha256"]) != f["sha256"]:
                n += 1
            base = f"{base[:-6]}-{n}.woff2"
        names[f["sha256"]] = base
        taken[base] = f["sha256"]
        data = downloaded[f["url"]]
        (FONT_DIR / base).write_bytes(data)
        files.append({"file": base, "sha256": f["sha256"], "bytes": len(data),
                      "source": f["url"]})

    entries = [{
        "file": names[f["sha256"]],
        "family": f["family"],
        "style": f["style"],
        "weight": f["weight"],
        "stretch": f["stretch"],
        "unicode_range": f["unicode_range"],
        "subset": f["subset"],
    } for f in faces]

    licences = []
    for family, url in LICENSES.items():
        name = f"OFL-{family.replace(' ', '')}.txt"
        text = _fetch(url).decode("utf-8")
        (FONT_DIR / name).write_text(text, encoding="utf-8", newline="\n")
        licences.append({"family": family, "file": name, "source": url,
                         "copyright": text.splitlines()[0].strip()})

    files.sort(key=lambda e: e["file"])
    MANIFEST.write_text(
        json.dumps({"query": FONT_QUERY, "files": files, "faces": entries,
                    "licences": licences}, indent=2) + "\n",
        encoding="utf-8")
    FONTS_CSS.write_text(render_fonts_css(entries), encoding="utf-8")

    total = sum(e["bytes"] for e in files)
    print(f"{len(entries)} face(s) over {len(files)} file(s), {total:,} bytes "
          f"-> {FONT_DIR.relative_to(ROOT).as_posix()}/")
    print(f"rewrote {FONTS_CSS.relative_to(ROOT).as_posix()}")
    return 0


def render_fonts_css(entries: list[dict]) -> str:
    """The token file, pointed at the committed files rather than the network."""
    out = [
        "/* Three families, vendored. The design system's readme anticipated this:",
        "   \"drop them in assets/fonts/ and replace this import with @font-face rules",
        "   pointing at them.\" These are the Google-hosted cuts the system was drawn",
        "   with, fetched once and committed, so a build sets type the same on a runner",
        "   with no network as on the machine that drew it.",
        "",
        "   Generated by tools/fetch_fonts.py --update. Edit that, not this. */",
        "",
    ]
    for e in entries:
        src = f"../assets/fonts/{e['file']}"
        out.append("@font-face {")
        out.append(f"  font-family: '{e['family']}';")
        out.append(f"  font-style: {e['style']};")
        out.append(f"  font-weight: {e['weight']};")
        if e["stretch"]:
            out.append(f"  font-stretch: {e['stretch']};")
        # block, not swap. On a screen, swap shows the fallback until the
        # face arrives and is the kinder default. In print there is no
        # second chance to repaint: a sheet that goes to PDF mid-swap is
        # set in Georgia and Segoe UI, and nothing says so afterwards.
        out.append("  font-display: block;")
        out.append(f"  src: url('{src}') format('woff2');")
        if e["unicode_range"]:
            out.append(f"  unicode-range: {e['unicode_range']};")
        out.append("}")
        out.append("")
    return "\n".join(out)


def rewrite_css() -> int:
    """Re-render fonts.css from the manifest alone.

    Changing how a face is declared is not a reason to re-download it,
    and re-downloading would put new binaries in the diff for a
    one-line CSS change.
    """
    if not MANIFEST.exists():
        print(f"No manifest at {MANIFEST.relative_to(ROOT).as_posix()}.", file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    FONTS_CSS.write_text(render_fonts_css(manifest["faces"]), encoding="utf-8")
    print(f"rewrote {FONTS_CSS.relative_to(ROOT).as_posix()} "
          f"from {len(manifest['faces'])} manifest face(s).")
    return 0


def verify() -> int:
    if not MANIFEST.exists():
        print(f"No manifest at {MANIFEST.relative_to(ROOT).as_posix()}. "
              f"Run: python tools/fetch_fonts.py --update", file=sys.stderr)
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    bad = []
    for e in manifest["files"]:
        p = FONT_DIR / e["file"]
        if not p.exists():
            bad.append(f"missing: {e['file']}")
            continue
        got = _sha256(p.read_bytes())
        if got != e["sha256"]:
            bad.append(f"changed: {e['file']}\n  manifest {e['sha256']}\n  on disk  {got}")
    named = {e["file"] for e in manifest["files"]}
    for orphan in sorted(p.name for p in FONT_DIR.glob("*.woff2")):
        if orphan not in named:
            bad.append(f"not in the manifest: {orphan}")
    # The licence has to ship with the binary, so a missing one is a failure
    # here rather than a note for later.
    for lic in manifest.get("licences", []):
        if not (FONT_DIR / lic["file"]).exists():
            bad.append(f"missing licence for {lic['family']}: {lic['file']}")
    if bad:
        print("\n".join(bad), file=sys.stderr)
        return 1
    print(f"{len(manifest['files'])} file(s) carrying {len(manifest['faces'])} "
          f"face(s) verified against the manifest.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true",
                    help="re-fetch the faces and rewrite the manifest and fonts.css")
    ap.add_argument("--rewrite-css", action="store_true",
                    help="rewrite fonts.css from the committed manifest, "
                         "without touching the network")
    args = ap.parse_args()
    if args.update:
        return update()
    if args.rewrite_css:
        return rewrite_css()
    return verify()


if __name__ == "__main__":
    raise SystemExit(main())
