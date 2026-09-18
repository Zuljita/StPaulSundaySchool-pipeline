# Sunday School Pipeline

Templates, rule engine, renderers, review app and approval service for a
lectionary Sunday School curriculum. Built for St. Paul Lutheran Church,
Austin.

**This repository holds no curriculum.** No Scripture, no hymn text, no
lesson content, no approvals. Those live in a separate private data
repository, which this points at. That separation is deliberate: the
content is copyrighted third-party text and pastoral work under review,
and the machinery is neither.

---

## The problem it solves

A curriculum drafted with a language model, reviewed by a pastor, and
then handed *back* to a language model to re-split into printed pieces
and, separately, to re-derive an export for an app.

Two things follow from that shape, and both happened.

**Reviewed text could change after review.** Nothing compared what got
printed against what got approved. Rules written down from the beginning
quietly stopped being applied: a term retired five weeks earlier was
still printed in a header, a mandated heading was replaced on three
guides, and 52 em dashes shipped against a standing rule whose own
workflow document already said "restating the rule has not been
sufficient on its own to keep it from recurring."

**The handouts and the app were never the same document.** They were two
independent derivations. Nobody wrote them to disagree; nothing made them
agree. In the real case, 5 of 12 pieces never reached the app at all, and
of the 7 that did, 0 matched the print.

The worst single instance: a Middle School teacher's guide told teachers
to say out loud to the room, "refuse to take 'because I said so' from
anyone, including Jesus." Three generations of that one sentence were in
circulation at once, and nothing could tell you which was current.

---

## How it works

```
content/<sunday>/          source of truth, in the data repo
     |
     |  fetch-scripture        Scripture from the publisher, on a runner
     |  tools/lint.py          rules as data, not as prose
     |  review/ + services/    a pastor reads and approves
     |  SHA-256 content hash   bound to the exact bytes reviewed
     v
===== FREEZE LINE =====    approvals/<sunday>.approval.json
     |
     |  tools/build.py         deterministic. no model runs below here.
     v
dist/<sunday>/   handoff .md · 12 .docx · 12 .pdf · web site · .zip · app export
     |           every output stamped with the same source_sha256
     |
     |  tools/publish_site.py  re-checks the hash and the approval
     |  tools/publish_r2.py    uploads what survived both
     v
r2://stpaul-sundayschool     the public site, served by services/site
```

All of it runs unattended. `.github/workflows/publish.yml` refreshes what
a reviewer can see, builds what a pastor has approved, and publishes it,
on a schedule and again within a minute of an approval being recorded. In
the data repository, `fetch-scripture.yml` fills each Sunday's Scripture
from Crossway's ESV API whenever a `lesson.yml` is pushed. Nothing in the
chain waits for a person to run a command, and the tools that do these
jobs refuse to run anywhere but a runner.

**The gate.** An approval is a statement about *specific bytes*, recorded
against a verified Google identity from the roster. Change one comma and
the recomputed hash no longer matches, every review attached to the old
text stops counting, and `build.py` refuses. Nobody has to remember to
re-check.

**Identity.** The approval service verifies a Google ID token against
Google's key set and checks the address against
`standards/reviewers.yml`, so an approval names an account that actually
authenticated rather than a name someone typed.

**Sync.** Handouts, web site and app export are produced in one run from
one parse of one approved input. "Are they in sync?" is a string
comparison.

**The site is a renderer, not an export.** An export is handed to another
system that re-derives a reading of it, which is how the handouts and the
app came to disagree in the first place. `render/site.py` runs beside
`render/sheet.py` over the same parse, so there is no second derivation
left to drift, and both read one shared block parser rather than two
copies of it.

**The printed sheets are the design system, read at build time.** Core
Standards section 5 puts every visual decision in the design project, so
`render/sheet.py` loads `design_standards/tokens/*.css` off disk rather
than restating a palette and a type scale in Python. Change a token there
and the next build prints it; a test fails if a colour or a typeface is
ever written into the renderer.

**Reproducible.** Two builds of the same approved bytes produce the same
files, byte for byte, on Windows and on Linux alike. That is what makes
"rebuild it and compare" a real check on a printed handout rather than a
figure of speech, so the renderers are held to it by tests that read the
artefacts rather than the source.

**Rules as data.** `rules.yml` in the data repo holds the enforceable
subset of the standards, each rule citing the document and section it
comes from. Contradictions *between* standards documents are recorded,
not resolved, because picking a side is a doctrinal decision.

**Scripture is never typed.** `lesson.yml` holds the publisher's text for
every passage a Sunday declares, fetched on a runner, and the
`scripture_quotations` rule holds every quotation in every piece to it,
word for word.

---

## Quick start

For working on the pipeline itself. Running it is the workflows' job.

```powershell
pip install pyyaml pypdf
$env:STPAUL_DATA = "D:\dev\StPaulSundaySchool"    # PowerShell
# export STPAUL_DATA=/path/to/data-repo           # bash
```

