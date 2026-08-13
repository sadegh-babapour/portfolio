# Next Actions

Last updated: 2026-08-13

## Phase 1: senior review

- [x] Create `docs/CODE_REVIEW.md` with prioritized, evidence-linked findings.
- [x] Review NiceGUI/FastAPI lifecycle, routes, components, configuration,
  security, error handling, and background tasks.
- [x] Review Express API contracts, validation, SQL, pooling, errors, CORS,
  logging, and shutdown behavior.
- [x] Review the realtime poller for parsing, transactions, idempotency,
  scheduling, retention, retry behavior, observability, and testability.
- [x] Review React component/effect boundaries, API access, accessibility,
  responsive behavior, state ownership, and build/deployment policy.
- [x] Explain the React application in plain language for the repository owner.
- [x] Review PostgreSQL schemas, migrations, views, indexes, retention,
  backup/recovery, and likely ORM boundaries.
- [x] Audit dependencies, secrets/configuration, privacy, authentication surface,
  accessibility, performance, tests, and deployment configuration.
- [x] Inventory every legacy module, route, import, environment variable,
  database object, startup hook, and Railway dependency.
- [x] Produce a characterization-test matrix and proposed target architecture
  for approval before changing the system.
- [x] Repository owner approves the six proposed decisions in
  `docs/CODE_REVIEW.md`.

## Phase 2: legacy removal

- [x] Add the initial characterization tests approved in phase 1.
- [x] Remove only proven-unused public-schema/NiceGUI transit paths.
- [x] Remove legacy-only dependencies, snapshot artifacts, SQL, and active-code
  documentation.
- [x] Verify local web boot, Express checks/tests, accepted poller boundaries,
  Python compilation, React lint/build, and dependency consistency.
- [x] Commit and deploy the cleanup, then verify the web, Express API, poller,
  résumé assets, and transit interactions in production.

## Product and platform phases

- [x] Move the on-page résumé timeline—not the PDF—and stable project content
  into validated JSON/YAML.
- [x] Redesign Projects as data-engineering/data-analysis case studies.
- [x] Define the portfolio persistence boundary: Git JSON is initially
  read-only, future admin/dynamic records use an ORM-owned PostgreSQL schema,
  and tuned transit SQL remains independent. ORM selection is deferred until
  the first database-backed portfolio feature.
- [ ] Replace the marked timeline placeholders with factual owner-provided
  career and education data.
- [ ] Finish Contact owner verification: confirm the two labeled Resend test
  emails, then exercise one visible Turnstile submission, verification link,
  one-time final delivery, replay, throttling, and provider-failure cases.
- [ ] Complete Google OIDC, secure sessions, roles, visible locked content, and
  an explicit admin allowlist. The dependency-free schema/config/security
  foundation is implemented locally; approve `google-auth`, configure a Google
  web client, and select protected case-study content before endpoint work.
- [ ] Add an admin console for users, logins, sessions, contact state, content,
  job health, and audit events.
- [ ] Implement bounded first-party operational/audit events; keep GA4 deferred
  unless a later privacy/consent review establishes a concrete need.
- [ ] Replace placeholder/empty charts with cached weekly and live
  PostgreSQL-backed analytical examples.
- [ ] Run a TTC data-capability/licensing spike before implementing the Toronto
  subway SVG schematic; defer the supplied candidate endpoint and comparison
  with established international rail feeds until phase 8.
- [ ] Add Calgary geolocation/manual pin, nearby stops, and 10–15 minute arrivals
  without retaining precise location by default.

## Existing verification debt

- [ ] Expand Express tests for HTTP routing, stops, and database errors; the
  freshness-health service contract now has initial coverage.
- [ ] Add poller fixture/upsert tests and frontend interaction tests.
- [ ] Automate NiceGUI mount and production asset smoke tests.
- [ ] Verify a production active-alert UI when the feed supplies one.
- [ ] Confirm credential rotation status from the recovered checkpoint without
  printing secret values.

## Current recommended next task

Review and deploy the Step-5 authentication foundation after approving the
`google-auth` dependency decision and choosing which case-study details should
be registered-only. Contact inbox/browser confirmation can run in parallel.

See `docs/ROADMAP.md` for phase scope, decision gates, and exit criteria.

Progress updates must include `Overall: Step X/9` and
`Current step: mini-step Y/N`.
