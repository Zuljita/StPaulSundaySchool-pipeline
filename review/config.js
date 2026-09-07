// Deployment settings for the review app.
//
// The app is static. It reads review/data/*.json, and for sign-in it
// talks to one small endpoint that performs the GitHub OAuth code
// exchange, because that step needs a client secret and a static page
// cannot hold one.
//
// See review/README.md for the three setup steps. Until authEndpoint is
// filled in the app runs in read-only mode: everything is readable, and
// approving is done from the command line instead.

window.STPAUL_CONFIG = {
  // owner/repo the review app approves pull requests in.
  repo: "",                       // e.g. "Zuljita/StPaulSundaySchool"

  // GitHub OAuth App client id. Public by design; not a secret.
  githubClientId: "",

  // Endpoint that exchanges an OAuth code for a token.
  // A Cloudflare Worker implementation is in review/worker/.
  authEndpoint: "",               // e.g. "https://stpaul-review-auth.workers.dev"

  // Shown in the header.
  churchName: "St. Paul Lutheran Church, Austin",
};
