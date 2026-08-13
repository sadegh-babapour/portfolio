# Session Log

## 2026-08-05 — Phase 2 production completion

- Committed the reviewed cleanup as `ffdbfb0` and pushed it to `origin/main`.
- Railway reported successful running deployments of `ffdbfb0` for `portfolio`,
  `transit-api`, and `transit-poller`.
- Production returned HTTP 200 for home, résumé, the volume-backed PDF, React
  entry, regenerated main asset, API health, history, paths, selected vehicle
  context, stops, and alerts.
- The removed `/transit` page and `/api/poller/status` route return HTTP 404.
- The operating-hours history response contained 30 vehicles fresh through
  `2026-08-05T20:33:05Z`; five featured route paths were present. The selected
  vehicle alerts request was healthy and empty.
- Phase 2 is complete. Phase 3 is the structured on-page timeline and portfolio
  case-study content model.

## 2026-08-05 — Phase 2 local legacy removal

### Changed

- Added five standard-library `unittest` boundary checks for public portfolio
  routes, the React mount, résumé defaults, absence of legacy endpoints, poller
  feed orchestration, and boolean flags.
- Removed the hidden NiceGUI transit pages, Python transit/control/debug API,
  web-process poller/updater startup, legacy services/loaders, public-schema SQL,
  and public-schema snapshot script/artifacts.
- Removed direct Psycopg 3/pool, HTTPX, and APScheduler requirements. The
  accepted standalone worker/bootstrap continue using Psycopg2 and Requests.
- Regenerated the tracked Vite output, replacing the stale main bundle hash.
- Added ADR-018 and reconciled architecture, project state, roadmap, actions,
  README, code-review gate, and next-session handoff.

### Verified

- The new boundary suite passed before deletion and all five checks passed after
  deletion.
- Express syntax checks and database-boundary tests passed.
- React lint and production build passed.
- Python compilation and `pip check` passed in `.venv`.
- The NiceGUI application reached its ready state at `localhost:8086`; the smoke
  process was then intentionally terminated by timeout.
- No active-code reference to the deleted legacy modules/endpoints remains.

### Pending

- Review the final diff, commit/push, deploy affected Railway services, and run
  the production smoke matrix before starting phase 3.

## 2026-08-05 — Phase 1 senior code and architecture review

### Completed

- Added `docs/CODE_REVIEW.md` with prioritized findings, strengths, a
  plain-language React walkthrough, legacy dependency/deletion inventory, test
  matrix, target architecture, proposed decisions, and sequenced refactors.
- Reviewed the NiceGUI/FastAPI lifecycle, legacy services, Express API,
  standalone poller, React/Leaflet frontend, PostgreSQL migrations/views,
  bootstrap, dependencies, security/privacy, accessibility, tests, and
  deployment boundaries.
- Confirmed `main`, `origin/main`, and the reviewed baseline are `f6f661e`.

### Principal findings

- No critical issue or committed secret was found.
- Unsanitized external alert text rendered as HTML, public legacy mutation/work
  endpoints, and the lack of durable forward migrations are high priority.
- The accepted React architecture is suitable for incremental extraction and
  testing; a framework rewrite is not recommended.
- A fresh Vite build changed the tracked main-bundle hash, proving generated
  output had drifted from source.

### Verification

- Express syntax checks and database-boundary tests passed.
- React lint and production build passed.
- Python compilation passed with `python3`; the `python` alias is absent.
- Offline production npm audits reported zero known vulnerabilities for both
  Node applications, limited to locally cached advisory data.
- Documentation whitespace validation passed before the final continuity edit.

### Gate

- Phase 1 technical work is complete. Phase 2 waits for owner approval of the
  six proposed decisions and begins with characterization tests.

## 2026-08-05 — Deferred rail-feed candidate and progress reporting

- Recorded `https://bustime.ttc.ca/gtfsrt/vehicles?debug` as a candidate endpoint
  for the future rail visualization without evaluating it now.
- Deferred city/feed research until phase 8 and broadened the later comparison
  to established international realtime rail feeds; Toronto is no longer a
  required final choice.
- Added two-level progress reporting for future work: overall roadmap step and
  mini-step within the active phase.

## 2026-08-05 — Roadmap decisions clarified

- Clarified that structured résumé content means the on-page timeline, not the
  volume-backed PDF.
