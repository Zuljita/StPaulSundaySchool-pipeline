# The review app

A static page pastors use to read a Sunday and approve it. No server
holds the curriculum; the page reads `review/data/*.json`, which
`tools/make_review.py` generates from `content/` through the same parser
the build uses. What a reviewer reads is what will print.

## How a Sunday moves through it

1. A Sunday is drafted on a branch named for it, e.g.
   `sunday/2026-09-27-trinity-17`, and opened as a pull request.
2. `tools/make_review.py` writes the review data; CI runs the linter.
3. Pastors open the app, read all twelve pieces, and see every rule
   violation against the piece it appears in, with line numbers and the
   standards section each rule comes from.
4. Approving posts a **GitHub pull request review** from that pastor's
   own account. The review body carries the content hash they were shown.
5. `.github/workflows/approval.yml` converts approving reviews into
   `approvals/<sunday>.approval.json`, bound to that hash, and only for
   reviewers listed in `standards/reviewers.yml`.
6. Merge, then `tools/build.py` renders handouts and the app export.

Approve is disabled while the linter reports errors. Nobody should be
asked to sign text that already violates a written standard.

## Running it locally

```bash
python tools/make_review.py
python -m http.server 8787 --directory review
```

Read-only until sign-in is configured, which is fine for reading and for
printing a proof. Approvals can be recorded from the command line:

```bash
python tools/approve.py 2026-09-27-trinity-17 \
    --reviewer "Bryan Wolfmueller" --role pastor --note "reviewed 9/25"
```

## Setup for multi-pastor sign-in

Three steps, all of which need account access this repository does not
have.

### 1. Create a GitHub OAuth App

<https://github.com/settings/developers> → New OAuth App.

| Field | Value |
|---|---|
| Application name | St. Paul Sunday School Review |
| Homepage URL | where the app is hosted, e.g. `https://<org>.github.io/StPaulSundaySchool/` |
| Authorization callback URL | the same URL |

Keep the **Client ID** (public) and generate a **Client Secret** (not
public, never committed).

### 2. Deploy the auth endpoint

The static page cannot hold the client secret, and GitHub's token
endpoint sends no CORS headers, so the code-for-token exchange needs one
small server-side hop. `worker/worker.js` is that hop and nothing more.
It runs inside Cloudflare Workers' free tier.

```bash
cd review/worker
npx wrangler secret put GITHUB_CLIENT_SECRET
npx wrangler deploy
```

Set `GITHUB_CLIENT_ID` as a plain variable in `wrangler.toml`, and add
the app's public URL to `ALLOWED_ORIGINS` in `worker.js` so a copy of the
page hosted elsewhere cannot mint tokens against the church's repository.

### 3. Fill in `review/config.js`

```js
window.STPAUL_CONFIG = {
  repo: "<org>/StPaulSundaySchool",
  githubClientId: "Iv1.xxxxxxxxxxxx",
  authEndpoint: "https://stpaul-review-auth.<subdomain>.workers.dev",
  churchName: "St. Paul Lutheran Church, Austin",
};
```

Then add each pastor to `standards/reviewers.yml` with their GitHub
login, and give them write access to the repository so GitHub will accept
their review.

## Who can approve

Two independent checks, and both must pass:

- **GitHub** decides whose review it will accept at all, by repository
  permission.
- **`standards/reviewers.yml`** decides whose approval counts toward the
  gate, and what the policy is (how many approvals, which roles). An
  approval from an account not on that roster is reported and ignored.

Raising `required_approvals`, or adding a required role, takes effect
immediately on everything not yet built, including Sundays already
sitting approved. Tightening the rule is the safe direction for that
surprise to run.

## What the app deliberately does not do

- It does not edit content. Reviewers give notes; a person applies them.
- It does not store curriculum text anywhere but this repository.
- It does not keep a token past the browser tab. Sign-in lives in
  `sessionStorage`, so a shared church computer does not stay signed in.
