# Current Project State

Last verified: 2026-08-13

## Project purpose

This repository is the Bizqlab data-engineering and analytics portfolio. It
presents public case studies and demonstrations, with optional Google sign-in
for registered-user Project Lab notes. Its most substantial live project is an
interactive Calgary Transit demonstration built from static GTFS data and
Calgary's VehiclePositions, TripUpdates, and Alerts GTFS-Realtime feeds.

The Calgary Transit feature has one source-level implementation: a React/Leaflet
frontend, Express API, standalone Python poller, and PostgreSQL objects under the
`transit` schema. The superseded NiceGUI/public-schema implementation has been
removed locally and from production.

## Version-control state

- Branch: `main`.
- Deployed functional baseline: `0c0c423` (`Polish member experience and OAuth
  branding`).
- `origin/main` and all three Railway application services run that revision.
  A later continuity-only commit may advance `main` without changing that
  runtime baseline.
- Secret-bearing environment profiles, dependencies, runtime caches, the large
  GTFS stop-times export, and the résumé PDF are ignored.

## Confirmed by current code

### Working or structurally complete

- `python -m app.main` is the declared NiceGUI entry point in `Procfile`.
- NiceGUI portfolio routes exist for home, about, résumé, projects, contact, and
  dashboard; it mounts the React transit build separately.
- Public branding now uses the exact name `Bizqlab`. The public homepage states
  the application's purpose, explains optional Google identity use, links the
  privacy notice, and declares `https://www.bizqlab.com/` as canonical.
- The theme-park dashboard reads committed sample data from
  `dashboard_cache.json` and does not require a live database.
- The React transit frontend implements:
  - a sticky portfolio navigation header with desktop links, a mobile menu,
    and a persistent light/dark theme toggle;
  - delayed playback from real observation history;
  - bus, BRT/MAX, featured, and all filters;
  - route lines and selected-route/corridor highlighting;
  - stopped and stale marker states;
  - selected-vehicle stops and alerts;
  - responsive desktop/mobile layout and multiple basemaps.
- The Express API implements health, vehicle, history, route-path, context,
  stop, and alert endpoints.
- `database_backup.sql` defines the newer `transit` schema, its tables, views,
  and indexes. It is a schema-only dump and contains no table data.
- The repository includes smaller Calgary static GTFS reference files and a
  route-category CSV. The 78.6 MB `stop_times.txt` artifact is intentionally
  excluded because the bootstrap downloads the current GTFS archive directly.
- The current React/PDF.js source builds and lints successfully with Vite;
  production assets use the `/calgary-transit-live/` base path.
- All 17 runtime/script Python files plus the boundary test parse successfully.
- Active first-party Express source passes `node --check`.
- The accepted worker/bootstrap use Psycopg2 Binary 2.9.10; the removed Psycopg
  3 pool and legacy scheduler/HTTP client are no longer declared.

### External data behavior established during development

The historical investigation found that Calgary's feeds are sparse in a
consistent way:

- VehiclePositions reliably supplies vehicle, trip, coordinates, and time but
  often omits route and stop context.
- `trip_id` is the reliable join from live VehiclePositions to static GTFS.
- TripUpdates supplies trip/route identifiers and stop-level predictions.
- Live route references behave like static `route_short_name`, while static
  `routes.route_id` is a different internal key.
- Alerts can be associated with route short names and stops.
- Calgary LRT trips appeared in TripUpdates but not VehiclePositions during the
  recorded investigation, so the Calgary page intentionally does not promise
  live train markers.

These observations are historical evidence from April 2026 and have not been
rechecked against today's external feeds.

## Partially working features

- NiceGUI mounts `frontend/dist` at `/calgary-transit-live`; the deployed React
  entry, PDF.js viewer, display module, worker, and hashed assets return HTTP
  200 at that path.
- NiceGUI navigation now links to `/calgary-transit-live/`.
- The React transit bundle includes matching portfolio navigation and its
  current production bundle has been verified at the public site.
- The production React bundle is built against the public Railway Express API
  at `https://transit-api-production.up.railway.app/api`.
- The Railway Express API health, vehicle-history, and route-path endpoints
  returned HTTP 200 after the production database bootstrap and first poll.
