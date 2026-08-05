# Product and Engineering Roadmap

Last updated: 2026-08-05

## Product objective

Build a credible data-engineering and data-analysis portfolio that demonstrates
production software judgment, data pipelines, database design, analytics,
visualization, security, and frontend delivery. The site should let a recruiter
understand the work without reading the repository, while preserving deeper
authenticated material for users who choose to sign in.

This roadmap records goals and sequencing. Technology choices marked as
decision gates are not accepted architecture until the review phase produces
evidence and an ADR records the choice.

## Delivery principles

- Review before refactoring and refactor before adding major platform features.
- Preserve the verified Calgary production path while removing only proven-dead
  legacy code.
- Do not introduce an ORM as a blanket replacement for tuned transit SQL.
- Keep public browsing useful; authentication should unlock extra content, not
  obstruct the basic portfolio.
- Treat identity, analytics, contact messages, and location as personal data.
- Never represent predictions or inferred train progress as precise live GPS.
- Each phase ends with tests, documentation, deployment, and a production smoke
  test before the next phase begins.
- During implementation, every progress update reports both levels in the form
  `Overall: Step X/9` and `Current step: mini-step Y/N`, with completed work,
  current work, and the next gate stated plainly.

## Phase 1 — Senior code and architecture review

Status: technically complete and approved on 2026-08-05.

### Goal

Establish an evidence-backed baseline before deleting or redesigning code.

### Review scope

- Python/NiceGUI/FastAPI application lifecycle, routes, components, error
  handling, async/background work, configuration, and security boundaries.
- Express API routing, validation, SQL ownership, pooling, error behavior,
  response contracts, CORS, logging, and shutdown behavior.
- Python realtime poller parsing, transactions, idempotency, scheduling,
  retention, retries, observability, and testability.
- React component boundaries, state/effect ownership, API client behavior,
  accessibility, responsive behavior, generated-build policy, and maintainable
  explanation for a developer new to React.
- PostgreSQL schemas, migrations, indexes, views, data retention, backup/recovery,
  and the boundary between direct SQL and future ORM-owned portfolio tables.
- Dependency, secret, authentication, privacy, accessibility, performance,
  deployment, and test-coverage audits.
- Exact legacy dependency graph: routes, modules, environment variables,
  database objects, startup hooks, imports, and Railway runtime usage.

### Deliverables

- `docs/CODE_REVIEW.md` with prioritized findings: critical, high, medium, low.
- A current component/data-flow diagram and deletion-candidate inventory.
- A React walkthrough describing state, effects, polling, map layers, selection,
  and the production build in plain language.
- Proposed ADRs and a sequenced refactor list; no broad rewrite during review.
- A test matrix showing current coverage and required characterization tests.

### Exit criteria

- Every deletion candidate has evidence that production does not use it.
- High-risk issues have owners and tests or an explicitly accepted risk.
- The user approves the proposed target architecture before implementation.

## Phase 2 — Characterize and remove the legacy transit stack

Status: complete and deployed on 2026-08-05.

### Goal

Remove the older public-schema NiceGUI transit implementation without changing
the verified React/Express/poller behavior.

### Planned work

- Add characterization/smoke tests around the current production entry points.
- Remove legacy startup hooks and Python JSON transit endpoints from `app/main.py`.
- Remove the hidden `/transit` NiceGUI page, superseded map variants, old
  poller/updater/load helpers, and unused public-schema SQL only after the phase-1
  dependency inventory confirms each target.
- Remove dependencies and environment variables used only by deleted code.
- Decide whether old SQL belongs in a tagged archive/recovery reference rather
  than the active tree.
- Verify web, API, worker, database bootstrap, and Railway deployment separately.

### Exit criteria

- One Calgary implementation and one documented schema remain active.
- Clean installs, tests, builds, local smoke tests, and production checks pass.
- No Railway service imports or starts deleted modules.

## Phase 3 — Content model and portfolio case studies

Status: implemented and deployed at `3e23075`.

### Goal

Replace code-embedded sample content with structured data and turn Projects
into recruiter-friendly case studies.