```bash
python -m unittest discover -s tools/tests   # no data repo needed
python tools/lint.py                         # rules vs content
python tools/lint.py --baseline              # only NEW violations (what CI runs)
python tools/verify.py                       # still what was approved?
python tools/build.py <sunday> --draft       # watermarked proof
```

The data repository is found via `$STPAUL_DATA`, else a sibling checkout,
else the current repo. Tests always use `tools/tests/data/` and never
touch real content.

Fetching Scripture, refreshing review data, building what is approved and
publishing all run on GitHub Actions. `fetch_scripture.py`,
`make_review.py`, `publish_site.py`, `publish_r2.py` and `approve.py`
refuse to run anywhere else. `--local` gets past that, and it exists for
working on those tools, not for doing their jobs by hand.

---

## What is here

| Path | |
|---|---|
| `tools/stpaul/` | model, rule engine, canonical hashing, approval gate |
| `tools/stpaul/render/` | block parser, handoff, printed sheets, site, package, app export |
| `design_standards/` | the design system: tokens, components, guidelines, the vendored faces |
| `tools/*.py` | the CLI: lint, verify, approve, build, importers, audits |
| `tools/tests/` | tests, with fixture data |
| `review/` | the review app, bundled into the Worker at deploy |
| `services/approval/` | Cloudflare Worker: serves the app, Google sign-in, commit |
| `services/site/` | Cloudflare Worker: serves the public site out of R2 |

| Tool | |
|---|---|
| `lint.py` | Content vs `rules.yml`. `--baseline` fails only on new violations. |
| `verify.py` | Does content still match its approval? |
| `history.py` | Who approved what, when, and whether it still applies. |
| `approve.py` | Record a review from the command line, for development only. Approvals come from the review app. |
| `build.py` | Render handoff, printed sheets, web site, ZIP and app export. Refuses unapproved. |
| `fit_check.py` | Does any sheet run past the page box? Run by `publish.yml`. |
| `print_pdf.py` | Turn the built sheets into PDFs, in a browser. Run by `publish.yml`. |
| `fetch_fonts.py` | Vendor the three design-system faces. Run by hand when a face changes. |
| `publish_site.py` | Stage the site for R2. Re-checks hash and approval; skips drafts. Run by `publish.yml`. |
| `publish_r2.py` | Upload a staged site. Run by `publish.yml`. |
| `make_icons.py` | Cut the app icons out of the church logo. |
| `make_review.py` | Build the data the review app and the service read. Run by CI in both repositories. |
| `import_legacy.py` | Lift produced DOCX into content. Copies, never rewrites. |
| `import_app.py` | Recover content from a Base44 app export. |
| `ocr_archive.py` | Recover text from PDFs whose type was flattened to outlines. |
| `drift.py` | App vs handouts, piece by piece. |
| `scripture_audit.py` | Verse counts against publisher permission limits. |
| `fetch_app.py` | Snapshot what the live app is serving. |
| `fetch_scripture.py` | Fill `lesson.yml` with Scripture from Crossway's ESV API. Run by the data repository's `fetch-scripture` workflow. |

---

## Setting up the public site

The site is open to everyone: no sign-in, no roster. It is served from
R2 by `services/site`, on a hostname of its own, and it installs to a
phone's home screen and reads offline.

```powershell
npx wrangler r2 bucket create stpaul-sundayschool
python tools\build.py --all --approved-only
python tools\publish_site.py --local
python tools\publish_r2.py --local --staged "D:\dev\StPaulSundaySchool\dist-site"
```

That is for standing the site up the first time. After that nobody runs
it: `.github/workflows/publish.yml` does it on a schedule and again within
a minute of an approval. The Worker and the content deploy separately and
on purpose: deploying needs no curriculum, and publishing a Sunday needs
no Worker deploy. Full walkthrough in `services/site/README.md`.

Nothing unapproved can reach it. `build.py` will not render a Sunday
that is not approved, and `publish_site.py` re-checks the hash and the
approval before staging, so a build that has gone stale is skipped by
name rather than published.

---

## Setting up approvals

1. Point a dedicated hostname at the Worker. A hostname of its own is the
   isolation boundary, not a nicety: authorising a shared origin would let
   anything else on it obtain a token this service accepts.
2. Create a Google OAuth client, Internal user type, for that origin.
3. Deploy `services/approval`, which serves the review app and the API
   together. Set a GitHub token scoped to the data repository.
4. Add reviewers to `standards/reviewers.yml` in the data repo, with
   their Google addresses. That roster decides who may approve.

Full walkthrough in `review/README.md`.

Reviewers then need no GitHub account and no new account of any kind.
Delegation is one line in `reviewers.yml`, which is a reviewable commit
rather than a setting changed inside a tool.

---

## Reusing this

Nothing here is specific to one congregation except the defaults. The
rules, the roster, the standards documents and all content live in the
data repository; this repository is the machinery. The design system in
`design_standards/` and the piece manifest in `rules.yml` are where
another parish would start: swap the tokens under `design_standards/
tokens/` for your own palette and type, and the printed sheets follow.