- The standalone poller is deployed as a Railway worker. Its schedule, flags,
  retention, and in-hours freshness have been verified.
- The standalone current-state poller uses `requests` and `psycopg2`; both are
  now declared directly in `requirements.txt`.
- The `transit` schema has ordered, idempotent migrations and a bootstrap
  loader. The migrations, current GTFS load, and live poll have been verified
  locally and the production bootstrap has completed.

## Known broken or incomplete behavior

- Initial Node database-boundary contract tests cover core transit service
  query parameters and response grouping. Five Python boundary tests cover the
  public web mounts, absence of legacy routes, and accepted poller orchestration;
  frontend and HTTP-level API tests are still absent.
- The sole `Procfile` starts only NiceGUI; it does not start the Express API or
  the standalone current-state poller.
- The repository does not yet provide one command that orchestrates the web,
  API, poller, and PostgreSQL locally; component start/check scripts do exist.
- Contact has been rebuilt around FastAPI, SQLAlchemy/Alembic,
  PostgreSQL, Cloudflare Turnstile, signed CSRF state, database throttling,
  one-time email verification, Resend HTTPS delivery, and audit events.
  Production configuration and the first migration are active. The owner
  confirmed receipt and completion of the manual verification email round trip.
  Replay, throttling, and provider-failure drills remain verification debt.
- Google OIDC endpoints, server-managed sessions, registered/admin roles,
  logout, local-account deletion, privacy/terms pages, and a registered-only
  Calgary Project Lab are deployed. Production credentials are active, and the
  owner confirmed real Gmail login and logout. The Account page now clearly
  distinguishes guest and signed-in states and links registered users to their
  unlocked material.
- There is no admin console or first-party analytics model yet.
- Several portfolio pages still contain sample résumé, chart, and image data.
- Superseded commented implementations remain inside some accepted React and
  Express files and are later maintainability cleanup.
- The React production bundle remains tracked temporarily under ADR-009 because
  Railway does not yet run the frontend build. Generated/runtime dependencies
  and bytecode are ignored.
- The phase-1 review found that a fresh local Vite build changes the tracked
  main-bundle hash even without review-time React source edits. The committed
  generated bundle was therefore stale relative to source; deployment should
  eventually build from source or enforce bundle synchronization in CI.
- GTFS alert descriptions currently cross from the external feed into React's
  `dangerouslySetInnerHTML` without sanitization. Treat this as a high-priority
  boundary fix before authenticated features share the origin.
- The accepted transit SQL files reproduce a clean database but do not provide
  a migration ledger or detect schema drift in an existing database.
- Transit health reports freshness-aware healthy/degraded/after-hours state. The
  frontend presents expected after-hours downtime, feed transactions are
  isolated, and City of Calgary attribution is displayed in production.
- Step 5's database foundation and application flow are in production. It uses the
  approved official `google-auth` verifier, authorization-code callback,
  digest-only state/nonce/browser binding, first-login registration, session
  rotation/revocation, session-bound CSRF, role enforcement, bounded cleanup,
  legal pages, account controls, visible locked content, concise dark-safe Codex
  disclosure, and a member-oriented Account page.

## Current development environment

- Host observed during recovery: Linux/Ubuntu-compatible environment.
- System Python: 3.12.3.
- Declared production Python: 3.13.
- Checked-in virtual environment: Python 3.12.
- Node: 24.18.1.
- npm: 11.16.0.
- Frontend package manager: npm with lockfile v3.
- Express package manager: npm with lockfile v3.
- Database represented in active code: PostgreSQL `transit` schema.
- Declared web command: `python -m app.main`.
- Default NiceGUI port: `$PORT` or 8086.
- Default Express port: `$TRANSIT_API_PORT`, then `$PORT`, then 4000.

## External services

- GitHub repository: `sadegh-babapour/portfolio`.
- Railway is the intended hosting platform.
- PostgreSQL is used locally and is intended to be used on Railway.
- Calgary Transit static GTFS and three GTFS-Realtime feeds are external data
  sources.
