# Contact Threat Model

## Protected assets

- Domain-mail reputation and SMTP credentials.
- Visitor email address and message contents.
- Owner inbox availability.
- Integrity of verification, delivery, and future admin state.

## Trust boundaries

The browser is untrusted. FastAPI validates origin, signed double-submit CSRF
state, field bounds, honeypot state, rate limits, and Turnstile before accepting
a pending message. Cloudflare attests only to the challenge; it does not prove
identity. Control of the submitted inbox is established only when its short-
lived, single-use verification link is consumed.

PostgreSQL is the durable workflow authority. SMTP is called only after a
pending record exists and again after verification. Secrets are environment
configuration and never enter browser code, database rows, logs, or Git.

## Principal threats and controls

| Threat | Controls |
|---|---|
| Automated spam and Siteverify flooding | Hidden field, per-IP/per-email database throttles, Turnstile, bounded inputs |
| Forged/replayed Turnstile response | Mandatory server Siteverify, hostname/action checks, Cloudflare single-use expiry |
| CSRF submission | SameSite HttpOnly cookie, signed one-hour token, matching header, strict allowed origins |
| Forged sender identity | Thirty-minute random verification link; verified address used only as `Reply-To` |
| Verification-link theft/replay | Only a digest is stored; row lock and `verified_at` make consumption single-use |
| Header injection | Normalization, length limits, email validation, fixed authenticated sender |
| Enumeration | Generic acceptance text independent of address state |
| Sensitive logs | Audit events contain state names and IDs, not raw IPs, tokens, bodies, or credentials |
| Cross-domain widget reuse | Cloudflare hostname restriction plus server-side hostname/action validation |
| Transit-data coupling | All new tables and Alembic state are isolated in the `portfolio` schema |

## State machine

```text
pending_verification
  -> verification_delivery_failed
  -> verified -> delivered
              -> delivery_failed
```

Expired, missing, and previously consumed tokens do not change state. Failed
final deliveries remain durable for a future admin retry workflow; visitors are
told not to create duplicate submissions.

## Retention follow-up

Phase 6 must add scheduled retention for attempts, expired pending messages,
delivered messages, and audit events before the admin console exposes them.
Until then, only keyed IP digests are stored and no raw IP address is retained.
