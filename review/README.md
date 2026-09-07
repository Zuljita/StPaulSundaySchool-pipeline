# The review app

A static page a pastor reads a Sunday on and approves. It holds no
curriculum: everything comes through the approval service, which is the
only thing with access to the private data repository.

Reviewers need **no GitHub account and no new account of any kind.** The
church runs on Google Workspace, so they sign in with the account they
already have.

---

## How a Sunday moves through it

1. A Sunday is drafted under `content/<sunday>/` in the data repository.
2. `tools/make_review.py` writes `review/data/<slug>.json`; CI keeps it
   current. That file is what the reviewer sees and what the approval is
   bound to.
3. A pastor opens the app, signs in with Google, reads all twelve pieces
   with every rule violation shown against the piece it appears in, and
   approves.
4. The service verifies the token, checks the roster, signs the review
   with Ed25519, and commits `approvals/<slug>.approval.json`.
5. `tools/build.py` will now render that Sunday, and refuses any other.

Approve is disabled while the linter reports errors. Nobody should be
asked to sign text that already breaks a written standard.

---

## Setup

Six steps, in order. Step 3 needs Google Workspace admin; step 4 needs
Cloudflare access.

Two values thread through the whole thing, so fix them first:

| | GitHub Pages default | With a custom domain (preferred) |
|---|---|---|
| **Page URL** | `https://<org>.github.io/StPaulSundaySchool-pipeline/` | `https://sundayschool.<church-domain>/` |
| **Origin** | `https://<org>.github.io` | `https://sundayschool.<church-domain>` |

An origin is scheme + host + port and **never a path**. For a GitHub
project site every repository under the same account shares one origin,
which is what both Google and the service want. Getting this wrong is the
most common failure and it shows up as `origin_mismatch` at sign-in.

### A note on ownership, before you start

The origin above is tied to whoever owns the repository, so moving the
repository later means redoing part of steps 3 and 4. Two ways out, and
the second is better:

**Use a custom domain.** Point Pages at something like
`sundayschool.stpaulaustin.org` (Settings → Pages → Custom domain, plus a
CNAME record). The origin is then the church's and never changes, no
matter who owns the repository or whether it moves between accounts. This
is the one decision that makes every later transfer a non-event.

**Or accept the rework.** It is about ten minutes: add the new origin in
the Google console, update `ALLOWED_ORIGIN` and `DATA_REPO` in
`wrangler.toml`, redeploy, and update `service` in `config.js` if
Cloudflare moved too. Real, but not a reason to delay.

**The Google project is the constraint that does not move.** For the
consent screen to be **Internal**, the Google Cloud project has to be
inside the church's Workspace organization. An Internal client for the
church's domain cannot be created from a personal Google account, so step
3 belongs to Bryan or a Workspace admin whoever owns the GitHub side.
That is worth sorting before anything else here.

**Prefer an organization to a personal account.** The premise of this
whole design is that reviewers need no GitHub account, so transferring to
the pastor personally works against it. A GitHub organization owned by the
church, with the maintainer as an admin, outlasts any individual.

### What changes on transfer

Whenever the repository moves, exactly four things:

| | |
|---|---|
| Google console | add the new origin to Authorized JavaScript origins |
| `wrangler.toml` | `ALLOWED_ORIGIN`, and `DATA_REPO` if the data repo moved too |
| `config.js` | `service`, only if the Worker moved to another Cloudflare account |
| GitHub token | reissue, scoped to the data repository at its new path |

Nothing in the code is pinned to an owner. Signed approvals already on
record stay valid: a signature covers the reviewer, the Sunday and the
content hash, none of which a transfer touches.

### 1. Enable GitHub Pages

Repository → Settings → Pages → **Source: GitHub Actions**.

`.github/workflows/pages.yml` publishes `review/` on every push. Until
Pages is enabled that workflow fails with "Get Pages site failed", which
is expected and means only this step is outstanding.

### 2. Generate the signing key

```bash
cd /path/to/pipeline
export STPAUL_DATA=/path/to/data-repo
python tools/keygen.py
```

Writes `standards/approval-key.pub` into the data repository, and prints
the private key **once**. Keep that terminal open for step 4.

Commit the public key. It belongs in git: everyone verifies against it,
so replacing it should be a visible commit someone can question.

### 3. Create the Google OAuth client

At <https://console.cloud.google.com/auth/clients> (Google Auth Platform
→ Clients), in a project for the church.