- Accepted a separate ORM-owned schema inside the existing PostgreSQL database.
- Selected Cloudflare Turnstile free plan for the public contact form while
  retaining server validation, throttling, honeypot, CSRF, replay protection,
  and sender-email verification.
- Deferred GA4 in favor of first-party operational/audit events first.
- Relaxed the Toronto requirement from GPS-grade positions to useful,
  transparently labeled station or between-station estimates; the
  owner-supplied feed will be evaluated first.

## 2026-08-05 — Product roadmap and review-first architecture plan

### Goal

Capture the next product direction and sequence it safely before starting a
large refactor or adding identity, messaging, analytics, data, and transit
features.

### Changed

- Added `docs/ROADMAP.md` with nine gated phases: senior review, legacy removal,
  structured case-study content, verified contact delivery, authentication,
  admin/analytics, data/chart platform, Toronto subway, and Calgary nearby-stop
  arrivals.
- Replaced stale next actions and session handoff instructions with the phase-1
  review scope.
- Reconciled project state and architecture with deployed commit `f6f661e`, the
  working PDF.js mobile viewer, verified Railway services, and current product
  gaps.
- Added ADR-016 requiring an evidence-backed review and characterization tests
  before legacy deletion or major platform choices.

### Planning conclusions

- Ordinary contact should not require Google login. Unauthenticated visitors
  can verify the submitted email through an expiring link; authenticated users
  can reuse their verified identity.
- Bot defense must be layered. Cloudflare Turnstile is a managed free-plan
  option; ALTCHA matches the requested self-hosted proof-of-work idea. The
  review will decide after operational/security analysis.
- A future ORM should own new portfolio-domain entities, not automatically
  replace the explicit Express transit SQL and PostgreSQL views.
- Public pages should remain valuable while selected deeper case-study content
  is visibly locked behind Google OIDC.
- First-party admin/audit data and GA4 serve different purposes; privacy and
  consent requirements must be reviewed before enabling GA4.
- Toronto subway visualization requires an official-feed capability spike. If
  only trip/stop predictions exist, the UI must label station/between-station
  progress as estimated rather than imply GPS positions.
- Calgary location must be opt-in with a manual-pin fallback and no default
  retention of precise coordinates.

### Verified

- Local `main`, `origin/main`, and the successful production baseline point to
  `f6f661e`; the working tree was clean before this documentation update.
- Current source has no implemented ORM, authentication, CAPTCHA, outbound
  contact delivery, protected-page policy, admin console, or GA4 integration.
- Official current documentation confirms Cloudflare Turnstile has a free plan
  and requires server-side token verification; ALTCHA provides a self-hosted
  proof-of-work option.

### Next

- Perform phase 1 and deliver `docs/CODE_REVIEW.md`; do not begin phase 2 until
  the findings and target architecture are approved.

## 2026-08-04 — PDF.js résumé and theme-aware charts

### Goal

Replace the mobile browser's non-rendering native PDF placeholder and make
Projects/Dashboard ECharts genuinely responsive to light/dark mode.

### Changed

- Added the user-approved `pdfjs-dist` 6.1.200 frontend dependency and lockfile
  entries.
- Added a locally bundled, portfolio-styled PDF.js viewer with fit-width page
  rendering, zoom controls, resize rerendering, status/error UI, and shared
  light/dark preference.
- Changed Vite to emit the transit application and PDF viewer as separate HTML
  entry points in one production bundle.
- Pointed the NiceGUI résumé iframe at the same-origin PDF.js viewer while
  preserving full-screen and download controls.
- Replaced white EChart canvases with runtime theme updates for chart text,
  axes, legends, grid lines, tooltips, polar axes, and backgrounds.

### Verified

- React lint and the multi-entry production build pass with the public transit
  API URL.
- PDF.js parses the actual ignored résumé as a two-page document.
- Local production-preview requests returned the viewer HTML, 2.2 MB worker,
  and viewer module successfully.
- The production dependency audit reports zero known vulnerabilities.
- Python compilation, NiceGUI component imports, and `git diff --check` pass.

### Next

- Commit, push, deploy, then verify the production viewer HTML/assets and test
  actual canvas rendering on the user's mobile browser.

## 2026-08-04 — Navbar parity and complete dark-mode pass

### Goal

Correct the deployed navbar mismatch, restore the missing transit theme action
at intermediate widths, eliminate light-theme flashes between pages, and make
all NiceGUI page content readable in dark mode.

