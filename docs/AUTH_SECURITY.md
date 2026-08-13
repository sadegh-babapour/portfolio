# Authentication Security Boundary

Last reconciled: 2026-08-13

## Scope

Phase 5 adds Google OpenID Connect only for authentication. It does not request
Drive, Calendar, contacts, or offline access, and it does not store Google
access tokens or refresh tokens. Public pages remain usable without signing in.

## Accepted flow

```text
browser -> same-origin login start -> durable state + nonce + browser binding
        -> Google authorization-code flow (`openid email profile`)
        -> callback validates state, browser binding, nonce, issuer, audience,
           signature, expiry, and `email_verified`
        -> Google provider + stable `sub` identity -> local user and roles
        -> rotated opaque server session -> HttpOnly Secure SameSite=Lax cookie
```

The authorization code and Google ID token exist only during the callback. The
application persists the stable Google `sub`, current verified email, display
name, local roles, and bounded audit state. It never uses email alone to merge
two external identities.

## Session boundary

- Cookies contain only a high-entropy opaque session token; PostgreSQL stores
  its SHA-256 digest.
- Sessions expire after 12 hours by default, rotate at authentication, support
  explicit revocation, and are rejected for disabled users.
- Authentication-changing POST requests require same-origin checks and a
  session-bound CSRF token whose digest is stored with the session.
- Login state expires after 10 minutes and is single-use. State, nonce, and a
  separate browser-binding value are stored only as digests.
- Return paths must be root-relative; external and protocol-relative redirects
  are rejected.

## Roles and administration

Every authenticated user receives `registered`. `admin` is granted only when a
verified identity matches the configured Google-subject or email allowlist.
Stable Google subjects are preferred. Registration never self-assigns admin,
and every protected endpoint must enforce its role server-side rather than
trusting hidden UI.

## Privacy and retention

- Do not store passwords, Google access/refresh tokens, raw session tokens, raw
  OIDC state/nonce values, or raw IP addresses.
- Auth events contain state transitions and bounded metadata, not credentials or
  complete provider payloads.
- Expired login states and sessions require scheduled deletion before the auth
  feature leaves limited production testing.
- The site needs implemented privacy/terms pages describing Google identity
  data, purposes, retention, logout/revocation, and contact details before broad
  public registration.

## Dependency and configuration gates

The callback requires an ID-token verifier. The recommended production
dependency is `google-auth`, which validates Google signature, issuer, audience,
and token time claims while the existing `requests` package performs the code
exchange. Adding it requires repository-owner approval.

Required production variables:

```dotenv
AUTH_PUBLIC_BASE_URL=https://bizqlab.com
GOOGLE_OIDC_CLIENT_ID=<web client id>
GOOGLE_OIDC_CLIENT_SECRET=<web client secret>
AUTH_ADMIN_GOOGLE_SUBJECTS=<preferred comma-separated stable subjects>
AUTH_ADMIN_EMAILS=<optional comma-separated verified-email fallback>
AUTH_SESSION_TTL_HOURS=12
AUTH_LOGIN_STATE_TTL_MINUTES=10
```

The Google web client must authorize exactly
`https://bizqlab.com/api/auth/google/callback` for production. Local development
may separately authorize `http://localhost:8086/api/auth/google/callback`.

## Remaining gates

- Owner approval for `google-auth` as a production dependency.
- Google Cloud OAuth web-client credentials and consent-screen configuration.
- Owner selection of which existing or new case-study details become
  `registered` content; current projects remain public until then.
- Endpoint, session-service, logout/revocation, locked-card, retention, hostile
  callback, and production browser tests.
