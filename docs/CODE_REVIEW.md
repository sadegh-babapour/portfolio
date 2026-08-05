# Senior Code and Architecture Review

Reviewed: 2026-08-05

Baseline: `f6f661e` (`main` and `origin/main`)

Scope: NiceGUI/FastAPI, Express, Python poller, React/Leaflet, PostgreSQL,
bootstrap/migrations, tests, dependencies, security, privacy, and deployment

## Executive assessment

The deployed Calgary path is a credible working vertical slice:

```text
Calgary feeds -> Python worker -> PostgreSQL transit schema -> Express -> React
                                                                    |
                                          NiceGUI serves the built application
```

It should be improved incrementally, not replaced. The strongest parts are the
clear runtime separation, parameterized SQL, PostgreSQL enrichment views,
same-origin PDF delivery, idempotent realtime upserts, and a React implementation
that models delayed playback from observations rather than inventing positions.

The repository is nevertheless carrying two transit generations. The NiceGUI
web process still starts and exposes the older public-schema implementation even
though users navigate to the React implementation. That duplication is the main
architectural problem and should be removed in phase 2 after characterization
tests protect the accepted production path.

No critical finding or committed secret was found. Three high-priority issues
should be addressed before adding authentication or protected content:

1. external GTFS alert text is inserted into the DOM as trusted HTML;
2. public legacy endpoints can mutate the legacy poller and trigger work;
3. the SQL bootstrap is not a durable migration system and cannot detect or
   repair schema drift in an existing database.

The codebase is currently closer to a well-functioning prototype than a mature
production platform. That is a good starting point for a portfolio: the next
work should demonstrate the engineering transition through tests, boundaries,
observability, security controls, and documented decisions.

## What is already done well

- The browser does not connect directly to PostgreSQL.
- The accepted API uses placeholders for user-controlled SQL values.
- The worker stores source timestamps and SHA-256 feed fingerprints.
- Current and short-history transit data have distinct table purposes.
- Static GTFS, route metadata, and realtime entities are enriched in PostgreSQL
  rather than repeatedly joined in the browser.
- Polling hours use `America/Edmonton`, avoiding server-local-time assumptions.
- The React effect intervals have cleanup functions and selection is reconciled
  against refreshed playback vehicles.
- The selected route, prior/next stops, stale state, and delayed playback make
  data provenance more visible than a decorative map would.
- Theme preference is shared across NiceGUI and React without a white flash.
- The PDF remains same-origin and is rendered client-side with locally bundled
  PDF.js rather than sent to an external viewer.
- Lockfiles exist for both JavaScript applications. Current offline production
  audits report no known vulnerabilities.
- The ignored-file policy covers credentials, environments, dependencies,
  generated Python state, and the private résumé PDF.

## Prioritized findings

### Critical

No critical issue was confirmed from the repository review.

### High

#### H1 — External alert content crosses an unsafe HTML boundary

Evidence:

- `frontend/src/App.jsx:402-405` uses `dangerouslySetInnerHTML` for
  `description_html`.
- `backend/transit_api/services/transitService.js:385-397` returns that database
  field unchanged.
- `poller/poll_calgary_gtfs_rt_current.py:342-343` obtains it from an external
  GTFS-Realtime translation even though it is named `description_html` locally.
- The unused `frontend/src/DashboardPage.jsx:117-120` repeats the behavior.

Impact: a compromised or malformed upstream feed could execute markup/script in
the portfolio origin. The impact grows substantially once authenticated sessions
and admin pages share that origin.

Recommendation: treat GTFS translation values as plain text by default. If a
real requirement for limited markup is established, sanitize against a small
server-side allowlist and test hostile payloads. Complete this before phase 5.

#### H2 — The public web process exposes legacy control and work endpoints

Evidence:

- `app/main.py:98-102` starts the public-schema poller and weekly GTFS updater in
  every NiceGUI process.
- `app/main.py:173-177` exposes unauthenticated daily resampling.
- `app/main.py:264-273` exposes unauthenticated pause/resume mutations.
- `app/main.py:277-304` exposes an unauthenticated upstream-feed debug request.
- `app/main.py:87-95` imports and registers the hidden `/transit` page.

