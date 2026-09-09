/**
 * The approval service.
 *
 * A reviewer signs in with Google, reads a Sunday, and approves it. No
 * GitHub account, no new account of any kind: the church already runs on
 * Google, so every reviewer has one already.
 *
 * WHAT THIS SERVICE IS FOR
 *
 * Three things a static page cannot do:
 *
 *   1. Verify who is asking. A browser can obtain a Google ID token, but
 *      only something server-side can check its signature and decide the
 *      holder is on the roster.
 *   2. Read the curriculum. The data repository is private and stays
 *      private, so review content is proxied here to authenticated
 *      reviewers rather than published.
 *   3. Write the approval. The GitHub token lives in this Worker's secret
 *      store, so recording a decision needs no GitHub account and no write
 *      access to the curriculum of the reviewer's own.
 *
 * WHAT IT DELIBERATELY DOES NOT DO
 *
 * It never edits curriculum text, and it will not sign a hash the
 * reviewer's browser supplied. The hash comes from `review/data/<slug>.json`
 * in the data repository, which CI generates from the content itself, so
 * the thing being approved is decided by the repository and not by the
 * client.
 *

 * ROUTES
 *   GET  /                 the review app
 *   GET  /config.js        generated; client id comes from wrangler.toml
 *   GET  /api/sundays      the index
 *   GET  /api/sunday/:slug one Sunday
 *   POST /api/approve      record a decision
 *
 * SECRETS (wrangler secret put ...)
 *   GITHUB_TOKEN           write access to the data repository only
 *   PUBLISH_DISPATCH_TOKEN optional; may fire a workflow in PUBLISH_REPO
 *
 * VARS (wrangler.toml)
 *   GOOGLE_CLIENT_ID       OAuth client id the ID token must be issued for
 *   DATA_REPO              e.g. "Zuljita/StPaulSundaySchool"
 *   ALLOWED_ORIGIN         where the review app is served from
 *   ALLOWED_HD             optional Workspace domain reviewers must be in
 *   PUBLISH_REPO           optional; the pipeline repository to notify
 */

// The review app itself. Serving it from here rather than from a separate
// static host is what keeps everything on one origin: no CORS pair to keep
// in sync, one custom domain, one deploy, and no possibility of the page
// and the service disagreeing about where the other one is.
import APP_HTML from "../../review/index.html";

const GOOGLE_JWKS = "https://www.googleapis.com/oauth2/v3/certs";
const GOOGLE_ISSUERS = ["https://accounts.google.com", "accounts.google.com"];
const GH = "https://api.github.com";

// ---------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------

const enc = new TextEncoder();

function b64urlToBytes(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  const bin = atob(s);
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

function bytesToB64(bytes) {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s);
}

function json(body, status, origin) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Cache-Control": "no-store",
      Vary: "Origin",
    },
  });
}

// ---------------------------------------------------------------------
// Google ID token verification
//
// Done properly rather than by decoding the payload and trusting it: an
// unverified JWT is just a string the client chose, and this one decides
// whether doctrine ships.
// ---------------------------------------------------------------------

let jwksCache = { at: 0, keys: null };

async function googleKeys() {
  if (jwksCache.keys && Date.now() - jwksCache.at < 3600_000) return jwksCache.keys;
  const res = await fetch(GOOGLE_JWKS);
  if (!res.ok) throw new Error("cannot reach Google's key set");
  const { keys } = await res.json();
  jwksCache = { at: Date.now(), keys };
  return keys;
}

async function verifyGoogleToken(idToken, clientId, allowedHd) {
  const parts = String(idToken || "").split(".");
  if (parts.length !== 3) throw new Error("malformed token");

  const [h, p, s] = parts;
  const header = JSON.parse(new TextDecoder().decode(b64urlToBytes(h)));
  const claims = JSON.parse(new TextDecoder().decode(b64urlToBytes(p)));

  const jwk = (await googleKeys()).find((k) => k.kid === header.kid);
  if (!jwk) throw new Error("unknown signing key");

  const key = await crypto.subtle.importKey(
    "jwk", jwk,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false, ["verify"]
  );
  const ok = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5", key, b64urlToBytes(s), enc.encode(`${h}.${p}`)
  );
  if (!ok) throw new Error("bad token signature");

  const now = Math.floor(Date.now() / 1000);
  if (claims.exp <= now) throw new Error("token expired");
  if (claims.iat > now + 300) throw new Error("token issued in the future");
  if (!GOOGLE_ISSUERS.includes(claims.iss)) throw new Error("wrong issuer");
  if (claims.aud !== clientId) throw new Error("token was issued for another app");
  if (!claims.email) throw new Error("token carries no email");
  if (claims.email_verified !== true && claims.email_verified !== "true") {
    throw new Error("email is not verified with Google");
  }
  // Optional Workspace restriction. The `hd` claim is the hosted domain
  // Google asserts for the account; a personal gmail.com account has none.
  // The roster is still the control over who may approve. This only keeps
  // accounts outside the church's Workspace from reaching the service.
  if (allowedHd && claims.hd !== allowedHd) {
    throw new Error(
      `${claims.email} is not in the ${allowedHd} Google Workspace`);
  }
  return { email: String(claims.email).toLowerCase(), name: claims.name || claims.email };
}