- OpenStreetMap and CARTO provide map tiles.
- The résumé page now uses a same-origin `/resume/document.pdf` endpoint with a
  full-width responsive desktop/mobile PDF.js canvas viewer and open/download
  fallbacks. Its
  local route, headers, file contents, and desktop/narrow layouts are verified.
  Production now reads the byte-identical ignored PDF from `/data/resume.pdf`
  through `RESUME_PDF_PATH`; inline and download responses return the expected
  disposition headers.
- The PDF.js display layer and worker are bundled into the tracked Vite output
  as a second HTML entry point. Mobile browsers therefore render PDF pages in
  canvas instead of relying on inconsistent native iframe PDF support.
- NiceGUI and React use the same `portfolio-theme` browser-storage key, so a
  light/dark selection follows users between the two frontend shells. Both
  initialize that preference in the document head before visible content to
  avoid a light-page flash, and NiceGUI supplies dark-safe form, table, tab,
  timeline, card, chart, and page surfaces.
- NiceGUI and React portfolio headers share exact desktop/mobile heights,
  padding, spacing, border sizing, and the 1050px mobile-menu breakpoint. The
  theme action cannot shrink out of the React header at intermediate widths.
- All NiceGUI pages now use a consistent wide responsive shell. Contact and
  Projects use desktop grids that collapse to one column; Dashboard charts
  stack on smaller screens and wide tables scroll within their cards; the
  résumé document remains full-width while its timeline uses a readable width.
- NiceGUI ECharts on Projects and Dashboard receive runtime light/dark updates
  for canvas background, titles, legends, axes, grids, and tooltips.
- The user confirmed the production PDF.js résumé works on mobile after the
  native browser embedding approaches failed.

No external service credentials belong in these documents.

## Product direction accepted for planning

- The senior code and architecture review is complete.
- The legacy transit path was removed after dependency and characterization
  evidence confirmed it was unused by the accepted path.
- Make résumé/project content data-driven, then build polished portfolio case
  studies.
- Add a real, verified-email contact flow with layered bot defenses.
- Add Google-based accounts, visible protected content, an admin console, and
  privacy-aware analytics in separate security-focused phases.
- Add cached and live database-backed chart examples after defining a clean
  portfolio data model and ORM boundary.
- Investigate a Toronto subway schematic and Calgary nearby-stop arrivals after
  the existing transit architecture is simplified.

See `docs/ROADMAP.md`. Specific vendors, ORM, schemas, and upstream Toronto
semantics remain decision gates rather than implemented architecture.

## Structured portfolio content

- `content/resume_timeline.json` owns the on-page timeline; it does not affect
  the separately deployed résumé PDF.
- `content/projects.json` owns recruiter-oriented project case studies and
  labels live database work separately from static/sample analysis.
- `app/content.py` validates schema versions, required fields, enumerations,
  unique IDs, and safe project links before either page renders.
- Projects now presents business problems, architecture, sources, pipelines,
  outcomes, limitations, and links instead of placeholder chart canvases.
- Invalid content fails to a controlled unavailable state and is logged rather
  than partially rendering.
- The timeline entries are intentionally marked placeholders until the owner
  supplies factual dates, organizations, roles, and education.
- Source-controlled JSON is runtime read-only. Future admin-managed content and
  service/job monitoring belong in a dedicated ORM-owned PostgreSQL schema.

## Senior review status

The phase-1 technical review in `docs/CODE_REVIEW.md` was approved. Phase 2 is
complete: characterization, source removal, dependency cleanup, local checks,
deployment, and production smoke checks passed.

## Deployment configuration note

- The repository intentionally contains only the Python web `Procfile`; the
  Express API and poller commands are configured per Railway service.

## Confirmed Railway state

- Railway currently has application services named `portfolio`, `transit-api`,
  and `transit-poller`, plus the PostgreSQL service named `postgres`.
- The Express service is public at
  `https://transit-api-production.up.railway.app` and its database-backed
  history and path endpoints have been verified.
- The poller worker completed the production schema/static-data bootstrap and
  one realtime poll.
- The poller is configured for 08:00-21:00 America/Edmonton, a 30-second
  interval, 15-minute raw retention, polling enabled, and kill switch disabled.
