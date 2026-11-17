#!/usr/bin/env python
"""Move intact print blocks onto measured continuation pages before fit checking.

This is a browser layout step, separate from the pure-Python build. It changes
only generated HTML, never source content. An indivisible block that exceeds a
whole page fails the run. All sheets must pass before any file is replaced.
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
from stpaul import browser, runner

SCRIPT = Path(__file__).parent / 'stpaul' / 'paginate.js'
RESULT = re.compile(r'<pre id="pagination-result">(.*?)</pre>', re.S)
PROBE = """<!DOCTYPE html><html><meta charset="utf-8"><body><script>
%s
(async () => {
  const results = [];
  for (const name of %s) {
    const frame = document.createElement('iframe');
    frame.style.cssText = 'width:816px;height:1056px;border:0;position:absolute;left:-9999px';
    try {
      const loaded = new Promise((resolve, reject) => {
        frame.onload = resolve; frame.onerror = () => reject(Error('Sheet did not load.'));
      });
      frame.src = name;
      document.body.append(frame);
      await loaded;
      const doc = frame.contentDocument;
      await doc.fonts.ready;
      for (const img of doc.images) {
        if (!img.complete) await img.decode();
        if (!img.naturalWidth) throw Error('An image failed to load.');
      }
      const faces = [...doc.fonts];
      if (!faces.length || faces.some(f => f.status === 'error')) throw Error('Sheet fonts failed to load.');
      results.push({name, ...paginate(doc)});
    } catch (error) { results.push({name, error: String(error)}); }
    finally { frame.remove(); }
  }
  const output = document.createElement('pre');
  output.id = 'pagination-result'; output.textContent = JSON.stringify(results);
  document.body.append(output);
})();
</script></body></html>"""


def prepare(handouts: Path) -> list[dict]:
    names = sorted(p.name for p in handouts.glob('*.html'))
    if not names:
        raise browser.BrowserError(f'No sheets in {handouts}.')
    probe = (PROBE % (SCRIPT.read_text(encoding='utf-8'),
                     json.dumps(names).replace('<', '\\u003c'))).encode('utf-8')
    with browser.Served(handouts, extra={'/_paginate': probe}) as site:
        proc = browser.run(browser.find_browser(), site.url('_paginate'), '--dump-dom')
    match = RESULT.search(proc.stdout or '')
    if proc.returncode or not match:
        raise browser.BrowserError('Pagination did not finish. ' + (proc.stderr or '')[:500])
    rows = json.loads(html.unescape(match.group(1)))
    if [r.get('name') for r in rows] != names:
        raise browser.BrowserError('Pagination did not return every sheet.')
    errors = [f"{r['name']}: {r['error']}" for r in rows if r.get('error')]
    if errors:
        raise browser.BrowserError('\n'.join(errors))
    for row in rows:
        (handouts / row['name']).write_text(row['html'], encoding='utf-8', newline='\n')
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('handouts', type=Path)
    runner.add_local_flag(ap)
    args = ap.parse_args()
    refusal = runner.refusal('paginate.py', 'publish.yml paginates the sheets before checking page fit.', args.local)
    if refusal:
        print(refusal, file=sys.stderr)
        return 2
    try:
        rows = prepare(args.handouts)
    except (browser.BrowserError, subprocess.TimeoutExpired) as exc:
        print(f'ERROR    {exc}', file=sys.stderr)
        return 1
    for row in rows:
        print(f"LAID OUT {row['name']}: {row['pages']} page(s)")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
