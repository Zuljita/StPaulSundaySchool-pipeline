# Auth endpoint

One job: exchange a GitHub OAuth code for a token, because a static page
cannot hold a client secret and GitHub's token endpoint sends no CORS
headers.

It never sees curriculum text and never decides who may approve. That is
GitHub repository permissions plus `standards/reviewers.yml`.

    npx wrangler secret put GITHUB_CLIENT_SECRET
    npx wrangler deploy

Set `GITHUB_CLIENT_ID` in wrangler.toml and add the review app's public
URL to `ALLOWED_ORIGINS` in worker.js.