### Changed

- Standardized both headers on border-box sizing, 64px desktop and 56px mobile
  heights, matching padding/gaps, and a 1050px responsive breakpoint.
- Reserved non-shrinking header space for the theme action so it cannot be
  pushed outside the React viewport.
- Added synchronous document-head theme initialization to NiceGUI and React,
  applying the saved preference before visible content renders.
- Added shared NiceGUI dark styles for pages, cards, contact fields, tabs,
  tables, timelines, separators, muted text, PDF controls, and chart surfaces.
- Added dark-state React controls and Leaflet zoom styling and regenerated the
  tracked production bundle with the public transit API URL.

### Verified

- Python compilation and changed NiceGUI component imports pass from the
  project virtual environment.
- React lint and production build pass.
- `git diff --check` passes.

### Next

- Commit and push the correction, verify all Railway services reach success, then
  visually confirm the corrected headers and themes in desktop/mobile browsers.

## 2026-08-04 — Sticky navigation, shared themes, and mobile résumé

### Goal

Keep both portfolio headers visible while scrolling, improve embedded résumé
behavior on mobile browsers, and add matching light/dark controls to NiceGUI
and React.

### Changed

- Made the NiceGUI and React portfolio headers sticky at the viewport top.
- Added accessible light/dark buttons to both headers, using one persistent
  `portfolio-theme` browser-storage preference and system preference fallback.
- Added dark surface/text/border styling to both shells without adding a
  dependency.
- Replaced the résumé `<object>` embed and its visible unsupported-browser
  fallback with a responsive same-origin `<iframe>` while retaining explicit
  full-screen and download controls.
- Regenerated the tracked React production bundle with the production Express
  API URL.

### Verified

- All first-party Python files compile and the changed NiceGUI components
  import in the project virtual environment.
- React lint and production build pass.
- The generated bundle contains the production Railway transit API base URL.
- `git diff --check` passes.

### Unresolved

- The new controls and mobile iframe still need real-device production testing
  after commit, push, and deployment.

### Next

- Commit, push, deploy, and test sticky scrolling, cross-shell theme
  persistence, and the résumé on the user's mobile browser.

## 2026-08-04 — Production résumé and live transit verification

### Goal

Deploy the committed navigation/résumé work, place the private résumé on the
portfolio volume, and verify production transit behavior during Calgary
operating hours.

### Changed

- Uploaded the ignored local `static/resume.pdf` to the `portfolio` Railway
  volume at `/data/resume.pdf`.
- Set `RESUME_PDF_PATH=/data/resume.pdf`, triggering a successful `portfolio`
  redeployment of `7cbf6a1`.
- Updated continuity documents with the observed production state.

### Verified

- Local `HEAD`, `origin/main`, and the successful Railway deployments for
  `portfolio`, `transit-api`, and `transit-poller` all use `7cbf6a1`; the local
  tree was clean before this documentation update.
- Railway identifies `portfolio-volume` as ready and mounted at `/data` on the
  `portfolio` service.
- `/resume`, the inline PDF route, and the download route return HTTP 200. The
  two production PDF responses match the local file's SHA-256 hash and use the
  expected content dispositions.
- Poller variables specify 08:00-21:00 America/Edmonton, a 30-second interval,
  15-minute raw retention, `POLL_ENABLED=true`, and
  `ADMIN_KILL_SWITCH=false`.
- At 20:59 MDT, the API returned 23 current vehicles, 22 histories, five route
  path groups, and fresh observations. Vehicle `8303` returned route context,
  511 shape points, previous/next stops, and eight stops.
- The selected vehicle's alerts endpoint returned HTTP 200 with an empty list.

### Unresolved

- Desktop/mobile visual interaction and browser-console checks still require a
  real browser session.
- No active vehicle alert was available to verify alert rendering.

### Next

- Complete the visual browser checklist on desktop and mobile, and verify an
  active alert when Calgary's feed provides one.

## 2026-08-03 — NiceGUI shell and résumé closeout

### Goal

Align the NiceGUI pages with the deployed React navigation, correct the résumé
holder width on desktop/mobile, and leave complete storage/session continuity.

### Changed

- Rebuilt the NiceGUI header to match the React header's link order, desktop
  layout, mobile dropdown, color, spacing, and active-page state.
