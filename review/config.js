// Deployment settings for the review app.
//
// The app is static and holds no curriculum. It signs the reviewer in
// with Google, then reads and writes through the approval service, which
// is the only thing with access to the private data repository.
//
// See review/README.md for the setup steps. With `service` unset the app
// falls back to reading local review/data/*.json for offline reading,
// and approving is done from the command line instead.

window.STPAUL_CONFIG = {
  // The approval service (services/approval).
  service: "",                    // e.g. "https://stpaul-approval.<sub>.workers.dev"

  // Google OAuth client id. Public by design; not a secret.
  // Must match GOOGLE_CLIENT_ID in the service.
  googleClientId: "",             // e.g. "1234-abc.apps.googleusercontent.com"

  churchName: "St. Paul Lutheran Church, Austin",
};
