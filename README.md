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
on a schedule and again within a minute of an approval being recorded.

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
app came to disagree in the first place. `render/site.py` runs beside the
DOCX and the PDF over the same parse, so there is no second derivation
left to drift, and all three read one shared block parser rather than
three copies of it.

**Reproducible.** Two builds of the same approved bytes produce the same
files, byte for byte, on Windows and on Linux alike. That is what makes
"rebuild it and compare" a real check on a printed handout rather than a
figure of speech, so the renderers are held to it by tests that read the
artefacts rather than the source.

**Rules as data.** `rules.yml` in the data repo holds the enforceable
subset of the standards, each rule citing the document and section it
comes from. Contradictions *between* standards documents are recorded,
not resolved, because picking a side is a doctrinal decision.

---

## Quick start

```powershell
pip install pyyaml python-docx reportlab pypdf
$env:STPAUL_DATA = "D:\dev\StPaulSundaySchool"    # PowerShell
# export STPAUL_DATA=/path/to/data-repo           # bash
```

```bash
python -m unittest discover -s tools/tests   # 100 tests, no data repo needed
python tools/lint.py                         # rules vs content
python tools/lint.py --baseline              # only NEW violations (what CI runs)
python tools/verify.py                       # still what was approved?
python tools/build.py <sunday>               # refuses unless approved
python tools/build.py <sunday> --draft       # watermarked proof
python tools/build.py --all --approved-only  # everything a pastor has signed
python tools/publish_site.py                 # stage the public site for R2
python tools/publish_r2.py --staged <dir>    # upload it
```

The data repository is found via `$STPAUL_DATA`, else a sibling checkout,
else the current repo. Tests always use `tools/tests/data/` and never
touch real content.

---

## What is here

| Path | |
|---|---|
| `tools/stpaul/` | model, rule engine, canonical hashing, approval gate |
| `tools/stpaul/render/` | brand constants, block parser, handoff, DOCX, PDF, site, package, app export |
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
| `approve.py` | Record a review locally. Unsigned; for development. |
| `build.py` | Render handoff, DOCX, PDF, web site, ZIP and app export. Refuses unapproved. |
| `publish_site.py` | Stage the site for R2. Re-checks hash and approval; skips drafts. |
| `publish_r2.py` | Upload a staged site. One uploader, Windows and CI alike. |
| `make_icons.py` | Cut the app icons out of the church logo. |
| `make_review.py` | Build the data the review app and the service read. |
| `import_legacy.py` | Lift produced DOCX into content. Copies, never rewrites. |
| `import_app.py` | Recover content from a Base44 app export. |
| `ocr_archive.py` | Recover text from PDFs whose type was flattened to outlines. |
| `drift.py` | App vs handouts, piece by piece. |
| `scripture_audit.py` | Verse counts against publisher permission limits. |
| `fetch_app.py` | Snapshot what the live app is serving. |
| `fetch_scripture.py` | Pull a Sunday's pericope from Crossway's ESV API into `lesson.yml`. Needs `ESV_API_KEY`. |

---

## Setting up the public site

The site is open to everyone: no sign-in, no roster. It is served from
R2 by `services/site`, on a hostname of its own, and it installs to a
phone's home screen and reads offline.

```powershell
npx wrangler r2 bucket create stpaul-sundayschool
python tools\build.py --all --approved-only
python tools\publish_site.py
python tools\publish_r2.py --staged "D:\dev\StPaulSundaySchool\dist-site"
```

Normally nobody runs that: `.github/workflows/publish.yml` does it on a
schedule and again within a minute of an approval. The Worker and the
content deploy separately and on purpose: deploying needs no curriculum,
and publishing a Sunday needs no Worker deploy. Full walkthrough in
`services/site/README.md`.

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
data repository; this repository is the machinery. The brand constants in
`tools/stpaul/render/brand.py` and the piece manifest in `rules.yml` are
where another parish would start.