- Made the résumé page and embedded PDF holder explicitly full-width and kept
  the holder visible at a useful viewport-relative height on mobile.
- Made relative `RESUME_PDF_PATH` values resolve from the repository root.
- Preserved `static/resume.pdf` locally while removing it from Git tracking and
  adding it to `.gitignore`.
- Added `docs/FILE_STORAGE.md` with the Railway `portfolio` volume upload,
  configuration, replacement, and verification procedure.
- Added `docs/NEXT_SESSION_PROMPT.md` as a ready-to-paste continuation prompt.
- Updated project state, architecture, decisions, next actions, and README.

### Verified

- First-party Python files compile with the host's `python3`.
- Frontend lint/build pass; incidental regenerated build output was restored
  because no React source changed in this task.
- Express syntax and contract tests pass.
- `git diff --check` passes, and the local résumé remains present while Git
  reports it ignored and removed from tracking.
- Created a clean ignored `.venv`, installed `requirements.txt`, and confirmed
  `pip check` reports no broken requirements.
- Started the real NiceGUI app locally on port 8091. Home, about, résumé,
  projects, contact, dashboard, and the mounted React transit route all returned
  HTTP 200.
- Verified the inline PDF response is byte-identical to `static/resume.pdf` and
  the download mode returns an attachment response.
- Captured and inspected 1440px desktop and 500px narrow screenshots. The
  matching desktop/mobile navbar and full-width résumé holder render as
  intended.
- Local runtime testing caught and fixed an unsupported `sanitize` argument in
  the first navbar implementation before publication.

### Unresolved

- The résumé file still needs to be uploaded to the running `portfolio` volume
  and `RESUME_PDF_PATH=/data/resume.pdf` configured in Railway.
- The NiceGUI changes still need deployment and desktop/mobile visual smoke
  testing.
- Transit markers and selection need verification while the poller is active.

### Next

- Publish/deploy these changes, upload the résumé, visually test the résumé and
  navigation, then verify live transit freshness and selection.

### End-of-session summary

- The recovered transit frontend/API baseline remains deployed at `f58763f`.
- Today's NiceGUI navigation, résumé delivery/layout, ignored runtime-file
  policy, Railway volume instructions, and continuity documentation are ready
  for one local commit.
- Local verification is complete: clean dependency installation, all portfolio
  routes returning HTTP 200, exact inline/download PDF behavior, inspected
  desktop and narrow screenshots, frontend lint/build, Express checks/tests,
  Python compilation, and clean diff formatting.
- No production push, Railway variable change, volume upload, or deployment was
  performed in this session.

## 2026-08-03 — Railway-volume résumé delivery

### Goal

Replace the external sample PDF dependency with a responsive, same-origin
résumé delivery path backed by Railway storage.

### Changed

- Added `/resume/document.pdf` with inline and download response modes.
- Added `RESUME_PDF_PATH`, defaulting locally to `static/resume.pdf`.
- Replaced the external PDF.js iframe with a responsive native desktop embed.
- Added full-screen and download fallbacks optimized for mobile browsers.

### Verified

- First-party Python files compile successfully.
- `git diff --check` passes.

### Unresolved

- The actual résumé must be uploaded to `/data/resume.pdf` on the attached
  `portfolio` volume and configured through `RESUME_PDF_PATH`.
- Runtime import testing was unavailable because system Python does not have
  the declared FastAPI dependencies installed.
- The fictional timeline entries still require confirmed résumé facts.

### Next

- Upload and configure the actual PDF, deploy the route, and verify inline and
  download behavior on desktop and mobile.

## 2026-08-03 — Railway transit API and database bootstrap

### Goal

Deploy the newer transit API and initialize its production database contract.

### Changed

- Configured a Railway Express service with a public domain.
- Bootstrapped the Railway `transit` schema and static GTFS data through the
  poller worker's one-time pre-deploy command.
- Ran one realtime ingestion pass.
- Rebuilt the tracked React bundle with the public Express `/api` URL.
- Removed the 78.6 MB tracked `data/stop_times.txt` artifact and ignored local
  copies because bootstrap downloads current GTFS directly.

### Verified

- Production `/api/health` returns HTTP 200.
- Production vehicle history returns HTTP 200 with current vehicle records.
- Production featured route paths return HTTP 200 with route geometry.
- Frontend lint and the production Vite build pass.
- The built JavaScript contains the intended production API base URL.
- Express syntax checks and database-boundary tests pass.
- First-party Python sources compile successfully with `python3`.