// ---------------------------------------------------------------------
// The data repository
// ---------------------------------------------------------------------

async function ghGet(env, path) {
  const res = await fetch(`${GH}/repos/${env.DATA_REPO}/contents/${path}`, {
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "stpaul-approval",
    },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`GitHub ${res.status} reading ${path}`);
  const meta = await res.json();
  const text = new TextDecoder().decode(b64urlToBytes(meta.content.replace(/\n/g, "")));
  return { text, sha: meta.sha };
}

async function ghPut(env, path, text, sha, message) {
  const res = await fetch(`${GH}/repos/${env.DATA_REPO}/contents/${path}`, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "Content-Type": "application/json",
      "User-Agent": "stpaul-approval",
    },
    body: JSON.stringify({
      message,
      content: bytesToB64(enc.encode(text)),
      ...(sha ? { sha } : {}),
    }),
  });
  if (!res.ok) throw new Error(`GitHub ${res.status} writing ${path}: ${await res.text()}`);
  return res.json();
}

/**
 * Tell the pipeline repository that something is ready to publish.
 *
 * Optional, and deliberately incapable of failing an approval. By the
 * time this runs the decision is already committed to the data
 * repository, which is the part that matters; this only shortens the
 * wait before it reaches the site. The publish workflow also runs on a
 * schedule, so a dispatch that never arrives costs minutes, not a
 * publication.
 *
 * Nothing here is allowed to throw. An approval that recorded correctly
 * must not report failure because a notification did not go out.
 */
async function notifyPublisher(env, slug, decision) {
  if (decision !== "approved") return;
  if (!env.PUBLISH_REPO || !env.PUBLISH_DISPATCH_TOKEN) return;
  try {
    await fetch(`${GH}/repos/${env.PUBLISH_REPO}/dispatches`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.PUBLISH_DISPATCH_TOKEN}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "stpaul-approval",
      },
      body: JSON.stringify({
        event_type: "approval-recorded",
        // Which Sunday, and nothing else. The workflow reads the
        // curriculum itself; it does not need to be told any of it.
        client_payload: { sunday: slug },
      }),
    });
  } catch (e) {
    // Swallowed on purpose. See the note above.
  }
}

/**
 * The roster, read from the data repository rather than from config, so
 * that adding an approver stays a reviewable commit.
 *
 * Deliberately a small hand parser: it needs a name, a role and an email
 * per reviewer, and pulling a YAML library into a Worker for that is not
 * a trade worth making.
 *
 * It reads the reviewer list and nothing else. Policy (how many
 * approvals, which roles, whether signatures are required) is enforced
 * by tools/verify.py at gate time, with a real YAML parser. An earlier
 * version of this function also parsed the policy block, which looked
 * like it worked while silently dropping `required_roles` because that
 * value is a list and this parser only reads scalars. A half-working
 * copy of a rule is worse than no copy: the enforcing one lives in
 * exactly one place.
 */