### Planned content model

- Start the on-page résumé timeline—not the separately deployed résumé PDF—plus
  skills, navigation metadata, and stable project copy in validated JSON or
  YAML so normal edits do not require Python changes.
- Model each case study with summary, business problem, architecture, data
  sources, pipeline, analysis, technologies, screenshots, measurable outcomes,
  limitations, repository/demo links, and visibility level.
- Keep source-controlled, reviewable content static initially. Move content to
  PostgreSQL only when admin editing is implemented and provides clear value.
- Store large/private media on the portfolio volume or future object storage;
  keep build-critical public assets in Git.

### Data access decision gate

- Evaluate SQLAlchemy 2.x plus Alembic for new portfolio-domain tables such as
  users, content, contact messages, and audit events. Keep those ORM-owned
  tables in a dedicated schema within the existing PostgreSQL database so they
  remain isolated from the `transit` schema without adding another database.
- Keep Express transit queries and complex PostgreSQL views as explicit SQL
  unless the review demonstrates a concrete ORM benefit.
- Define repository/service boundaries before selecting the ORM.

### Implemented

- Versioned JSON contracts and dependency-free validation for the on-page
  timeline and project case studies.
- Recruiter-focused project cards with explicit business, architecture,
  pipeline, outcome, limitation, provenance, and visibility fields.
- A read-only Git-content boundary now; ORM-owned PostgreSQL persistence when
  admin editing and operational monitoring are implemented.
- Owner personalization of the clearly marked timeline placeholders remains a
  content task rather than a code dependency.

## Phase 4 — Contact experience, bot defense, and verified senders

Status: application and migration implemented locally; external configuration,
deployment, and production end-to-end verification pending.

### Goal

Create a polished contact page that sends real messages while limiting spam and
confirming control of the supplied reply address.

### User flow

1. Visitor submits name, email, subject/category, and message.
2. Immediately before submission, the visitor completes Cloudflare Turnstile;
   the server validates length/format, honeypot, rate limit, and the resulting
   single-use bot-defense proof.
3. Unauthenticated visitors receive a short-lived verification link at the
   supplied address; the message remains pending until clicked.
4. Verified signed-in users bypass repeated email verification.
5. After verification, the system delivers or forwards the message through the
   configured domain-mail provider and records delivery state without exposing
   mail credentials.

Email verification proves control of an inbox at that moment; it does not prove
the person's real-world identity. Google sign-in can provide a stronger account
link but should not be mandatory for an ordinary recruiter contact.

### Abuse controls

- Server-side validation, CSRF protection, generic responses, size limits,
  honeypot field, per-IP/per-email throttles, replay-resistant expiring tokens,
  and structured audit events.
- Cloudflare Turnstile free plan is the accepted first bot-defense provider.
  Verify every token server-side immediately before accepting the message and
  combine it with the other controls above. ALTCHA remains a possible future
  self-hosted experiment, not the initial contact implementation.
- Do not rely on CAPTCHA alone; rate limits and verification remain mandatory.

### UX redesign

- More whitespace, clear contact expectations, response-time note, topic
  selector, concise privacy statement, direct professional links, success/error
  states, and mobile-friendly spacing.

## Phase 5 — Authentication and protected portfolio content

### Goal

Let visitors see that deeper material exists while requiring authentication to
open selected case-study details or datasets.

### Planned model

- Google OpenID Connect as the first identity provider; store the provider's
  stable subject identifier, not passwords.
- Server-managed secure sessions with HttpOnly, Secure, SameSite cookies,
  rotation, expiry, CSRF protection, and logout/revocation.
- Roles: public, registered user, and admin. Admin access uses an explicit email
  or subject allowlist plus role checks; registration never grants admin rights.
- Locked cards remain visible with a clear explanation and sign-in action.
- Record consent/privacy requirements before enabling identity or analytics.

### Tables to evaluate

- users, external identities, sessions, login events, role assignments,
  protected-content access events, email-verification tokens, contact messages,
  and audit events.

## Phase 6 — Admin console and analytics

### Goal

