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

Five steps, in order. Step 2 needs Google Workspace admin; step 3 needs
Cloudflare access.

### 1. Generate the signing key

```bash
cd /path/to/pipeline
export STPAUL_DATA=/path/to/data-repo
python tools/keygen.py
```

Writes `standards/approval-key.pub` into the data repository, and prints
the private key **once**. Keep that terminal open for step 3.

Commit the public key. It belongs in git: everyone verifies against it,
so replacing it should be a visible commit someone can question.

### 2. Create the Google OAuth client

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

Origins are scheme + host + port, never a path. For local development add
`http://localhost:8787` as a second origin.

No redirect URI is needed: the app uses Google Identity Services, which
hands the page an ID token directly rather than redirecting.

Scopes stay at `openid`, `email`, `profile`. Nothing here reads the
reviewer's mail, calendar or files, and nothing should.

Copy the **Client ID**. It is public by design; it identifies the app, it
does not authenticate it.

### 3. Deploy the approval service

```bash
cd services/approval
```

Fill in `wrangler.toml`: `GOOGLE_CLIENT_ID`, `DATA_REPO`,
`ALLOWED_ORIGIN` (the same origin as above), and optionally `ALLOWED_HD`
(the Workspace domain, e.g. `stpaulaustin.org`).

Then the two secrets:

```bash
npx wrangler secret put APPROVAL_SIGNING_KEY   # paste the PEM from step 1
npx wrangler secret put GITHUB_TOKEN           # see below
npx wrangler deploy
```

The GitHub token should be a **fine-grained personal access token**
scoped to the data repository alone, with **Contents: read and write**
and nothing else. It is how the service commits approvals. Give it an
expiry and a calendar reminder.

Note the deployed URL.

### 4. Point the app at the service

In `review/config.js`:

```js
window.STPAUL_CONFIG = {
  service: "https://stpaul-approval.<subdomain>.workers.dev",
  googleClientId: "…apps.googleusercontent.com",
  churchName: "St. Paul Lutheran Church, Austin",
};
```

Commit and push. `.github/workflows/pages.yml` publishes `review/` to
GitHub Pages; enable Pages for the repository with **Source: GitHub
Actions** the first time.

If the published URL differs from what you guessed in step 2, go back and
correct the authorized origin and `ALLOWED_ORIGIN`. A mismatch shows up
as `origin_mismatch` at sign-in.

### 5. Add the reviewers and close the gate

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