- During the 2026-08-04 operating window, the API returned 23 current vehicles,
  22 histories, fresh 20:59 MDT observations, route context, shape points, and
  stops for a selected live vehicle. Its alerts response was healthy but empty.
- At deployed commit `ffdbfb0`, all three application services reported success.
  The portfolio home, résumé, volume-backed PDF, React entry, and new hashed
  bundle returned HTTP 200; `/transit` and `/api/poller/status` returned 404.
  The API returned 30 vehicle histories fresh through 20:33:05 UTC, five
  featured route paths, and HTTP 200 for selected vehicle context, stops, and
  alerts.
- At deployed commit `3e23075`, all three application services again reported
  success. Home, résumé, Projects, volume-backed PDF, React transit, and API
  health returned HTTP 200; production HTML contained the validated timeline
  and both project case studies.
- At deployed commit `1410133`, all three application services reported success.
  Every portfolio route and the React mount returned HTTP 200 with the new wide
  responsive layouts. Contact displayed its configuration notice and its CSRF
  endpoint returned the expected fail-closed HTTP 503 until production database,
  Turnstile, application-secret, and Resend variables are supplied.
- At deployed commit `dffb4b7`, all three application services report success.
  Contact and its configured CSRF endpoint return HTTP 200, the portfolio
  migration runs as a pre-deploy command, and the transit poller continues to
  ingest live Calgary data during 08:00-21:00 America/Edmonton.
- On 2026-08-12 Calgary time, poller logs showed roughly 280-298 vehicle
  positions, 525-571 trip updates, about 10,500-11,000 stop predictions, and 46
  alerts per successful cycle. The browser-facing current endpoint returned 350
  last-known vehicles after hours while four-minute history correctly returned
  none once the 15-minute raw window expired.
- At deployed commit `6644beb`, all three application services reached
  `SUCCESS`. Production health returned `outside_operating_hours` with the
  expected feed timestamps and schedule, the current bundle contained the
  Calgary licence and after-hours copy, and contact CSRF remained configured.
  Direct production calls through both Resend templates succeeded; inbox
  receipt and the interactive browser verification-link round trip await owner
  confirmation.
- At deployed commit `65b33ea`, all three application services reached
  `SUCCESS`. The portfolio pre-deploy log confirmed migration
  `20260805_01 -> 20260813_02`, then NiceGUI started normally. Home remained
  HTTP 200 and the intentionally unimplemented Google login endpoint returned
  HTTP 404.
- At deployed commit `7da2bfa`, all three application services reached
  `SUCCESS`. Production home, Projects, Account, Privacy, Terms, React transit,
  and transit health returned HTTP 200. Projects displayed the locked Calgary
  Project Lab and configuration notice, `/api/auth/session` returned the
  expected unauthenticated response, and Google login failed closed with HTTP
  503 because its client credentials are intentionally not configured yet.
- At deployed commit `0c0c423`, all three application services reached
  `SUCCESS`. Home, Account, Projects, Privacy, Terms, and the React transit page
  returned HTTP 200. Production rendered the exact `Bizqlab` name, homepage
  purpose/data-use copy, canonical URL, guest Account state, and dark-safe
  development-note class. OAuth initiation returned 303 to Google with only
  `openid email profile` and a Secure/HttpOnly browser-binding cookie; a
  cancelled callback returned the expected status, replay failed, and anonymous
  logout/account deletion returned 403. The owner separately confirmed real
  Gmail login and logout.
- The application deploys branch `main` with Railpack and is detected as a
  Python application.
- The observed failed build selected Python 3.13.14, installed
  `requirements.txt`, and selected `python -m app.main` from `Procfile`.
- An older observed failure was caused by Psycopg 3 binary resolution. The
  deployed legacy cleanup removed that dependency.

## Unknown or unverified

- Whether any database credentials in the checkpoint have been exposed or
  rotated.
- Exact production row counts beyond the verified API-visible data.
- Current per-feed field completeness beyond the counts rechecked on 2026-08-12.
- Whether the broader portfolio content is ready for public presentation.
- Google Search Console ownership verification and OAuth brand-review approval;
  these require the owner to publish Google's DNS TXT record and resubmit/reply
  to the review after verification.