Provide an admin-only operational view without turning the portfolio into a
surveillance system.

### Admin capabilities

- Registered users, roles, last login, session revocation, contact-message
  state, content publication state, job/cache health, and aggregate page usage.
- Append-only audit log for privileged actions.
- Minimum-data defaults, bounded retention, no raw secrets, and no unnecessary
  long-term raw IP storage.

### Analytics decision gate

- First-party PostgreSQL events for product-specific demonstrations and the
  admin console.
- GA4 is deferred. Reconsider it only if its external reporting later adds
  value after a privacy/cookie-consent review; it would complement rather than
  replace application audit data.

## Phase 7 — Data platform and chart overhaul

### Goal

Demonstrate both cached analytical products and live database-backed analysis.

### Planned work

- Replace placeholder/empty ECharts with intentional case-study dashboards.
- Define chart contracts, empty/loading/error states, accessible summaries,
  responsive layouts, theme behavior, and data provenance timestamps.
- Use scheduled jobs for slow-changing datasets. Materialize a versioned JSON
  snapshot weekly only when the job succeeds, then let public charts read that
  small cache without querying PostgreSQL on every visit.
- Use API queries for charts whose value is freshness; add bounded caching,
  timeouts, indexes, query budgets, and freshness labels.
- Show pipeline metadata—source, last successful refresh, row count, duration,
  and data-quality checks—as part of the portfolio story.
- Keep snapshot files reproducible and non-sensitive; do not use the volume as
  an undocumented database.

## Phase 8 — Toronto subway schematic

### Goal

Add a Toronto rail-only experience using an SVG line/station schematic and
honest realtime semantics. Station-level or between-station estimates are
acceptable; precise GPS coordinates are not a requirement when the UI clearly
labels what the feed actually represents.

### Required data spike

- Evaluate the repository owner's candidate TTC endpoint only when this phase
  begins: `https://bustime.ttc.ca/gtfsrt/vehicles?debug`.
- Confirm current official TTC static GTFS, subway trip updates, alerts, route
  identifiers, direction semantics, station/platform mapping, refresh limits,
  and licensing.
- Determine whether the candidate feed provides subway vehicle positions,
  station events, or trip/stop predictions and establish its real refresh rate
  and reliability. If it supports only predictions, display a train at a
  station or between known stations as an estimate and label it clearly; do not
  imply GPS.
- Compare the supplied TTC endpoint with already-established realtime rail feeds
  internationally. The demonstration city is not fixed: prefer a dependable,
  documented feed that supports the strongest honest portfolio experience.
- Do not begin feed or city selection until the preceding review, cleanup,
  content, contact, identity/admin, and data-platform phases are complete.

### Proposed UI

- SVG paths for subway lines and station circles.
- Direction-aware trains, current/next station state, blinking next stop,
  disruption overlays, accessible text equivalents, and responsive zoom/pan.
- Reuse shared transit contracts only after Calgary cleanup establishes a
  clean city-adapter boundary.

## Phase 9 — Nearby Calgary stops and arrivals

### Goal

Turn the Calgary demonstration into a useful stop-discovery experience.

### Proposed flow

- Ask for browser geolocation only after a clear user action and explanation.
- If declined, allow a draggable pin or address/map selection without blocking
  the rest of the page.
- Find nearby stops using indexed geography or a bounded distance query.
- Selecting a stop shows scheduled/realtime arrivals in the next 10–15 minutes,
  route/headsign, prediction freshness, accessibility, and service alerts.
- Do not retain precise user location by default; document any analytics before
  collecting coarse location events.

## Recommended execution order

1. Senior code/architecture review.
2. Characterization tests and legacy removal.
3. Structured content and polished case studies.
4. Contact delivery, verification, and bot defense.
5. Authentication and protected content.
6. Admin console and privacy-aware analytics.
7. Data platform and chart overhaul.
8. Toronto subway data spike and schematic implementation.
9. Calgary nearby stops and arrivals.

The sequence may be adjusted after phase 1, but security and identity work
should not be mixed into legacy deletion, and Toronto should not begin until
the existing transit boundary is clean and tested.
