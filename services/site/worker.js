/**
 * The public Sunday School site.
 *
 * WHAT THIS WORKER IS
 *
 * A map from a URL path to an R2 key, and nothing else. It holds no
 * curriculum, renders no text, and makes no decision about what may be
 * published. Every one of those decisions was already made, upstream and
 * on purpose:
 *
 *   tools/build.py         refuses to render a Sunday that is not approved
 *   tools/publish_site.py  re-checks the hash and the approval, then stages
 *   services/site/publish.ps1   uploads what was staged
 *
 * So this file can be deployed at any time without touching a word of
 * doctrine, and a Sunday can be published without deploying. Those two
 * things moving independently is the point of the split.
 *
 * WHY R2 RATHER THAN STATIC ASSETS
 *
 * Static assets ship with the Worker, and the Worker lives in the public
 * pipeline repository while the curriculum lives in the private data
 * repository. Bundling pages into the deploy would mean this repository's
 * CI needed a checkout of the content to deploy the site, which is the
 * separation the whole project rests on. Reading from R2 keeps the
 * machinery publishable and the content private, and lets whoever holds
 * $STPAUL_DATA publish without any access to Cloudflare deploys.
 *
 * THE ONLY SCRIPT IS THE SERVICE WORKER
 *
 * The pages carry no inline script and no event handlers: curriculum
 * text is escaped when it is rendered, and the CSP below allows no
 * inline execution, so even a missed escape cannot run. The single
 * external script registers a service worker, which is what makes the
 * site installable on a phone and readable without signal.
 *
 * That worker is an addition, never a dependency. Every page renders
 * completely with JavaScript switched off.
 *
 * BINDINGS (wrangler.toml)
 *   SITE                   the R2 bucket publish.ps1 uploads to
 */

// The site is served from R2 under keys that are exactly its URL paths.
// A directory resolves to index.html; nothing else is rewritten.
const INDEX = "index.html";

// Nothing inline may run, nothing may frame the page, and script may
// only come from this origin, which is the registration file and the
// service worker it registers. Fonts come from Google, which is where
// design_standards/tokens/fonts.css points; if the church ever licenses
// desktop cuts and self-hosts them, tighten style-src and font-src to
// 'self' at the same time.
//
// 'unsafe-inline' must never appear here. The reason the escaping in
// render/site.py is not the only line of defence is that this header
// refuses to execute anything the page did not load from this origin as
// a file.
const CSP = [
  "default-src 'none'",
  "script-src 'self'",
  "worker-src 'self'",
  "manifest-src 'self'",
  "connect-src 'self'",
  "style-src 'self' https://fonts.googleapis.com",
  "font-src https://fonts.gstatic.com",
  "img-src 'self' data:",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-ancestors 'none'",
].join("; ");

// HTML is short-lived so a republished Sunday reaches readers quickly.
// Everything else revalidates on its ETag, which R2 supplies.
function cacheControl(key) {
  // The service worker decides how long every other object is held on a
  // reader's phone, so it is the one file a stale copy could pin there.
  // Always revalidated.
  if (key === "sw.js") return "no-cache";
  if (key.endsWith(".html")) return "public, max-age=60, stale-while-revalidate=86400";
  if (key.startsWith("handouts/")) return "public, max-age=300";
  // Icons are content-stable and cheap to revalidate on their ETag.
  if (key.startsWith("assets/")) return "public, max-age=3600";
  return "public, max-age=600";
}

function securityHeaders(headers) {
  headers.set("Content-Security-Policy", CSP);
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  return headers;
}

/**
 * Turn a request path into an R2 key.
 *
 * Returns null for anything that tries to climb out of the bucket. The
 * check is on the decoded path, because "%2e%2e" is "..".
 */
function keyFor(pathname) {
  let path;
  try {
    path = decodeURIComponent(pathname);
  } catch {
    return null;                       // undecodable percent-escapes
  }

  if (path.includes("\\") || path.includes("\0")) return null;

  const parts = path.split("/").filter((p) => p !== "");
  if (parts.some((p) => p === "." || p === "..")) return null;

  const key = parts.join("/");
  if (key === "") return INDEX;
  // A path with no file extension in its last segment is a directory.
  return /\.[A-Za-z0-9]+$/.test(parts[parts.length - 1]) ? key : `${key}/${INDEX}`;
}

async function notFound(bucket) {
  // The front page doubles as the 404 body: a reader who mistypes a
  // Sunday should land on the list of Sundays, not on a dead end.
  const obj = await bucket.get(INDEX);
  const headers = securityHeaders(new Headers({
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store",
  }));
  if (!obj) return new Response("Not found\n", { status: 404, headers });
  return new Response(obj.body, { status: 404, headers });
}

export default {
  async fetch(request, env) {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method not allowed\n", {
        status: 405,
        headers: securityHeaders(new Headers({ Allow: "GET, HEAD" })),
      });
    }

    const url = new URL(request.url);
    const key = keyFor(url.pathname);
    if (key === null) {
      return new Response("Bad request\n", {
        status: 400,
        headers: securityHeaders(new Headers()),
      });
    }

    // onlyIf lets R2 answer a conditional request itself, so an unchanged
    // page costs a 304 and no body. Range is deliberately not handled:
    // every object here is a page of HTML or a one-piece handout, none of
    // them large enough to be worth a partial-content path that would have
    // to be right about 206, 416 and Content-Range to be worth having.
    const obj = await env.SITE.get(key, { onlyIf: request.headers });

    if (obj === null) return notFound(env.SITE);

    const headers = new Headers();
    obj.writeHttpMetadata(headers);
    headers.set("ETag", obj.httpEtag);
    headers.set("Cache-Control", cacheControl(key));
    securityHeaders(headers);

    // R2 returns an object with no body when the caller's If-None-Match
    // or If-Modified-Since already matched.
    if (!("body" in obj) || obj.body === null) {
      return new Response(null, { status: 304, headers });
    }

    return new Response(request.method === "HEAD" ? null : obj.body, {
      status: 200,
      headers,
    });
  },
};