Impact: third parties can alter legacy runtime state or cause unnecessary
database/upstream activity. Scaling the web service would also create one legacy
poller per replica. These endpoints are unrelated to the accepted React worker.

Recommendation: phase 2 should remove the legacy startup tasks, Python transit
API, hidden page, and controls as one characterized boundary. Until removal, do
not scale the NiceGUI service beyond one replica and do not build new features on
these endpoints.

#### H3 — Database bootstrap files are not durable migrations

Evidence:

- `scripts/db/002_create_transit_tables.sql` relies on `CREATE TABLE IF NOT
  EXISTS`.
- There is no migration ledger, version table, checksum, or ordered upgrade
  history beyond a hard-coded filename tuple in
  `scripts/bootstrap_transit_db.py:21-26`.
- Existing tables are not altered when a definition changes.
- Several schema objects represented in the migrations are currently unused by
  the worker, making drift harder to detect.

Impact: a clean database can be reproduced, but an existing production database
can silently differ from source. Future portfolio/auth tables would make this
unsafe and difficult to audit.

Recommendation: retain the present files as the clean transit baseline, then
adopt a real forward-only migration ledger. Evaluate Alembic with SQLAlchemy in
phase 3 for the ORM-owned portfolio schema; explicit SQL migrations can continue
to own the transit schema.

### Medium

#### M1 — API query values are not validated or bounded

`backend/transit_api/server.js:130-139`, `214-224`, and `354-365` accept arbitrary
mode, route lists, density, and numeric history windows. `Number(...)` can produce
`NaN`, negative values, or excessive ranges. Unknown modes silently become
`all`. Add explicit enums, route-count/length limits, a bounded integer window,
and consistent 400 responses.

#### M2 — API operational boundaries are incomplete

`backend/transit_api/server.js` listens at import time, has unrestricted CORS,
logs raw errors to the console, lacks request IDs and structured logging, and
does not close the HTTP server/PostgreSQL pool on shutdown. The health check only
executes `select 1`; it does not expose feed freshness. Export an application
factory, add readiness/freshness separately, restrict allowed methods/origins as
appropriate for the public client, and implement graceful shutdown.

#### M3 — Worker recovery and observability rely heavily on platform restarts

`poller/poll_calgary_gtfs_rt_current.py` keeps one PostgreSQL connection for the
process lifetime, prints unstructured counters, uses a fixed retry interval, and
has no last-success/readiness signal. A rollback failure can terminate the
worker; repeated upstream failures have no exponential backoff or jitter. Add
structured poll-run records/logs, feed-specific duration/count/freshness, bounded
backoff, reconnection, and explicit failure thresholds.

#### M4 — Current-state feed semantics are incomplete

The worker upserts seen vehicles but never removes vehicles absent from a later
full feed. Trip-update cleanup occurs only when at least one trip is seen, and
only the first alert active period is stored. Feed incrementality and deleted
entities are not explicitly handled. The history endpoint hides many stale rows
because raw history expires, but `/api/vehicles` and route selection can still
read old current-state records. Record feed mode, define expiry per entity type,
handle deletion flags, and test empty/partial feeds.

#### M5 — The declared raw model and actual ingestion do not match

The schema contains trip-update and alert raw parent/child tables and views, but
the accepted worker only populates their current tables. Decide whether raw
history is a genuine observability requirement. Either implement bounded raw
ingestion/retention or remove the unused tables and views through migrations.

#### M6 — Static GTFS integrity is weakly constrained

Shapes, stop times, and calendar dates lack primary/unique keys; most static
relationships lack foreign keys. The transactional full refresh is a reasonable
first implementation, but it validates only filenames and lets database
constraints catch little source corruption. Add staging-table row counts,
coordinate/range checks, uniqueness tests, orphan checks, and a publish/swap
gate. Add constraints only after confirming real Calgary feed behavior.

#### M7 — Client failures are displayed as valid empty data

React fetches do not check `response.ok`, do not impose timeouts, and generally
turn errors into empty arrays. Consequently “No active route alerts” can mean a
healthy empty feed or an API failure. Add a shared API client with status checks,
abort support, typed/validated response boundaries, and distinct loading, empty,
stale, and error states.

#### M8 — React responsibilities are concentrated in oversized components

