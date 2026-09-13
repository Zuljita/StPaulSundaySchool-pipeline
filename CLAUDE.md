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

## Where things run

**On GitHub Actions.** Every step that changes something is a workflow,
and it runs because something happened: a push, an approval, a schedule.
None of them waits for a person to remember it.

| What | Where | When |
|---|---|---|
| Fetch Scripture into `lesson.yml` | data repo, `fetch-scripture.yml` | a push that changes a `lesson.yml` |
| Lint and verify | data repo, `ci.yml` | every pull request, and every push to `main` |
| Refresh `review/data` | data repo, `refresh-review-data.yml` | a push to `main` that changes content |
| Build what is approved | data repo, `build-approved.yml` | a new approval |
| Build and publish the site | here, `publish.yml` | an approval, and hourly |
| Deploy the Workers | here, `deploy.yml` and `deploy-site.yml` | a push to `main` that touches them |

So:

- **Do not hand anyone a command in place of a workflow.** Not the
  maintainer, and never the pastor or a reviewer. If a step cannot run on
  a runner yet, making it run there is the work.
- **Do not ask anyone to set up a machine or an environment.** No API keys
  in environment variables, no network allowlists, no local installs. A
  key the pipeline needs is a GitHub Actions secret, and asking for one is
  one sentence to the maintainer in the pull request: which secret, in
  which repository.
- **Never ask the pastor for anything technical.** Pastor Wolfmueller reads
  and approves words. A blocked fetch, a missing secret or a failed
  workflow goes to the maintainer, in the pull request. It does not go to
  the pastor, and it does not go in an email for the pastor to pass on.
- **Tools that belong to a workflow refuse to run anywhere else.**
  `fetch_scripture.py`, `make_review.py`, `publish_site.py`, `publish_r2.py`
  and `approve.py` stop and say what does their job. `--local` exists so
  the maintainer can work on those tools. Do not pass it to get something
  done, and do not tell anyone else to.

This section is a postmortem too. A drafting session could not reach the
ESV API, and it wrote an email for the pastor asking for a network policy
change on a Claude Code environment, a registered API key and an
environment variable. None of that was the pastor's to do, and none of it
was needed: on a runner the network is open and the key is a secret.

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
  Tests use invented placeholder text, never a real verse.
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

Scripture is not that prose. A quotation that checks out against the text
`lesson.yml` fetched from the publisher is the publisher's words, and the
rules about prose, the em dash among them, do not read it. Do not change a
verse's punctuation to suit the Voice Guide.

The same goes for anything under `open_conflicts` in the data repo's
`rules.yml`. Those are contradictions between two standards documents.
Picking a side is a doctrinal decision and it belongs to the pastor.

## Commands

These are for working **on** the pipeline. Running it is the workflows'
job; see above.

This project is developed on Windows. Prefer PowerShell forms in anything
you hand a person to run: `$env:STPAUL_DATA = "D:\path"` rather than
`export`, backslash paths rather than `/d/dev/...`, and a backtick rather
than a backslash for line continuation. `/d/dev/x` in PowerShell resolves
to `D:\d\dev\x` and fails confusingly.

```powershell
$env:STPAUL_DATA = "D:\dev\StPaulSundaySchool"
python -m unittest discover -s tools\tests   # no data repo needed
python tools\lint.py --baseline              # reads only
python tools\verify.py                       # reads only
python tools\build.py <sunday> --draft       # a watermarked proof, never published
```
