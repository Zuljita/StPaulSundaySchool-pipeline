#!/usr/bin/env python
"""Print the built sheets to PDF, in a browser, on a runner.

    python tools/print_pdf.py dist/2026-09-20-trinity-16/handouts

The sheets are HTML because the design system is HTML: tokens, a grid, a
fixed page box. Turning that into paper takes the same engine a browser
uses, so this step is separate from `build.py`, which is pure Python and
stays that way. `build.py` is a function of the approved bytes; this is a
function of what `build.py` wrote.

It belongs to publish.yml and refuses to run anywhere else, because a
browser on a maintainer's laptop is a different browser from the one on
the runner, and a handout that came off the wrong one is not the handout
anybody reviewed.

Two things are checked rather than hoped for.

  * **The faces.** `font-display: block` holds the text back until the
    real face arrives, and `--virtual-time-budget` gives it the time.
    Both can still be defeated, and the failure is silent: Chrome prints
    Georgia and Segoe UI and says nothing. So every finished PDF is
    opened and its embedded faces are read back. A sheet set in a
    fallback fails the run.
  * **The bytes.** Chrome stamps a creation date and a document ID into
    every PDF, which would make two builds of one approved Sunday differ.
    Both are rewritten to a fixed value derived from the source hash, so
    a rebuild proves a handout came from the approved text.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from stpaul import runner  # noqa: E402

# design_standards/readme.md, "Type": three faces, three jobs, no overlap.
# If one of these is missing from a finished PDF, the sheet is not set in
# the system's type and must not go out.
REQUIRED_FACES = ("InstrumentSerif", "SourceSerif4", "Montserrat")

# Chrome renders and lays out asynchronously. The budget is virtual time,
# not wall clock: the browser advances its own timers until the page is
# quiet or the budget is spent, so this is a bound on work, not a sleep.
VIRTUAL_TIME_BUDGET_MS = 20000

CANDIDATES = (
    os.environ.get("CHROME_PATH"),
    shutil.which("chromium"),
    shutil.which("chromium-browser"),
    shutil.which("google-chrome"),
    shutil.which("google-chrome-stable"),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/chromium",
    "/usr/bin/google-chrome",
)

_BASE_FONT = re.compile(rb"/BaseFont\s*/([A-Za-z0-9+\-]+)")


class PrintError(Exception):
    """The run cannot produce a printable sheet."""


def find_browser() -> str:
    for c in CANDIDATES:
        if c and Path(c).exists():
            return str(c)
    raise PrintError(
        "No Chrome or Chromium found. On the runner, ubuntu-latest ships one; "
        "set CHROME_PATH in the workflow if it moves.")


class Served:
    """The handouts directory, on a loopback port, for as long as it takes.

    The sheets could be opened as file:// URLs and very nearly work. They
    do not: Chrome gives every file:// document its own opaque origin, so
    the `@font-face` rules never fetch, and the page prints in Segoe UI
    with no error anywhere. --allow-file-access-from-files does not lift
    it either. Over http://127.0.0.1 the three families load exactly as
    they do in the design project's own browser.

    Nothing leaves the machine: it binds loopback on a port the OS picks,
    serves the one directory, and stops.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        handler = functools.partial(_Quiet, directory=str(self._root))
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self._server.server_address[1]

    def __enter__(self) -> "Served":
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def url(self, name: str) -> str:
        return f"http://127.0.0.1:{self.port}/{urllib.parse.quote(name)}"


class _Quiet(SimpleHTTPRequestHandler):
    """A handler that does not narrate every asset fetch to stderr."""

    def log_message(self, *args) -> None:
        pass


