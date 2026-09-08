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
     |  Ed25519 signature      bound to the exact bytes reviewed
     v
===== FREEZE LINE =====    approvals/<sunday>.approval.json
     |
     |  tools/build.py         deterministic. no model runs below here.
     v
dist/<sunday>/   handoff .md · 12 .docx · 12 .pdf · app export
                 every output stamped with the same source_sha256
```

**The gate.** An approval is a statement about *specific bytes*, signed
by a verified reviewer. Change one comma and the recomputed hash no
longer matches, every review attached to the old text stops counting, and
`build.py` refuses. Nobody has to remember to re-check.

**Signatures.** The signing key lives only in the approval service, so
write access to the data repository is not enough to approve doctrine.
A missing public key fails closed.

**Sync.** Handouts and app export are produced in one run from one parse
of one approved input. "Are they in sync?" is a string comparison.

**Rules as data.** `rules.yml` in the data repo holds the enforceable
subset of the standards, each rule citing the document and section it
comes from. Contradictions *between* standards documents are recorded,
not resolved, because picking a side is a doctrinal decision.

---

## Quick start

```bash
pip install pyyaml python-docx reportlab pypdf cryptography
export STPAUL_DATA=/path/to/the/data/repo
```

```bash
python -m unittest discover -s tools/tests   # 50 tests, no data repo needed
python tools/lint.py                         # rules vs content
python tools/lint.py --baseline              # only NEW violations (what CI runs)
python tools/verify.py                       # still what was approved?
python tools/build.py <sunday>               # refuses unless approved
python tools/build.py <sunday> --draft       # watermarked proof
```

The data repository is found via `$STPAUL_DATA`, else a sibling checkout,
else the current repo. Tests always use `tools/tests/data/` and never
touch real content.

---

## What is here

| Path | |
|---|---|
| `tools/stpaul/` | model, rule engine, canonical hashing, approval gate, signing |
| `tools/stpaul/render/` | brand constants, handoff, DOCX, PDF, app export |
| `tools/*.py` | the CLI: lint, verify, approve, build, keygen, importers, audits |
| `tools/tests/` | 54 tests, with fixture data |
| `review/` | the review app, bundled into the Worker at deploy |
| `services/approval/` | Cloudflare Worker: serves the app, Google sign-in, signing, commit |

| Tool | |
|---|---|
| `lint.py` | Content vs `rules.yml`. `--baseline` fails only on new violations. |
| `verify.py` | Does content still match its signed approval? |
| `approve.py` | Record a review locally. Unsigned; for development. |
| `build.py` | Render handoff, DOCX, PDF and app export. Refuses unapproved. |
| `keygen.py` | Generate the Ed25519 approval keypair. |
| `make_review.py` | Build the data the review app and the service read. |
| `import_legacy.py` | Lift produced DOCX into content. Copies, never rewrites. |
| `import_app.py` | Recover content from a Base44 app export. |
| `ocr_archive.py` | Recover text from PDFs whose type was flattened to outlines. |
| `drift.py` | App vs handouts, piece by piece. |
| `scripture_audit.py` | Verse counts against publisher permission limits. |
| `fetch_app.py` | Snapshot what the live app is serving. |

---

## Setting up approvals

1. Point a dedicated hostname at the Worker. A hostname of its own is the
   isolation boundary, not a nicety: authorising a shared origin would let
   anything else on it obtain a token this service accepts.
2. Create a Google OAuth client, Internal user type, for that origin.
3. `python tools/keygen.py` — writes the public key into the data repo,
   prints the private key once.
4. Deploy `services/approval`, which serves the review app and the API
   together. Set the signing key and a GitHub token scoped to the data
   repository.
5. Add reviewers to `standards/reviewers.yml` in the data repo, with
   their Google addresses, and set `require_signed_approvals: true`.

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