`frontend/src/App.jsx` is 672 lines and owns API calls, playback math, Leaflet
icons, selection, layout, and detail fetching. `SelectedCorridor.jsx` contains a
large obsolete implementation in comments. Extract pure playback/geometry
utilities, a transit API module, polling hooks, selection/detail components, and
shared route styling. This is an incremental refactor; React and React Leaflet
remain appropriate.

#### M9 — Transit accessibility needs a non-map interaction path

Emoji `divIcon` markers are primarily pointer-driven, the close button has no
accessible label, map state lacks a complete textual equivalent, and animation
does not honor reduced-motion preference. Provide a keyboard-accessible vehicle
list, named controls, live but non-noisy freshness announcements, reduced-motion
behavior, and text summaries for route/stops/alerts.

#### M10 — The committed build can diverge from source

Running the verified build changed the hashed main bundle while no React source
was changed during this review. This proves the committed `frontend/dist` was
stale relative to source. A generated bundle in Git is acceptable only as a
temporary deployment constraint, but CI must build and verify it or Railway must
build from source. Prefer the latter after a deployment spike.

#### M11 — Runtime browser assets depend on third-party hosts

Leaflet marker images load from unpkg while map tiles load from OpenStreetMap and
CARTO. Map tiles are expected external services; marker artwork is a small
build-time asset and should be local to reduce runtime failure and tracking
surface. Document tile-provider terms, attribution, and rate expectations.

#### M12 — Portfolio pages currently overstate completion

The Contact page displays a success message without delivering anything.
Projects and résumé timeline contain placeholders, Dashboard uses sample cache
data, and privacy/terms links do not resolve. Until their planned phases land,
label demos/sample data honestly and do not claim a message was sent.

### Low and maintainability

- `backend/transit_api/server.js` contains hundreds of lines of superseded
  commented SQL and a duplicate unused `buildVehicleWhere`.
- `app/services/gtfs_updater.py`, `app/services/poller.py`, transit page files,
  and several React files retain large commented predecessors.
- `DashboardPage.jsx`, `TestRoutesPage.jsx`, and `AntPath.jsx` are not reachable
  from `main.jsx`; generated starter SVG assets also appear unused.
- Several NiceGUI pages import `navbar` without using it; Dashboard imports an
  unused `datetime`.
- `dashboard_cache.json` is resolved relative to the process working directory
  instead of the repository/module path.
- Three PostgreSQL clients are present: Psycopg 3 for legacy NiceGUI, Psycopg 2
  for the accepted worker/bootstrap, and Node `pg` for the API. After legacy
  deletion, document the remaining language boundary rather than forcing one
  driver across languages.
- `logging.basicConfig` is configured at import time in `app/main.py`; application
  startup should own logging configuration.
- Background task references are not retained or cancelled explicitly during
  NiceGUI shutdown.
- The API parses JSON request bodies although all current routes are GET and use
  no request body.

## React walkthrough in plain language

### Entry and shell

`frontend/src/main.jsx` asks React to render `App` into the single `#root`
element. `PortfolioNav` is a normal React component that reads the shared theme
preference once, stores it as component state, and mirrors changes to the HTML
element and browser storage.

### State

Think of React state as the current working set for the screen:

- `mode` is the selected vehicle filter.
- `vehicleHistory` is the latest API response containing real observations.
- `vehicles` is the derived playback position for each bus.
- `routePaths` is the line geometry displayed on Leaflet.
- `selectedVehicle` and `selectedContext` drive highlighting and details.
- timestamps distinguish source-data time, fetch time, and displayed refresh
  age.
- `baseMap` selects the tile provider/style.

Changing state causes React to calculate the visible component tree again. It
does not reload the page.

### Effects and polling

An effect is code synchronized with something outside React:

1. one interval updates the “last refresh” age each second;
2. one effect fetches history and route paths immediately and every 30 seconds;
3. one effect fetches route/station context after a vehicle is selected;
4. one interval advances delayed playback every second.

Each interval effect returns cleanup code so React can stop the old interval
when dependencies change or the component unmounts. Boolean `cancelled` flags
prevent completed old requests from setting state, though `AbortController`
would also stop the network work itself.

### Delayed playback

