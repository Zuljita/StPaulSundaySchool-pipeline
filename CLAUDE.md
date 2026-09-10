# Working in this repository

This is the **pipeline**. The curriculum lives in a separate private data
repository, found via `$STPAUL_DATA`.

## The one rule

**There is a freeze line, and it is in the other repository.**

Once `approvals/<sunday>.approval.json` records an approval, that
Sunday's content is finished text. A pastor read those exact words and
signed for them. You do not edit it, and you do not write code that
edits it.

Code here runs *below* the line. `build.py` and everything under
`render/` must stay deterministic: no language model, no network, no
clock-dependent output. Two builds of the same approved bytes produce the
same files. That property is the only reason the printed handouts and the
app can be trusted to say the same thing.

## Why this exists

A postmortem, not caution in the abstract. The old pipeline reviewed at
step 5 and then let a model revise and re-export at steps 6 and 7. Rules
lived in prose and were enforced by a model remembering them. What
shipped: a term retired five weeks earlier, printed in a header; a
mandated heading replaced on three guides; 52 em dashes against a
standing rule; the Apostolic Benediction on none of twelve pieces; five
pieces that never reached the app; and a Middle School guide telling
teachers to say "refuse to take 'because I said so' from anyone,
including Jesus."

Every one of those rules was written down. Being written down was not
enough.

## What you may and may not do

**Yes:**
- Fix a bug in `tools/`, with a test.
- Add a renderer, keeping it deterministic.
- Improve the review app or the service.

**No:**
- Do not write curriculum prose. Not in an importer, not in a "tidy up"
  pass, not as placeholder text. `import_legacy.py` copies and leaves
  unknown fields null on purpose.
- Do not weaken a rule, or the gate, to make something pass.
- Do not run `--update-baseline` to make CI green. That hides a new
  mistake among old ones.
- Do not commit Bible or hymn text here. Neither the NKJV (© 1982 Thomas
  Nelson) nor the ESV (© 2001 Crossway) is public domain, and this
  repository is meant to be publishable precisely because it holds none.
- Do not change what a decision is called in one place only.
  `tools/stpaul/approval.py` defines the words, `services/approval/worker.js`
  records them and `review/index.html` sends them. When they drifted, the
  app sent `"REQUEST_CHANGES"`, the service matched only
  `"changes_requested"`, and everything else fell to a default of
  `"approved"`, so asking for changes recorded an approval. A test compares
  all three; do not skip it.

## Editorial judgment is not yours

The Voice Guide bans em dashes and says the fix is "a comma, a period and
a new sentence, or a colon, whichever reads best in context." *Whichever
reads best* is a judgment about someone else's prose. Flag it, quote the
line, let the author choose.

The same goes for anything under `open_conflicts` in the data repo's
`rules.yml`. Those are contradictions between two standards documents.
Picking a side is a doctrinal decision and it belongs to the pastor.

## Commands

This project is developed on Windows. Prefer PowerShell forms in anything
you hand a person to run: `$env:STPAUL_DATA = "D:\path"` rather than
`export`, backslash paths rather than `/d/dev/...`, and a backtick rather
than a backslash for line continuation. `/d/dev/x` in PowerShell resolves
to `D:\d\dev\x` and fails confusingly.

```powershell
$env:STPAUL_DATA = "D:\dev\StPaulSundaySchool"
python -m unittest discover -s tools\tests   # no data repo needed
python tools\lint.py --baseline
python tools\verify.py
python tools\build.py <sunday>
python tools\build.py --all --approved-only  # everything a pastor has signed
python tools\publish_site.py                 # stage the public site for R2
python tools\publish_r2.py --staged <dir>    # upload it
```