**Configure the consent screen first, if prompted.** Choose **Internal**
as the user type. On Workspace that restricts sign-in to the church's own
domain and skips app verification entirely. External would work but is
the wrong shape here.

Then **Create client**:

| Field | Value |
|---|---|
| Application type | **Web application** |
| Name | St. Paul Sunday School Review |
| Authorized JavaScript origins | the page's origin, e.g. `https://<org>.github.io` |
| Authorized redirect URIs | *leave empty* |

Use the **Origin** from the table above. Add `http://localhost:8787` as a
second origin for local development.

No redirect URI is needed: the app uses Google Identity Services, which
hands the page an ID token directly rather than redirecting.

Scopes stay at `openid`, `email`, `profile`. Nothing here reads the
reviewer's mail, calendar or files, and nothing should.

Copy the **Client ID**. It is public by design; it identifies the app, it
does not authenticate it.

### 4. Deploy the approval service

```bash
cd services/approval
```

Fill in `wrangler.toml`: `GOOGLE_CLIENT_ID`, `DATA_REPO`,
`ALLOWED_ORIGIN` (the same origin as above), and optionally `ALLOWED_HD`
(the Workspace domain, e.g. `stpaulaustin.org`).

Then the two secrets:

```bash
npx wrangler secret put APPROVAL_SIGNING_KEY   # paste the PEM from step 2
npx wrangler secret put GITHUB_TOKEN           # see below
npx wrangler deploy
```

The GitHub token should be a **fine-grained personal access token**
scoped to the data repository alone, with **Contents: read and write**
and nothing else. It is how the service commits approvals. Give it an
expiry and a calendar reminder.

Note the deployed URL.

### 5. Point the app at the service

In `review/config.js`:

```js
window.STPAUL_CONFIG = {
  service: "https://stpaul-approval.<subdomain>.workers.dev",
  googleClientId: "…apps.googleusercontent.com",
  churchName: "St. Paul Lutheran Church, Austin",
};
```

Commit and push. The Pages workflow republishes `review/` automatically.

### 6. Add the reviewers and close the gate

In the data repository, `standards/reviewers.yml`:

```yaml
policy:
  required_approvals: 1
  required_roles: [pastor]
  require_signed_approvals: true

reviewers:
  - name: "Bryan Wolfmueller"
    role: pastor
    email: "bryan@stpaulaustin.org"     # the Google address, lowercase
```

`require_signed_approvals: true` is the switch that closes the gate. With
it on, an unsigned approval is not an approval, and a missing public key
fails closed rather than passing unchecked.

Delegation is one more entry. Because it is a commit, adding an approver
is something a person can see and question.

---

## Checking it works

Sign in as yourself. You should see the Sunday index. Then, in order of
what each proves:

| Try | Expect |
|---|---|
| A personal gmail account | rejected before the roster is read, if `ALLOWED_HD` is set |
| A Workspace address not on the roster | "… is not on the reviewer roster" |
| Approving a Sunday with lint errors | refused, with the count |
| Approving a clean Sunday | a commit appears in the data repo |
| `python tools/verify.py <sunday>` | `approved`, naming the reviewer |
| Edit one comma, re-run verify | `stale`, naming the changed file |

That last row is the whole system in one test. If it does not go stale,
something is wrong and nothing else matters.

---

## Running locally without any of this

With `service` unset in `config.js`, the app reads `review/data/*.json`
from disk and is read-only, which is enough for reading a proof:

```bash
python tools/make_review.py
python -m http.server 8787 --directory review
```

Approvals then go through the CLI, which records them unsigned:

```bash
python tools/approve.py 2026-09-27-trinity-17 \
    --reviewer "Bryan Wolfmueller" --role pastor --note "reviewed 9/25"
```

Those do not satisfy `require_signed_approvals`. That is deliberate: a
command anyone with a checkout can run is not a doctrinal approval.

---

## Who can approve

Three independent checks, and all must pass:

- **Google** decides the sign-in is genuine, and with an Internal client,
  that the account is in the church's Workspace.
- **`ALLOWED_HD`**, if set, rejects anything outside that domain before
  the roster is read.
- **`standards/reviewers.yml`** decides whose approval counts, how many
  are needed, and which roles.

Tightening the policy takes effect immediately on everything not yet
built, including Sundays already sitting approved. That is the safe
direction for the surprise to run.

## What the app deliberately does not do

- It does not edit content. Reviewers give notes; a person applies them.
- It does not store curriculum anywhere but the data repository.
- It does not keep a token past the browser tab. The ID token is held in
  memory only, so a shared church computer does not stay signed in.