def to_pdf(browser: str, url: str, label: str, pdf: Path) -> None:
    pdf.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="stpaul-chrome-") as profile:
        cmd = [
            browser, "--headless", "--disable-gpu", "--no-sandbox",
            "--no-pdf-header-footer",
            f"--user-data-dir={profile}",
            f"--virtual-time-budget={VIRTUAL_TIME_BUDGET_MS}",
            # Absolute: the browser resolves this against its own working
            # directory, not ours, and a relative path fails with "cannot
            # find the path" against a directory that plainly exists.
            f"--print-to-pdf={pdf.resolve()}",
            url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not pdf.exists():
        raise PrintError(f"{label}: the browser wrote no PDF.\n"
                         f"{proc.stderr.strip()[:500]}")


def embedded_faces(pdf: Path) -> set[str]:
    """Every /BaseFont name in the file, subset prefixes stripped.

    Read off the raw bytes rather than through a PDF library: this runs
    on a runner, the check has to hold whether or not an optional
    dependency is installed, and the names are not hidden in a stream.
    """
    out = set()
    for m in _BASE_FONT.finditer(pdf.read_bytes()):
        name = m.group(1).decode("ascii", "replace")
        out.add(name.split("+", 1)[-1])
    return out


def check_faces(pdf: Path) -> None:
    got = embedded_faces(pdf)
    missing = [f for f in REQUIRED_FACES
               if not any(g.replace(" ", "").startswith(f) for g in got)]
    if missing:
        raise PrintError(
            f"{pdf.name} is not set in the design system's type.\n"
            f"         missing: {', '.join(missing)}\n"
            f"         embedded: {', '.join(sorted(got)) or 'none'}\n"
            f"         The faces are in design_standards/assets/fonts/ and the "
            f"sheet links them; a sheet that prints without them has fallen "
            f"back to whatever the machine had.")


def normalise(pdf: Path, source_hash: str) -> None:
    """Replace the two stamps that would differ between two identical builds.

    Chrome writes /CreationDate and /ModDate from the clock and an /ID
    from a random seed. All three are rewritten from the source hash, so
    the same approved bytes print to the same file.
    """
    data = pdf.read_bytes()
    stamp = b"D:20000101000000+00'00'"
    data = re.sub(rb"/CreationDate\s*\(([^)]*)\)", b"/CreationDate (" + stamp + b")", data)
    data = re.sub(rb"/ModDate\s*\(([^)]*)\)", b"/ModDate (" + stamp + b")", data)

    seed = hashlib.sha256((source_hash + pdf.name).encode("utf-8")).hexdigest()[:32]
    ident = b"<" + seed.upper().encode("ascii") + b">"
    data = re.sub(rb"/ID\s*\[\s*<[0-9A-Fa-f]*>\s*<[0-9A-Fa-f]*>\s*\]",
                  b"/ID [" + ident + b" " + ident + b"]", data)
    pdf.write_bytes(data)


def source_hash_of(html: Path) -> str:
    m = re.search(r'name="source-sha256" content="([0-9a-f]+)"',
                  html.read_text(encoding="utf-8"))
    return m.group(1) if m else ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("handouts", type=Path,
                    help="a handouts/ directory written by tools/build.py")
    runner.add_local_flag(ap)
    args = ap.parse_args()

    refusal = runner.refusal(
        "print_pdf.py",
        "publish.yml prints the sheets after a build, on the runner.",
        args.local)
    if refusal:
        print(refusal, file=sys.stderr)
        return 2

    sheets = sorted(p for p in args.handouts.glob("*.html"))
    if not sheets:
        print(f"No sheets in {args.handouts}. Nothing to print.", file=sys.stderr)
        return 1

    try:
        browser = find_browser()
    except PrintError as e:
        print(f"ERROR    {e}", file=sys.stderr)
        return 1

    failures = 0
    with Served(args.handouts) as site:
        for html in sheets:
            pdf = html.with_suffix(".pdf")
            try:
                to_pdf(browser, site.url(html.name), html.name, pdf)
                check_faces(pdf)
                normalise(pdf, source_hash_of(html))
            except (PrintError, subprocess.TimeoutExpired) as e:
                failures += 1
                print(f"ERROR    {e}", file=sys.stderr)
                continue
            print(f"PRINTED  {pdf.name}  ({pdf.stat().st_size:,} bytes)")

    print()
    print(f"{len(sheets) - failures} printed, {failures} failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
