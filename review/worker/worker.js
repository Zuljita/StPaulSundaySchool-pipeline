/**
 * GitHub OAuth code exchange for the review app.
 *
 * The review app is a static page and cannot hold a client secret, and
 * GitHub's token endpoint does not send CORS headers, so the exchange
 * cannot happen in the browser either. This is the smallest thing that
 * closes that gap: it takes the temporary code the browser was handed,
 * swaps it for a token using the secret, and returns the token.
 *
 * It deliberately does nothing else. It does not see curriculum text, it
 * does not decide who may approve, and it does not hold a token after the
 * response is written. Who may approve is decided by GitHub repository
 * permissions plus standards/reviewers.yml, both of which live where
 * someone can read them.
 *
 * Deploy: see review/README.md.
 *
 *   wrangler secret put GITHUB_CLIENT_SECRET
 *   wrangler deploy
 */

const ALLOWED_ORIGINS = [
  // Add the origin the review app is served from. Keeping this explicit
  // means a copy of the page hosted somewhere else cannot use this
  // endpoint to mint tokens against the church's repository.
  "http://localhost:8787",
];

function cors(origin) {
  const allow = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Vary": "Origin",
  };
}

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";
    const headers = { ...cors(origin), "Content-Type": "application/json" };

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors(origin) });
    }
    if (request.method !== "POST") {
      return new Response(JSON.stringify({ error: "POST only" }),
        { status: 405, headers });
    }
    if (!ALLOWED_ORIGINS.includes(origin)) {
      return new Response(JSON.stringify({ error: "origin not allowed" }),
        { status: 403, headers });
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return new Response(JSON.stringify({ error: "bad json" }),
        { status: 400, headers });
    }
    if (!body.code) {
      return new Response(JSON.stringify({ error: "missing code" }),
        { status: 400, headers });
    }

    const res = await fetch("https://github.com/login/oauth/access_token", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        client_id: env.GITHUB_CLIENT_ID,
        client_secret: env.GITHUB_CLIENT_SECRET,
        code: body.code,
        redirect_uri: body.redirect_uri,
      }),
    });

    const data = await res.json();
    if (data.error) {
      return new Response(JSON.stringify({ error: data.error_description || data.error }),
        { status: 400, headers });
    }
    // Only the token travels back. Nothing is logged or stored.
    return new Response(JSON.stringify({ access_token: data.access_token }),
      { status: 200, headers });
  },
};