`computePlaybackVehicles` is the key analytical function. It sorts each bus's
real observations, chooses the observations surrounding the playback clock, and
linearly interpolates between them. It does not extrapolate beyond known points.
Distance between observations determines the stopped label, while source age
determines stale status.

The playback clock intentionally stays about 75 seconds behind the newest source
observation. This creates enough history to animate smoothly despite a roughly
30-second upstream/poller interval.

### Map layers and selection

React Leaflet turns components into Leaflet layers:

- `TileLayer` supplies the visual basemap.
- `RouteLine` draws route shapes.
- each `Marker` represents one derived playback bus.
- `SelectedRouteAntPath` and `SelectedCorridor` emphasize the chosen route and
  upcoming stops.
- `FitToVehicles` uses Leaflet directly to frame visible buses after a filter
  changes.

Clicking a marker stores that bus in `selectedVehicle`. That triggers the context
effect and opens the detail drawer. Each playback tick replaces the selected
object with the newest derived object for the same vehicle ID, so its marker and
status keep moving without losing selection.

### Production build

Vite converts source modules and CSS into hashed browser assets. The base path
is `/calgary-transit-live/`, and NiceGUI serves `frontend/dist` at that same
path. The build also emits a separate `pdf-viewer.html` entry using PDF.js. At
present the generated output is tracked; therefore a source edit is not deployed
until the build is regenerated and the changed hash/index are committed.

## Legacy dependency and deletion inventory

### Runtime roots

| Legacy root | Evidence | Phase-2 disposition |
|---|---|---|
| Public-schema pool | `app/main.py:64-79`, startup `init_pool()` | Remove from web after endpoint/page characterization |
| Vehicle poller | `app/main.py:81`, `101`; `app/services/poller.py` | Remove; standalone `poller/` is accepted worker |
| Weekly updater | `app/main.py:80`, `102`; `app/services/gtfs_updater.py` | Remove; static bootstrap belongs to accepted schema |
| Python transit API | `app/main.py:110-304` | Remove after proving React uses Express URL/contracts |
| Hidden map | `app/main.py:94`; `app/pages/transit_map.py:265` | Remove after route smoke test |
| Superseded maps | `transit_map_v2.py`, commented predecessors | Delete |
| Manual loaders | `load_lrt.py`, `load_routes.py` | Delete or retain only as historical Git references |
| Public-schema DDL | `sql/*.sql` | Remove from active tree after snapshot/recovery decision |

### Legacy environment and database surface

- `DATABASE_URL` is used by both the legacy pool and accepted worker/bootstrap;
  the name must remain for the accepted path.
- `app.services.schedule` has process-local activity/pause state used only by
  the legacy poller and `/transit` page.
- Legacy public tables include vehicle raw/latest, daily samples, route
  geometry, LRT stations/shapes, and `gtfs_*` tables.
- Accepted tables and views are schema-qualified under `transit`.
- Psycopg 3, Psycopg Pool, `httpx`, and APScheduler must be re-evaluated after
  legacy removal; `httpx` may still be useful for future web integrations, but
  no production dependency should be removed solely from this inventory.

### Required proof before deletion

1. production React bundle contains and calls only the Express API base;
2. Railway web service has no documented dependency on public-schema endpoints;
3. Express contract tests cover all routes consumed by React;
4. poller fixture tests cover the accepted worker's three feeds;
5. web smoke test covers every NiceGUI page plus the React mount and PDF viewer;
6. database inventory confirms no accepted view/function depends on public
   tables;
7. a pre-removal database backup/recovery procedure is recorded;
8. deployment smoke tests pass separately for web, API, and worker.

## Test matrix

