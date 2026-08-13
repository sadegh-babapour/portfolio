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
  complete provider payloads. Login starts opportunistically remove expired
  login states, sessions, and events older than the configured retention.
- `/privacy`, `/terms`, and `/account` describe identity use and provide logout
  plus local-account deletion. Public registration is active, and the owner has
  confirmed real Gmail login and logout.

## Dependency and configuration gates

The owner-approved production dependency is `google-auth`, which validates
Google signature, issuer, audience, and token time claims while the existing
`requests` package performs the code exchange.

Required production variables:

```dotenv
AUTH_PUBLIC_BASE_URL=https://bizqlab.com
GOOGLE_OIDC_CLIENT_ID=<web client id>
GOOGLE_OIDC_CLIENT_SECRET=<web client secret>
AUTH_ADMIN_GOOGLE_SUBJECTS=<preferred comma-separated stable subjects>
AUTH_ADMIN_EMAILS=<optional comma-separated verified-email fallback>
AUTH_SESSION_TTL_HOURS=12
AUTH_LOGIN_STATE_TTL_MINUTES=10
AUTH_EVENT_RETENTION_DAYS=90
```

The Google web client must authorize exactly
`https://bizqlab.com/api/auth/google/callback` for production. Local development
may separately authorize `http://localhost:8086/api/auth/google/callback`.

## Google Console setup

In Google Cloud Console, select or create the production project, then open
**Google Auth Platform**. Configure **Branding**, **Audience**, and **Data
Access** with only `openid`, `email`, and `profile`. Under **Clients**, create an
OAuth client of type **Web application** and add the production callback below.
Use a separate development project/client for localhost, as required by
Google's OAuth production policy.

Production links supplied to Google should be:

- Home: `https://www.bizqlab.com`
- Privacy: `https://www.bizqlab.com/privacy`
- Terms: `https://www.bizqlab.com/terms`
- Authorized redirect: `https://bizqlab.com/api/auth/google/callback`

Put the resulting client ID and client secret directly in the Railway
`portfolio` service as `GOOGLE_OIDC_CLIENT_ID` and
`GOOGLE_OIDC_CLIENT_SECRET`; never paste them into source or documentation.

## Google branding verification

The public application now uses the exact name `Bizqlab`, and its canonical
homepage publicly explains the portfolio purpose, optional Google sign-in, and
identity-data use with a direct Privacy link. This addresses the application
content and name-match findings.

The exact consent-screen logo is also public and visibly used on the homepage,
in both navigation shells, as the favicon, and in Open Graph/structured website
metadata at `https://www.bizqlab.com/static/bizqlab_logo.png`.

Domain ownership cannot be completed in source code. Using the same Google
account that is a Cloud project Owner or Editor:

1. Open [Google Search Console](https://search.google.com/search-console) and
   add a **Domain property** for `bizqlab.com` (not a URL-prefix property).
2. Copy Google's TXT verification value into the DNS for `bizqlab.com`.
3. Return to Search Console and select **Verify**.
4. Reply to the OAuth review email or resubmit Brand verification.

The owner confirmed completion of this DNS verification through Cloudflare on
2026-08-13. Google findings do not disappear merely because DNS or source code
changed: cancel an in-progress stale verification if necessary, save the
corrected draft, select **Verify branding**, and after approval select
**Publish branding** within seven days.

Google's supporting guidance is available in its
[domain-verification instructions](https://support.google.com/cloud/answer/13804266),
[homepage requirements](https://support.google.com/cloud/answer/13807376), and
[verification requirements](https://support.google.com/cloud/answer/13464321).

Both `bizqlab.com` and `www.bizqlab.com` are active Railway custom domains.
The OAuth callback intentionally remains on the configured apex origin, while
the review homepage stays at the submitted canonical `www` URL.

## Remaining gates

- Google logo/brand-review approval and publication of the approved draft.
- Owner-approved local-account deletion/re-registration and optional stable-
  subject admin allowlist verification.