### Unresolved

- Verify ongoing poller hours, flags, retention, and next in-hours refresh.
- Push and verify the rebuilt transit page on the portfolio domain.

### Next

- Finish poller configuration verification, then deploy and smoke-test the web
  bundle.

## 2026-08-03 — Transit portfolio navigation

### Goal

Restore portfolio navigation on the standalone React Calgary Transit page.

### Changed

- Added a React portfolio header matching the NiceGUI route set.
- Added a desktop link row and an accessible, responsive mobile menu.
- Regenerated the tracked recovery bundle in `frontend/dist`.
- Updated project state, the transit mount decision, and next actions.

### Verified

- Frontend ESLint passes.
- The Vite production build succeeds with `/calgary-transit-live/` assets.

### Unresolved

- The updated bundle has not yet been pushed or verified on Railway.
- Production still lacks the Express transit API and standalone poller worker.

### Next

- Configure the Express transit API as a second Railway service and wire its
  public `/api` URL into the web build.

## 2026-08-02 — Read-only repository recovery audit

### Goal

Recover an evidence-based understanding of a partially completed repository
without modifying files or contacting its configured services.

### Inspected

- Repository layout and tracked artifact counts.
- Git status, recent history, transition commits, and entry points.
- Python, React, Express, SQL, environment examples, dependency manifests, and
  deployment files.
- NiceGUI pages, React request flow, Express queries, both database models, and
  GTFS-related services.
- Documentation, TODO/commented code, test discovery, and generated artifacts.

### Changed

- No files changed.

### Verified

- Local `main` was clean and one checkpoint commit ahead of `origin/main`.
- 24 of 24 first-party Python files parsed.
- Active first-party Express files passed `node --check`.
- The React frontend built successfully to a temporary directory and matched
  checked-in production hashes.
- Frontend lint failed with three errors and one warning.
- No first-party tests were discovered.
- Importing the NiceGUI application and pages registered the expected routes;
  `/map` was absent and `/calgary-transit-live` was mounted.

### Decisions

- None made. The audit separated current implementation from inferred intent.

### Unresolved

- Production and database state.
- Authoritative transit architecture and schema.
- Safe treatment of the local checkpoint's credentials and generated files.

### Next

- Read the historical development conversation and reconcile its intent with
  current code before planning changes.

## 2026-08-03 — History reconciliation and project memory

### Goal

Read the complete transit-development history, compare it with the repository
and public GitHub branch, and create durable project memory.

### Inspected

- All 5,804 lines of `docs/CHAT_HISTORY_RAW.md`.
- All recommendations in `docs/last_suggestions.md`.
- Local `HEAD`, `origin/main`, public GitHub branch metadata, and remote head.
- Claims about feed behavior, database evolution, frontend work, environment
  separation, NiceGUI integration, and the proposed Railway deployment.

### Changed

- Added root `AGENTS.md`.
- Added `PROJECT_STATE.md`, `ARCHITECTURE.md`, `DECISIONS.md`,
  `NEXT_ACTIONS.md`, and this session log under `docs/`.
- No application, dependency, environment, SQL, data, or deployment files were
  changed.

### Verified

- Public GitHub `main` and local `origin/main` both point to `447ecbf`.
- Local `HEAD` is the unpushed checkpoint `eeb44cf`.
- GitHub exposes no project homepage, and no real Railway public URL is present
  in repository history.
- The user chose to record production behavior as unverified.

### Decisions

- Recorded previously accepted technical directions as ADRs while marking
  unimplemented or unverified consequences explicitly.
- Kept the repository as implementation truth and the transcript as evidence
  of intent.
- Deferred README startup/deployment instructions until they can be verified
  from a clean environment.

### Unresolved

- Railway production URL and service state.
- Database reachability, contents, and credential exposure.
- Reproducible bootstrap and startup for the newer transit stack.

### Next

- Secure the local checkpoint before it is pushed, keeping cleanup separate
  from application recovery.

## 2026-08-03 — Railway dependency compatibility

### Goal

Resolve the reported Railway build issue around Psycopg on Python 3.13.

### Inspected

- `requirements.txt`, `runtime.txt`, the Railway `Procfile`, and the Python
  application entry point.
- Official package metadata for Psycopg, Psycopg Binary, Psycopg Pool, and
  Psycopg2 Binary.

