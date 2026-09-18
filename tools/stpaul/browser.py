"""Driving a headless browser over the built sheets.

Two tools need this and they need it identically: `print_pdf.py` turns the
sheets into paper, and `fit_check.py` asks whether any of them overflows
the page box. Both want the same browser, found the same way, pointed at
the same directory over the same kind of URL.

**Why a server and not a file:// URL.** Chrome gives every file://
document its own opaque origin, so the `@font-face` rules in the sheet's
stylesheet never fetch. The page still renders — in Segoe UI — and
nothing anywhere says so. `--allow-file-access-from-files` does not lift
it. Over http://127.0.0.1 the three families load exactly as they do in
the design project's own browser, so that is how the sheets are opened.

Nothing leaves the machine: the server binds loopback on a port the OS
picks, serves one directory, and stops.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
import tempfile
import threading
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Chrome renders and lays out asynchronously. The budget is virtual time,
# not wall clock: the browser advances its own timers until the page is
# quiet or the budget is spent, so this bounds work rather than sleeping.
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


class BrowserError(Exception):
    """No usable browser, or it did not do what was asked."""


def find_browser() -> str:
    for c in CANDIDATES:
        if c and Path(c).exists():
            return str(c)
    raise BrowserError(
        "No Chrome or Chromium found. ubuntu-latest ships one; set CHROME_PATH "
        "in the workflow if it moves.")


class _Quiet(SimpleHTTPRequestHandler):
    """A handler that does not narrate every asset fetch to stderr."""

    extra: dict[str, bytes] = {}

    def log_message(self, *args) -> None:
        pass

    def do_GET(self) -> None:          # noqa: N802  (the stdlib spells it this way)
        body = self.extra.get(self.path)
        if body is None:
            return super().do_GET()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Served:
    """One directory on a loopback port, for as long as the `with` lasts.

    `extra` adds pages that are served but never written to disk. The fit
    check needs a page of its own alongside the sheets, and the built
    output is not the place to leave one lying around.
    """

    def __init__(self, root: Path, extra: dict[str, bytes] | None = None) -> None:
        self._root = root.resolve()
        handler = type("Handler", (_Quiet,), {"extra": dict(extra or {})})
        self._server = ThreadingHTTPServer(
            ("127.0.0.1", 0), functools.partial(handler, directory=str(self._root)))
        self.port = self._server.server_address[1]

    def __enter__(self) -> "Served":
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def url(self, name: str) -> str:
        return f"http://127.0.0.1:{self.port}/{urllib.parse.quote(name)}"


def run(browser: str, url: str, *args: str, timeout: int = 180) -> subprocess.CompletedProcess:
    """One headless run, in a profile that is thrown away afterwards."""
    with tempfile.TemporaryDirectory(prefix="stpaul-chrome-") as profile:
        cmd = [
            browser, "--headless", "--disable-gpu", "--no-sandbox",
            "--hide-scrollbars",
            f"--user-data-dir={profile}",
            f"--virtual-time-budget={VIRTUAL_TIME_BUDGET_MS}",
            *args,
            url,
        ]
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
