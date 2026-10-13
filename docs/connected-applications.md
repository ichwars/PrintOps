# Sign in to external applications with PrintOps

Connected applications receive a user's current identity after explicit consent.
They receive **no PrintOps JWT, refresh token, or API access token**. The protocol
is a small authorization-code identity exchange, not an OpenID Connect provider.
The permission list is informational; it grants no rights on the PrintOps API.

## Register the application

Enable PrintOps authentication. A user with `settings:update` can manage apps in
**Settings → Integrations → API & metrics → Connected applications**
(`/settings?tab=integrations&sub=api-metrics`). Register one exact HTTP(S) callback
URL. LAN HTTP callbacks are supported; fragments, embedded credentials, whitespace
and backslashes are rejected. No callback URL is fetched by PrintOps.

Save the returned `poa_…` client ID and `pos_…` secret on your application's server.
Only creation and rotation disclose the secret. PrintOps stores a password hash.
Rotation replaces the secret and invalidates pending codes. Disabling, deleting,
or changing the callback also invalidates pending codes. A callback change clears
saved consents. Editing the display name keeps the same application identity.

Management uses the existing PrintOps JWT session and `settings:update`:

| Method | Path under `/api/v1` | Result |
| --- | --- | --- |
| GET | `/connect/apps` | Registered apps, never secrets |
| POST | `/connect/apps` | Create with `{ "name": "Workshop", "redirect_uri": "https://workshop.example/callback" }`; secret shown once |
| PATCH | `/connect/apps/{id}` | Update `name`, `redirect_uri`, and/or `enabled` |
| POST | `/connect/apps/{id}/rotate-secret` | Replace and show the new secret once |
| DELETE | `/connect/apps/{id}` | Delete app, consents and pending codes |

## Request consent

1. Generate a cryptographically random PKCE verifier (43–128 unreserved ASCII
   characters) and unpredictable `state`; keep both in your application's server
   session for this sign-in attempt.
2. Compute `BASE64URL(SHA256(verifier))` without padding.
3. Redirect the browser to PrintOps:

```text
/connect/authorize?client_id=poa_…&redirect_uri=URL_ENCODED_EXACT_CALLBACK&code_challenge=BASE64URL_SHA256&code_challenge_method=S256&state=OPAQUE_STATE
```

The normal PrintOps login route preserves this entire query across login. The
consent page names the application, account and validated callback and explains
that user ID, username, email, groups, administrator status and current permissions
are shared. A previous consent never automatically approves a new request.
API keys cannot provide personal consent. Consent can be framed by the same origin
only; other existing frame policies remain in force.

Approval redirects to the registered callback with `code` and the original `state`.
Denial redirects with `error=access_denied` and `state`, without issuing a code.
An invalid application/callback request does not redirect. Existing callback query
parameters are preserved; protocol parameters `code`, `error`, and `state` are replaced.
Your application must verify the returned state against its saved session before
exchanging the code. Do not put client secrets in browser URLs or browser storage.

The SPA uses `GET /api/v1/connect/authorize/info?client_id=…&redirect_uri=…`
and `POST /api/v1/connect/authorize` with the same four authorization fields.
Both endpoints require an active user's JWT and enabled authentication.

## Exchange the code on your server

Within **60 seconds**, send JSON to `POST /api/v1/connect/token`:

```json
{
  "grant_type": "authorization_code",
  "client_id": "poa_EXAMPLE",
  "client_secret": "pos_EXAMPLE",
  "code": "CODE_FROM_CALLBACK",
  "redirect_uri": "https://workshop.example/callback",
  "code_verifier": "VERIFIER_SAVED_IN_YOUR_SERVER_SESSION"
}
```

The exchange endpoint authenticates the application using its own secret; no
PrintOps session header is required. A successful response contains only:

```json
{
  "user": {
    "sub": "23d1d329450ddd5846054fbe9ca122a3d",
    "id": 42,
    "username": "operator",
    "email": "operator@example.test",
    "is_admin": false,
    "groups": ["Operators"],
    "permissions": ["printers:read"]
  },
  "issued_at": "2026-10-13T12:00:00Z"
}
```

Create your own application session from that snapshot using your own authorization
policy. **Bind external accounts to the stable `sub` together with the PrintOps
instance URL.** Numeric `id` and `username` are current lookup/display values and
can be reused after account deletion. The subject survives renames but never
transfers to a recreated account. It is not a signed identity token and must be received directly from the
trusted PrintOps server. PrintOps checks the live active account and current groups
and permissions at exchange time. Renaming a user cannot transfer a code; even
SQLite reuse of a deleted numeric user ID cannot revive the old identity.

Codes are atomically single use, bound to the app, exact callback, current app
configuration, nonreused user identity and S256 challenge. A syntactically valid
exchange with the correct app secret spends the code even if its callback or PKCE
verifier is wrong. Retry sign-in from the beginning after an exchange failure.

Errors use `detail.error` for `invalid_client` (401), `invalid_grant` (400), or
`auth_disabled` (400). Consent returns 409 when authentication is disabled.
Malformed input returns 422. Twenty failed exchanges per client or source IP in the
existing 15-minute window produce 429; failure events persist across workers and
restarts. The existing event-counter limiter is a soft concurrency limit.

## Storage and deployment

The additive startup migration creates `connected_apps` and `connected_app_grants`
and backfills a random `users.connected_identity` exactly once for legacy accounts.
Codes and failure events use the existing ephemeral authentication tables, without
changing MFA, OIDC, camera or media token purposes. Explicit cleanup also works on
SQLite deployments where foreign-key enforcement is off. PostgreSQL schema and SQL
compilation are checked; runtime concurrency tests use committed SQLite transactions.

User documentation lives in [the existing feature guide](upstream-features-guide.md).
The separate wiki/website repository was unavailable during this integration.