### Changed

- Updated `psycopg[binary,pool]` from 3.2.2 to 3.3.4.

### Verified

- The complete requirements set resolves and downloads as Linux CPython 3.13
  wheels.
- The resolved Psycopg packages are `psycopg==3.3.4`,
  `psycopg-binary==3.3.4`, and `psycopg-pool==3.3.1`.
- A clean Python 3.12 environment installs successfully, passes `pip check`,
  imports both Psycopg generations, and imports `app.main`.

### Unresolved

- The exact Railway build log and a successful Railway redeploy have not been
  observed.
- A true Python 3.13 application startup was not available locally; its wheel
  resolution was verified explicitly instead.

### Next

- Redeploy on Railway and capture the first failing log section if the build
  still fails.

## 2026-08-03 — Local transit integration recovery

### Goal

Verify the newer transit stack end to end before defining Railway services.

### Inspected

- Database bootstrap, current-state poller, Express queries, React production
  build, NiceGUI static mount, and current Railway configuration guidance.

### Changed

- Fixed empty-alert responses by requiring a matching active alert.
- Added database-boundary Express contract tests.
- Regenerated `frontend/dist` with subpath-safe assets.
- Removed the incompatible legacy transit page from portfolio navigation while
  retaining its route and implementation.
- Replaced the placeholder README with verified installation, bootstrap,
  startup, checks, and Railway target documentation.
- Kept the regenerated React bundle tracked temporarily because the current
  Railway web build phase is unverified (ADR-009).

### Verified

- Loaded current Calgary static GTFS: 150 routes, 29,034 trips, 5,887 stops,
  198,098 shape points, and 912,156 stop times.
- A live poll ingested 211 vehicles, 343 trip updates, 6,820 stop predictions,
  47 alerts, and 113 informed entities.
- Express health, vehicles, history, paths, context, stops, and alerts returned
  successful responses against the isolated database.
- NiceGUI served the React document and hashed JavaScript asset from
  `/calgary-transit-live/` with HTTP 200 responses.
- Frontend lint/build, Express syntax checks, and five service contract checks
  passed.

### Unresolved

- Railway's actual services, variables, custom configuration paths, build
  commands, logs, and public domains remain unavailable locally.
- The older public-schema implementation remains in code and should not be
  deleted until the newer production path is confirmed.

### Next

- Reconcile the verified commands with the actual Railway services and deploy
  web, API, and worker independently.

## 2026-08-03 — Railway build-log reconciliation

### Goal

Compare the failed Railway deployment with the locally verified dependency
set and deployment assumptions.

### Inspected

- User-provided Railway service summary and failed Railpack build output.

### Changed

- Ignored `docs/temp_doc/` because temporary notes may contain personal or
  deployment details that must not be committed.
- Updated project memory with non-secret Railway facts.

### Verified

- Railway currently deploys one NiceGUI application and one PostgreSQL
  service from `main`.
- Railpack detected Python 3.13.14 and the `Procfile` command correctly.
- The failed revision requested Psycopg 3.2.1, while the recovery tree uses the
  verified Python 3.13-compatible Psycopg 3.3.4 dependency.

### Unresolved

- The recovery changes have not yet been committed or pushed, so Railway has
  not built them.
- The app's public URL and remaining service settings are still unknown.

### Next

- Review and publish the recovery commit, then inspect the resulting Railway
  build before adding API and worker services.

## 2026-08-05 — Structured portfolio content

### Goal

Make the on-page timeline and project portfolio data-driven while establishing
the persistence boundary needed by later admin and monitoring work.

### Changed

- Added validated JSON contracts for timeline entries and project case studies.
- Rebuilt Résumé and Projects rendering around the validated content loader.
- Replaced placeholder project charts with honest, expandable case-study
  sections and documented the editing workflow.
- Established source JSON as runtime read-only and reserved a future ORM-owned
  PostgreSQL schema for admin-managed content and operational records.

### Verified

- Eight Python boundary/content tests, Python compilation, and local HTTP smoke
  checks for `/resume` and `/projects` passed.
- Express syntax/tests, React lint/build, and diff validation passed.
- All three Railway application services reached `SUCCESS` at `3e23075`.
  Production home, résumé, Projects, PDF, React transit, and API health returned
  HTTP 200, and the new content appeared in the rendered page payloads.

### Unresolved