| Area | Current evidence | Required before phase-2 exit |
|---|---|---|
| Python syntax | `python3 -m compileall` passes | Keep as basic check |
| NiceGUI pages | Manual production checks | Automated route/mount/PDF smoke tests |
| Legacy endpoints | Manual/history only | Characterize response/status, then delete tests with code |
| Express service SQL | Five database-boundary cases in one test file | Add stops, invalid input, grouping edge cases, DB failure |
| Express HTTP | None | App-factory route tests for status, JSON contract, 400/404/500 |
| Poller parsing | None | Saved protobuf fixtures: full, empty, malformed, deleted, partial |
| Poller persistence | Production smoke only | Transaction/upsert/expiry tests against isolated PostgreSQL |
| Migrations | Clean isolated apply previously verified | Upgrade/drift/checksum and schema-contract tests |
| Static loader | Manual clean load | Fixture ZIP, missing fields, invalid rows, publish rollback |
| React lint/build | Passes | Retain in CI |
| Playback math | None | Unit tests for interpolation, boundaries, stopped/stale/invalid time |
| React data/UI | Manual | Loading/empty/error, filter, selection persistence, abort/race tests |
| Accessibility | Manual inspection | Keyboard route, names, reduced motion, automated baseline plus manual map test |
| Security | Secret grep; offline npm audits | Alert-XSS tests, headers/CORS, dependency audits in CI |
| Production | Manual Railway smoke | Scripted health/freshness/assets checks plus manual responsive check |

## Proposed target architecture

```text
                                    +------------------------------+
                                    | NiceGUI/FastAPI web          |
Browser --------------------------> | portfolio pages, auth,       |
  |                                 | contact, admin, static build |
  |                                 +---------------+--------------+
  |                                                 |
  | public transit JSON                            portfolio ORM
  v                                                 |
+---------------------+       +---------------------v--------------+
| Express transit API | ----> | one PostgreSQL service             |
| validated read API  |       | transit schema: explicit SQL       |
+---------------------+       | portfolio schema: ORM + migrations |
                              +---------------------^--------------+
                                                    |
Calgary feeds -> standalone poller -----------------+
scheduled analytical jobs -> validated snapshots / portfolio schema
```

Ownership rules:

- NiceGUI/FastAPI owns portfolio identity, contact, admin, page events, and
  structured content delivery.
- Express owns the public transit read contract and explicit transit queries.
- The standalone Python worker alone owns realtime ingestion.
- PostgreSQL is one service with separately owned `transit` and future
  `portfolio` schemas.
- Source-controlled JSON/YAML owns stable résumé timeline and initial case-study
  content until admin editing has demonstrated value.
- Weekly snapshots are published artifacts with provenance, not a substitute
  database.

## Proposed decisions for approval

1. Retain NiceGUI/FastAPI for the portfolio shell and React for interaction-heavy
   transit visualization; do not rewrite one framework into the other.
2. Remove the legacy public-schema transit runtime in phase 2 after the listed
   characterization tests.
3. Treat all upstream feed text as untrusted plain text.
4. Keep explicit SQL for `transit`; evaluate SQLAlchemy 2 plus Alembic only for
   the new `portfolio` schema.
5. Move frontend building into Railway/CI when a reproducible deployment check
   is proven; then stop tracking `frontend/dist` in a separate decision.
6. Make first-party operational events the analytics source for admin; keep GA4
   deferred.

## Sequenced implementation after approval

1. Add the minimum characterization tests and smoke scripts.
2. Remove the legacy startup/tasks/endpoints/page/services/DDL and legacy-only
   dependencies.
3. Fix alert rendering, API validation/error contracts, and distinct frontend
   failure states.
4. Add worker fixture/persistence tests, expiry semantics, reconnection, and poll
   observability.
5. Establish forward-only transit migrations and CI checks.
6. Refactor React into tested utilities/hooks/components without changing UX.
7. Move the frontend build to deployment automation and remove tracked output
   only after production verification.
8. Proceed to the structured portfolio content phase.

## Review verification

Commands executed:

```text
npm run check && npm test                       # backend/transit_api: pass
npm run lint                                    # frontend: pass
npm run build                                   # frontend: pass; exposed stale tracked bundle
python3 -m compileall -q app poller scripts     # pass
npm audit --offline --omit=dev                  # both Node apps: 0 reported
git diff --check                                # documentation: pass
```

The first attempted compilation used `python`, which is not installed on this
host; repeating it with `python3` passed. Offline audit results only cover
advisories available in the local npm cache and are not a substitute for CI
audits with current registry data.

## Review gate

The repository owner approved all six decisions on 2026-08-05. Phase 2 began
with passing boundary characterization tests, then removed the mapped legacy
runtime. Commit `ffdbfb0` deployed successfully and passed the production smoke
matrix. See `docs/PROJECT_STATE.md` for current status.
