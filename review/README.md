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

| | |
|---|---|
| **Page URL** | `https://schoolreview.stpaulaustin.org/` |
| **Origin** | `https://schoolreview.stpaulaustin.org` |

An origin is scheme + host + port and **never a path**. Getting it wrong
shows up as `origin_mismatch` at sign-in.

> **A dedicated hostname is required here, not preferred.**
>
> Every GitHub project Pages site under one account shares a single
> origin: `https://<account>.github.io`. Authorising that origin on the
> OAuth client would let **any page under any of that account's Pages
> projects** initialise Google sign-in with this client ID and obtain a
> token the approval service accepts. Every unrelated demo, experiment
> and abandoned project on that account would join the trust boundary
> for approving doctrine.
>
> A hostname the review app has to itself is the isolation boundary.
> **Do not add `<account>.github.io` to the authorised origins**, even
> temporarily. With a custom domain configured, GitHub redirects the
> project URL to it anyway, so the app is not served there.
>
> The app stores nothing in the browser and holds the ID token in memory
> only, so there is no persisted credential for a co-resident page to
> read. That limits the damage; it does not remove the reason above.

### A note on ownership, before you start

The custom domain is not optional, for the isolation reason in the box
above, and it happens to settle ownership too. Pointed at
`schoolreview.stpaulaustin.org`, the origin belongs to the church and
does not change when the repository moves between accounts, so a later
transfer touches no Google or Cloudflare configuration at all.

This is the one decision that makes every later transfer a non-event, and
it is the same decision that keeps unrelated projects out of the trust
boundary. Worth doing first for either reason.

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
| Authorized JavaScript origins | `https://schoolreview.stpaulaustin.org` |
| Authorized redirect URIs | *leave empty* |

Use the **Origin** from the table above, and nothing else. In
particular do not add `<account>.github.io`, for the reason in the box
above.

`http://localhost:8787` can be added for local development, with the same
caveat in miniature: any local page on that port could then obtain a
token. It is a much smaller exposure since it needs code already running
on the machine, but remove it from the production client once the
deployed app works, or use a separate OAuth client for development.

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
(the Workspace domain, `stpaulaustin.org`).

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