- The repository owner still needs to replace the marked timeline placeholders
  with factual career history.
- ORM selection and the admin monitoring implementation remain later phases.

### Next

- Start the contact security and delivery design.

## 2026-08-05 — Secure contact implementation

### Goal

Replace the presentation-only form with a durable, verified sender workflow and
layered abuse controls.

### Changed

- Added SQLAlchemy/Alembic ownership of contact records, keyed abuse attempts,
  and audit events in a dedicated `portfolio` schema.
- Added origin/CSRF validation, bounded inputs, honeypot handling, transactional
  rate limits, Turnstile Siteverify checks, one-time verification links, and
  authenticated SMTP delivery with a verified `Reply-To`.
- Rebuilt Contact with clearer expectations, topic selection, privacy copy,
  mobile spacing, accessible status feedback, and fail-closed configuration.
- Standardized all NiceGUI pages on a wide responsive container, converted the
  Dashboard chart layout to a mobile-first grid, constrained table overflow,
  widened the timeline, and replaced sparse Home/About shells with responsive
  portfolio-oriented sections.
- Added explicit light-theme contact-field borders plus hover and keyboard-focus
  states while retaining the approved dark-theme field surfaces.
- Added setup and threat-model documentation without recording secrets.

### Verified

- Twenty Python tests and Python compilation passed.
- Contact returned HTTP 200 locally and its unconfigured API returned the
  expected HTTP 503 instead of claiming delivery.
- Home, About, Résumé, Projects, Contact, Dashboard, and the React mount all
  returned HTTP 200 after the responsive page audit.
- All three Railway application services reached `SUCCESS` at `1410133`; the
  same seven production routes returned HTTP 200 and the unconfigured contact
  CSRF endpoint returned the expected fail-closed HTTP 503.
- Alembic offline SQL generation passed. Upgrade/downgrade/upgrade created the
  expected four `portfolio` tables in a disposable PostgreSQL container.

### Unresolved

- PostgreSQL 18 image download was blocked by the container registry network,
  so the disposable migration lifecycle used the locally available PostgreSQL
  13 image. Railway's PostgreSQL 18 remains the production verification target.
- Production Turnstile, generated application secrets, SMTP values, migration,
  deployment, and email round-trip remain pending owner configuration.

### Next

- Follow `docs/CONTACT_SETUP.md`, apply the migration, deploy, and verify one-
  time delivery plus abuse/error paths.

## 2026-08-05 — Contact delivery adapted for Railway Hobby

### Goal

Replace the production-blocked SMTP transport with an HTTPS transactional-email
transport while retaining the verified-sender workflow.

### Changed

- Replaced direct SMTP delivery with Resend's HTTPS email API using the existing
  `requests` dependency.
- Replaced SMTP configuration requirements with `RESEND_API_KEY`; retained the
  verified `Reply-To` behavior and Zoho as the receiving/reply mailbox.
- Updated contact tests, example environment values, setup guidance, current
  state, architecture, decisions, security notes, and next actions.

### Unresolved

- The owner must verify a sending domain in Resend, add a sending-only API key
  to the Railway `portfolio` service, deploy, and complete the email round trip.
- Railway's `alembic upgrade head` pre-deploy command should remain configured
  for future portfolio-schema migrations.

## 2026-08-13 — Step 4 contact and transit health closeout

### Goal

Correct the duplicate-looking Turnstile experience, establish truthful transit
freshness health, preserve successful feeds during partial Calgary failures, and
meet the Calgary open-data attribution requirement.

### Changed

- Deferred Turnstile execution until a valid Send attempt and submit only from
  its success callback; mandatory server-side Siteverify validation remains.
- Added a freshness-aware Express health contract and React healthy, degraded,
  unavailable, and expected after-hours states.
- Isolated VehiclePositions, TripUpdates, and Alerts transactions so one failed
  feed no longer rolls back successful sibling feeds.
- Added the required City of Calgary open-data licence attribution to every map
  basemap and regenerated the tracked production bundle.
- Added initial health-contract and partial-feed-failure tests and ADR-021.

### Verified

- All 22 Python tests passed.
- Active Express source passed `node --check`; the Node test command passed.
- Frontend lint and the production Vite build passed.
- Before these local changes, Railway showed all services running `dffb4b7`;
  production contact/CSRF returned HTTP 200 and live poller logs confirmed
  current Calgary ingestion during configured hours.

