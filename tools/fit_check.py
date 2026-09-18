#!/usr/bin/env python
"""Does every built sheet fit on its page?

    python tools/fit_check.py dist/2026-09-20-trinity-16/handouts

design_standards/readme.md, first paragraph: "the foremost constraint is
that the page box clips — a sheet that runs long loses its footer
silently." The design project's answer is a procedure: "Verify page fit
on every page before delivering." This is that procedure, run by a
machine, so that it happens on every build rather than when someone
remembers.

It has to run in a browser. The page box is 816 x 1056 and the content is
CSS grid, flex and multi-column; how tall a paragraph sets is a fact
about a font and a line-breaking algorithm, and `build.py` is pure Python
and cannot know it. So the sheets are served, opened, and measured.

What it measures is `scrollHeight` against `clientHeight` on each
`.page`, plus the same on the rail and the substance column, and whether
the footer's bottom sits inside the box. A page over by a pixel or two is
reported and allowed; the tolerance is there because sub-pixel layout
rounds, not because a little clipping is acceptable. Anything beyond it
fails the run, and the message says which piece, which page and by how
much, because the fix is someone's editorial decision about what comes
off the sheet, and that is not this tool's to make.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from stpaul import browser, runner  # noqa: E402

# Sub-pixel layout rounds, and a fractional pixel is not a clipped word.
# Anything past this is content that will not be on the paper.
TOLERANCE_PX = 2

PROBE_PATH = "/_fit-check"

# Measures in the page rather than beside it: an iframe is same-origin
# with the sheets, so the probe can read the real laid-out geometry
# instead of guessing from the markup.
PROBE = """\
<!DOCTYPE html><html><head><meta charset="utf-8"><title>fit</title></head>
<body><script>
const sheets = %s;
const results = [];
function measure(doc, name) {
  const out = [];
  doc.querySelectorAll('.page').forEach((page, i) => {
    const over = page.scrollHeight - page.clientHeight;
    const inner = page.querySelector('.inner');
    const foot = page.querySelector('footer.sheet');
    let footOver = 0;
    if (foot && inner) {
      const fb = foot.getBoundingClientRect().bottom;
      const pb = page.getBoundingClientRect().bottom;
      footOver = Math.round((fb - pb) * 100) / 100;
    }
    let widest = 0;
    page.querySelectorAll('.frame, .rail, .stack, .scripture').forEach(el => {
      widest = Math.max(widest, el.scrollWidth - el.clientWidth);
    });
    out.push({sheet: name, page: i + 1, over, footOver, sideways: widest});
  });
  return out;
}
(async () => {
  for (const name of sheets) {
    const f = document.createElement('iframe');
    f.style.cssText = 'width:816px;height:1056px;border:0;position:absolute;left:-9999px';
    f.src = name;
    document.body.appendChild(f);
    await new Promise(r => { f.onload = r; f.onerror = r; });
    try {
      if (f.contentDocument.fonts) { await f.contentDocument.fonts.ready; }
      results.push(...measure(f.contentDocument, name));
    } catch (e) {
      results.push({sheet: name, page: 0, error: String(e)});
    }
    f.remove();
  }
  const el = document.createElement('div');
  el.id = 'fit-result';
  el.textContent = JSON.stringify(results);
  document.body.appendChild(el);
})();
</script></body></html>
"""

_RESULT = re.compile(r'<div id="fit-result">(.*?)</div>', re.S)


def measure(handouts: Path) -> list[dict]:
    sheets = sorted(p.name for p in handouts.glob("*.html"))
    if not sheets:
        raise browser.BrowserError(f"No sheets in {handouts}.")

    probe = (PROBE % json.dumps(sheets)).encode("utf-8")
    chrome = browser.find_browser()
    with browser.Served(handouts, extra={PROBE_PATH: probe}) as site:
        proc = browser.run(chrome, f"http://127.0.0.1:{site.port}{PROBE_PATH}",
                           "--dump-dom")
    m = _RESULT.search(proc.stdout or "")
    if not m:
        raise browser.BrowserError(
            "The fit probe returned nothing measurable. The browser said:\n"
            + (proc.stderr or "").strip()[:800])
    return json.loads(html.unescape(m.group(1)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("handouts", type=Path,
                    help="a handouts/ directory written by tools/build.py")
    runner.add_local_flag(ap)
    args = ap.parse_args()

    refusal = runner.refusal(
        "fit_check.py",
        "publish.yml checks page fit after a build, on the runner.",
        args.local)
    if refusal:
        print(refusal, file=sys.stderr)
        return 2

    try:
        rows = measure(args.handouts)
    except (browser.BrowserError, subprocess.TimeoutExpired) as e:
        print(f"ERROR    {e}", file=sys.stderr)
        return 1

    bad = []
    for r in rows:
        if r.get("error"):
            bad.append(f"{r['sheet']}: {r['error']}")
            continue
        if r["over"] > TOLERANCE_PX:
            bad.append(f"{r['sheet']} page {r['page']}: {r['over']}px of content "
                       f"below the page box, and it will be clipped.")
        if r["footOver"] > TOLERANCE_PX:
            bad.append(f"{r['sheet']} page {r['page']}: the footer sits {r['footOver']}px "
                       f"past the foot of the sheet.")
        if r["sideways"] > TOLERANCE_PX:
            bad.append(f"{r['sheet']} page {r['page']}: {r['sideways']}px of content "
                       f"runs off the side. A squeezed multi-column block does this.")

    pages = len([r for r in rows if not r.get("error")])
    if bad:
        print(f"OVERFLOW  {len(bad)} problem(s) across {pages} page(s):", file=sys.stderr)
        for b in bad:
            print(f"          {b}", file=sys.stderr)
        print(file=sys.stderr)
        print("          Nothing here is a code fix. A sheet that runs long is a "
              "sheet with more on it than fits, and what comes off is the "
              "author's call, not the pipeline's.", file=sys.stderr)
        return 1

    print(f"FITS     {pages} page(s), none overflowing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
