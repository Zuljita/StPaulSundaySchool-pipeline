# The public site

Everything approved, rendered as web pages and served from R2. It is
public: no sign-in, no roster, nothing to log into.

**It holds no opinion about what may be published.** By the time a page
reaches this Worker, `build.py` has refused to render an unapproved
Sunday and `publish_site.py` has re-checked the hash and the approval.
This service maps a URL onto an R2 key.

---

## Why the site is a renderer and not an export

The app used to be a separate system the content was pushed into.
`fetch_app.py`, `drift.py` and `import_app.py` exist to measure how far
that second system drifted from the approved text, and the answer, once,
was that 5 of 12 pieces never arrived and none of the 7 that did matched
the print.

`tools/stpaul/render/site.py` runs in the same pass as the DOCX and the
PDF, over the same parse of the same bytes. There is no second derivation
left to drift. The hash in a page's colophon is the hash in the handout's
colophon because both came out of one call.

The Base44 export is still produced. It is a locked schema, it costs
almost nothing, and it is the bridge while the app is still running.

---

## How a Sunday reaches the internet

```powershell
$env:STPAUL_DATA = "D:\dev\StPaulSundaySchool"

python tools\build.py 2026-09-20-trinity-16   # refuses unless approved
python tools\publish_site.py                  # re-checks, then stages
pwsh services\site\publish.ps1 -Staged "D:\dev\StPaulSundaySchool\dist-site"
```

`publish_site.py` skips a Sunday, by name and with the reason, when it is
a draft build, when it was built unapproved, when the content has changed
since the build, or when the approval is no longer current. A stale build
is not published; it is rebuilt.

---

## Two things that deploy separately, on purpose

| | |
|---|---|
| **The Worker** | `.github/workflows/deploy-site.yml`, on a push to `main`. Needs no curriculum. |
| **The content** | `publish.ps1`, run by whoever holds `$STPAUL_DATA`. Needs no Cloudflare deploy. |

That split is why this Worker reads from R2 instead of bundling static
assets. Bundled pages would have to be uploaded at deploy time, which
would mean this public repository's CI needed a checkout of the private
curriculum. Reading from R2 keeps the machinery publishable, the content
private, and lets the person who can approve a lesson publish it without
holding deploy credentials.

---

## Setup

Two steps, both needing Cloudflare access.

**1. Create the bucket.** The name must match `bucket_name` in
`wrangler.toml`.

```powershell
npx wrangler r2 bucket create stpaul-sundayschool
```

**2. Point a hostname at the Worker.** `wrangler.toml` has
`sundayschool.stpaulaustin.org`; the zone must be on Cloudflare DNS.

> **Not the approval service's hostname.**
>
> `schoolreview.stpaulaustin.org` is authorised on a Google OAuth client
> that decides who may approve doctrine, and an origin is a trust
> boundary. This site is public, has no sign-in and holds no credential,
> so co-hosting would gain nothing and would put a public page inside
> that boundary. Give it its own name.

Then set `CLOUDFLARE_API_TOKEN` (Edit Cloudflare Workers) as a repository
secret, and `CLOUDFLARE_ACCOUNT_ID` too if the token can see more than
one account. The upload needs a token with **Workers R2 Storage: Edit**,
which is a different permission from the deploy token and can belong to a
different person.

---

## What the site is made of

No JavaScript. Not a script tag, not an inline handler: the pages are
text and a stylesheet. That is what lets the Worker send
`default-src 'none'` and have it mean something, and the deploy workflow
fails if that header goes missing.

Curriculum text is HTML-escaped when it is rendered, including the parts
that look like markup, because imported content has carried raw tags
before. `tools/tests/test_site.py` counts every `<` in the output and
fails on one the renderer did not write.

| URL | R2 key |
|---|---|
| `/` | `index.html` |
| `/<sunday>/` | `<sunday>/index.html` |
| `/<sunday>/pieces/05-primary-teacher-guide.html` | the same path |
| `/handouts/<sunday>/05-primary-teacher-guide.pdf` | the same path |
| `/assets/site.css` | `assets/site.css` |

The key is the URL path. A 404 is always a missing object, never a
rewrite rule disagreeing with another rewrite rule.