### Pending

- Review, commit, deploy, and run the real Resend verification/final-delivery
  matrix plus in-hours and after-hours health smoke checks.

## 2026-08-13 — Step 4 production release and Step 5 foundation

### Step 4 production verification

- Committed and pushed `6644beb`; `portfolio`, `transit-api`, and
  `transit-poller` each reached Railway `SUCCESS` on that commit.
- Production freshness health correctly reported `outside_operating_hours`,
  recent count zero, the configured schedule, and last feed timestamps.
- Verified the deployed bundle contains Calgary attribution, after-hours copy,
  and health integration. Contact CSRF returned its configured sitekey/token.
- Sent clearly labeled verification-template and owner-delivery-template tests
  through the production Resend configuration. Both API calls succeeded; owner
  inbox receipt and a real interactive form/link round trip remain manual.

### Step 5 started

- Added `docs/AUTH_SECURITY.md` covering Google authorization-code OIDC,
  state/nonce/browser binding, server sessions, CSRF, roles, privacy, retention,
  exact callback configuration, and remaining gates.
- Added fail-closed auth configuration and high-entropy token digest plus safe
  return-path helpers without adding a dependency.
- Added ORM models and a linear Alembic migration for users, external
  identities, roles, sessions, login states, and bounded auth events. No Google
  tokens or raw IP addresses are modeled.
- Added tests for configuration, allowlists, tokens, redirects, schema
  isolation, and digest-only persistence.

### Verified

- All 29 Python tests passed after the auth foundation.
- Python compilation passed, Alembic reports one linear head at `20260813_02`,
  and `git diff --check` passed.

### Gates

- Owner approval is required before adding `google-auth` to production.
- Google OAuth web-client credentials and the registered-only content choice are
  required before implementing and exposing the login flow.

### Production foundation verification

- Committed and pushed `65b33ea`; all three Railway services reached
  `SUCCESS`.
- The portfolio pre-deploy log explicitly recorded the upgrade from
  `20260805_01` to `20260813_02`; NiceGUI then reached ready state.
- Production home returned HTTP 200, freshness health retained its expected
  after-hours contract, and `/api/auth/google/login` returned HTTP 404 because
  no unfinished login endpoint is exposed.
- A local `railway run alembic current` could not resolve the private Railway
  database from outside its service network. The successful in-network
  pre-deploy migration log is the authoritative verification.

## 2026-08-13 — Step 5 Google identity implementation

### Changed

- Added the owner-approved official `google-auth` verifier and implemented the
  Google authorization-code login start/callback with state, nonce, browser
  binding, verified-email, issuer/audience/signature/time validation, and
  root-relative return paths.
- Added first-login registration, registered/admin role assignment, opaque
  digest-only server sessions, rotation, revocation, session-bound CSRF,
  logout, local-account deletion, and bounded expired-record cleanup.
- Added public Privacy, Terms, and Account pages. Public projects remain useful;
  Calgary now advertises a registered-only Project Lab containing technique,
  implementation, trade-off, and candid AI-assisted working-method notes.
- Kept authentication fail-closed until Google credentials are supplied and
  synchronized the Account navigation link into the tracked React bundle.

### Verified locally

- All 32 Python tests, Python compilation, dependency consistency, one-head
  Alembic/offline SQL, frontend lint/build, and `git diff --check` passed.
- Local HTTP smoke checks returned 200 for home, Projects, Account, Privacy, and
  Terms. The login endpoint returned the intended 503 without credentials, and
  Projects displayed the locked Project Lab configuration state.

### Remaining

- Configure the Google production web client and Railway credentials, then
  exercise the complete real-browser identity matrix.

### Production verification

- Committed and pushed `7da2bfa`; Railway reported `SUCCESS` for portfolio,
  transit API, and transit poller on that revision.
- Production home, Projects, Account, Privacy, Terms, React transit, and transit
  health returned HTTP 200. The session endpoint correctly reported an
  unauthenticated visitor, and Projects showed the locked Project Lab without
  exposing its registered-only technique content.
- Google login returned the intended HTTP 503 because the production client ID
  and secret are not configured. Runtime logs confirmed normal NiceGUI startup
  and named only the two missing variable names, without secret values.
- Railway's agent-tooling health check reported an apparent skill revision
  update; `railway skills update` then confirmed installed skills were already
  current.