function parseRoster(yamlText) {
  const reviewers = [];
  let section = null;
  let current = null;

  for (const raw of yamlText.split("\n")) {
    const line = raw.replace(/\t/g, "  ");
    if (/^\s*#/.test(line) || !line.trim()) continue;

    if (/^policy:/.test(line)) { section = "policy"; continue; }
    if (/^reviewers:/.test(line)) { section = "reviewers"; continue; }
    if (section !== "reviewers") continue;

    {
      const start = line.match(/^\s*-\s*([a-z_]+):\s*(.*)$/i);
      if (start) {
        current = {};
        reviewers.push(current);
        current[start[1]] = start[2].replace(/^["']|["']$/g, "").trim();
        continue;
      }
      const kv = line.match(/^\s+([a-z_]+):\s*(.*)$/i);
      if (kv && current) current[kv[1]] = kv[2].replace(/^["']|["']$/g, "").trim();
    }
  }
  return { reviewers };
}

// ---------------------------------------------------------------------
// Request handling
// ---------------------------------------------------------------------

async function authenticate(request, env) {
  const auth = request.headers.get("Authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (!token) throw new Error("not signed in");

  const identity = await verifyGoogleToken(
    token, env.GOOGLE_CLIENT_ID, env.ALLOWED_HD || "");

  const rosterFile = await ghGet(env, "standards/reviewers.yml");
  if (!rosterFile) throw new Error("roster not found in the data repository");
  const { reviewers } = parseRoster(rosterFile.text);

  const entry = reviewers.find(
    (r) => (r.email || "").toLowerCase() === identity.email);
  if (!entry) {
    // Say who was rejected. A reviewer signing in with the wrong Google
    // account should be able to see that is what happened.
    throw new Error(
      `${identity.email} is not on the reviewer roster in standards/reviewers.yml`);
  }
  return { identity, entry };
}

async function handleApprove(request, env, origin) {
  const { identity, entry } = await authenticate(request, env);
  const body = await request.json();

  const slug = String(body.sunday || "");
  if (!/^\d{4}-\d{2}-\d{2}-[a-z0-9-]+$/.test(slug)) {
    return json({ error: "bad sunday slug" }, 400, origin);
  }
  // Never infer an approval. This defaulted anything it did not
  // recognise to "approved", and the review app was sending "APPROVE"
  // and "REQUEST_CHANGES", so a pastor clicking "Request changes" had an
  // approval signed and committed in his name. The one safe default at
  // this line is no default at all: a decision this service cannot name
  // exactly is one it refuses to record.
  //
  // The values are the constants in tools/stpaul/approval.py, which is
  // what counts them at gate time. If those ever gain a third, this list
  // is the place it has to be added.
  const DECISIONS = ["approved", "changes_requested"];
  if (!DECISIONS.includes(body.decision)) {
    return json({
      error: `unrecognised decision ${JSON.stringify(body.decision ?? null)}. ` +
             `Expected one of: ${DECISIONS.join(", ")}.`,
    }, 400, origin);
  }
  const decision = body.decision;

  // The hash comes from the repository, never from the client. CI writes
  // review/data/<slug>.json from the content itself, so what gets
  // approved is what is actually committed.
  const bundle = await ghGet(env, `review/data/${slug}.json`);
  if (!bundle) {
    return json({ error: `no review data for ${slug}. Run tools/make_review.py and commit.` },
                404, origin);
  }
  const review_data = JSON.parse(bundle.text);
  const contentHash = review_data.content_sha256;

  // If the reviewer's page has gone stale, refuse rather than sign
  // something they were not looking at.
  if (body.content_sha256 && body.content_sha256 !== contentHash) {
    return json({
      error: "The content changed while you were reading. Reload and review again.",
      shown: body.content_sha256, current: contentHash,
    }, 409, origin);
  }

  // Refuse to sign an approval over content that breaks a rule it did
  // not break before.
  //
  // This is weaker than blocking on the raw count, and the weakening was
  // decided rather than overlooked. The Sundays imported from the
  // archive carry violations that were already in print, several of them
  // the pastor's to rule on rather than anyone's to fix, and
  // standards/lint-baseline.json is the record of that debt. Blocking on
  // the raw count meant no imported Sunday could ever be approved: the
  // three live ones stood at 98, 109 and 212, so the gate refused
  // everything, which is not a stricter gate but an unusable one. What
  // is new is still refused, and lint.py --baseline draws its line in
  // exactly the same place.
  //
  // A bundle written before new_errors existed cannot tell new from
  // known, so it falls back to the raw count and refuses. Failing closed
  // on a stale bundle is the same instinct as refusing a decision this
  // service cannot name: when it does not know, it does not sign.
  const lint = review_data.lint || {};
  const baselined = typeof lint.new_errors === "number";
  const blocking = baselined ? lint.new_errors : (lint.errors || 0);
  if (decision === "approved" && blocking > 0) {
    return json({
      error: baselined
        ? `${blocking} rule violation(s) introduced since the baseline. ` +
          `Nobody should be asked to approve text that breaks a written ` +
          `standard it did not break before.`
        : `${blocking} rule violation(s) outstanding, and this review bundle ` +
          `predates the baseline count, so which of them are new cannot be ` +
          `told from here. Regenerate it with tools/make_review.py and commit.`,
    }, 409, origin);
  }

  const review = {
    reviewer: entry.name,
    role: entry.role || "",
    decision,
    at: new Date().toISOString().replace(/\.\d{3}Z$/, "+00:00"),
    content_sha256: contentHash,
    note: String(body.note || "").slice(0, 2000),
    github: "",
    method: "google",
    verified_identity: `google:${identity.email}`,
  };

  const path = `approvals/${slug}.approval.json`;
  const existing = await ghGet(env, path);
  const record = existing ? JSON.parse(existing.text) : {
    sunday: slug, algorithm: "stpaul-canonical-sha256/1", reviews: [],
  };
  record.content_sha256 = contentHash;
  record.files = review_data.files || record.files || {};
  record.reviews = record.reviews || [];
  record.reviews.push(review);

  await ghPut(
    env, path, JSON.stringify(record, null, 2) + "\n", existing?.sha,
    `${decision === "approved" ? "Approve" : "Request changes on"} ${slug}` +
    `\n\nReviewer: ${entry.name} <${identity.email}> (${entry.role})\n` +
    `Content: ${contentHash}\n` +
    `Recorded by the approval service, which verified the reviewer's ` +
    `Google identity against standards/reviewers.yml.\n`
  );

  // After the commit, never before: publishing is downstream of the
  // approval being recorded, not a condition of it.
  await notifyPublisher(env, slug, decision);

  return json({ ok: true, decision, reviewer: entry.name,
                content_sha256: contentHash, at: review.at }, 200, origin);
}

async function handleSunday(request, env, origin, slug) {
  await authenticate(request, env);
  const bundle = await ghGet(env, `review/data/${slug}.json`);
  if (!bundle) return json({ error: "not found" }, 404, origin);
  return json(JSON.parse(bundle.text), 200, origin);
}

async function handleIndex(request, env, origin) {
  const { entry } = await authenticate(request, env);
  const bundle = await ghGet(env, "review/data/index.json");
  if (!bundle) return json({ sundays: [] }, 200, origin);
  return json({ ...JSON.parse(bundle.text), you: entry }, 200, origin);
}

export default {
  async fetch(request, env) {
    // Compared case-insensitively: DNS is case-insensitive and the record
    // may be written SchoolReview.stpaulaustin.org, while browsers send
    // the Origin header lowercased. A mixed-case config value would
    // otherwise reject every request with nothing to show why.
    const allowed = (env.ALLOWED_ORIGIN || "").trim().toLowerCase();
    const sent = (request.headers.get("Origin") || "").trim().toLowerCase();
    const origin = allowed || "*";
    if (allowed && sent && sent !== allowed) {
      return json({ error: `origin ${sent} is not allowed` }, 403, origin);
    }
    const url = new URL(request.url);

    if (request.method === "OPTIONS") return json({}, 204, origin);

    // The app and its configuration. config.js is generated rather than
    // stored so the client ID exists in exactly one place, wrangler.toml,
    // and cannot drift from what this service verifies tokens against.
    if (request.method === "GET" && (url.pathname === "/" || url.pathname === "/index.html")) {
      return new Response(APP_HTML, {
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "no-cache",
          "X-Content-Type-Options": "nosniff",
          "Referrer-Policy": "same-origin",
        },
      });
    }
    if (request.method === "GET" && url.pathname === "/config.js") {
      const cfg = {
        // Relative, so the app talks to whatever host served it. Same
        // origin by construction.
        service: "/api",
        googleClientId: env.GOOGLE_CLIENT_ID || "",
        churchName: env.CHURCH_NAME || "St. Paul Lutheran Church, Austin",
      };
      return new Response(
        `window.STPAUL_CONFIG = ${JSON.stringify(cfg, null, 2)};
`, {
          headers: {
            "Content-Type": "application/javascript; charset=utf-8",
            "Cache-Control": "no-cache",
          },
        });
    }

    try {
      if (url.pathname === "/api/sundays" && request.method === "GET") {
        return await handleIndex(request, env, origin);
      }
      const m = url.pathname.match(/^\/api\/sunday\/([\w.-]+)$/);
      if (m && request.method === "GET") {
        return await handleSunday(request, env, origin, m[1]);
      }
      if (url.pathname === "/api/approve" && request.method === "POST") {
        return await handleApprove(request, env, origin);
      }
      return json({ error: "not found" }, 404, origin);
    } catch (e) {
      const msg = String(e.message || e);
      // Anything about identity is the caller's problem to fix, and
      // saying which is the difference between a usable error and a
      // shrug. Nothing here leaks curriculum content.
      const status = /signed in|token|roster|issuer|expired|verified|Workspace/i.test(msg)
        ? 401 : 500;
      return json({ error: msg }, status, origin);
    }
  },
};
