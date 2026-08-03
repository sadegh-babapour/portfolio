# Current Project State

Last verified: 2026-08-03

## Project purpose

This repository is a personal portfolio web application. Its most substantial
project is an interactive Calgary Transit demonstration built from static GTFS
data and Calgary's VehiclePositions, TripUpdates, and Alerts GTFS-Realtime
feeds.

The repository currently contains two overlapping generations of the transit
feature:

1. A NiceGUI/FastAPI implementation using Python services and tables in the
   PostgreSQL public schema.
2. A newer React/Leaflet frontend with an Express API, a separate Python
   poller, and database objects under the PostgreSQL `transit` schema.

The newer stack is the intended direction for the Calgary Transit page. Local
recovery work has made its database bootstrap and frontend build reproducible,
but the complete multi-service Railway deployment is not yet verified.

## Version-control state

- Branch: `main`.
- Local `HEAD`: `eeb44cf` (`checkpoint before Codex repository recovery`).
- Public GitHub and local `origin/main`: `447ecbf`.
- The local branch is one commit ahead of the public branch.
- The checkpoint changes 768 files relative to `origin/main`, including source
  work, generated dependencies, a virtual environment, data, and sensitive
  configuration material.
- `docs/` was untracked when this recovery documentation was started.

Do not push the checkpoint unchanged. In particular, `.env.remote` is tracked
in the local-only commit and contains configured database fields rather than
safe placeholders.

## Confirmed by current code

### Working or structurally complete

- `python -m app.main` is the declared NiceGUI entry point in `Procfile`.
- NiceGUI portfolio routes exist for home, about, résumé, projects, contact,
  dashboard, and the legacy transit map.
- The theme-park dashboard reads committed sample data from
  `dashboard_cache.json` and does not require a live database.
- The React transit frontend implements:
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
- The repository includes Calgary static GTFS files and a route-category CSV.
- The current React source builds and lints successfully with Vite; production
  assets use the `/calgary-transit-live/` base path.
- All 26 first-party Python files parse successfully.
- Active first-party Express source passes `node --check`.
- A clean dependency install can import the packages used by both Python
  transit implementations.
- The complete dependency graph resolves to binary wheels for Railway's
  declared Linux CPython 3.13 runtime. This includes Psycopg 3.3.4, its
  matching binary package, Psycopg Pool 3.3.1, and Psycopg2 Binary 2.9.10.

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

- NiceGUI mounts `frontend/dist` at `/calgary-transit-live`, and Vite now emits
  production asset URLs for that path. A deployed HTTP smoke test remains.
- NiceGUI navigation now links to `/calgary-transit-live/`.
- The React application expects the Express API contract. NiceGUI exposes a
  different set of `/api` routes, so the default same-origin `/api` fallback is
  not a compatible production backend.
- The newer Express API and standalone poller run locally against current feed
  data but still lack verified Railway service configuration.
- The standalone current-state poller uses `requests` and `psycopg2`; both are
  now declared directly in `requirements.txt`.
- The legacy NiceGUI transit stack uses `DATABASE_URL`, while `.env.example`
  primarily documents individual `PG*` variables for the newer stack.
- The newer `transit` schema has ordered, idempotent migrations and a bootstrap
  loader. The migrations pass against an isolated PostgreSQL instance; a full
  live GTFS download/load remains to be verified.

## Known broken or incomplete behavior

- Initial Node database-boundary contract tests cover core transit service
  query parameters and response grouping. Python, frontend, and HTTP-level API
  tests are still absent.
- The sole `Procfile` starts only NiceGUI; it does not start the Express API or
  the standalone current-state poller.
- The React and Express `package.json` files do not provide a complete
  repository-level orchestration workflow; the Express package has no scripts.
- The contact form only displays a notification and sends no message.
- Several portfolio pages still contain sample résumé, chart, and image data.
- Footer links target unimplemented privacy and terms routes.
- Experimental and superseded transit implementations remain in the tree,
  including large commented blocks.
- The legacy NiceGUI `/transit` route remains available but has been removed
  from navigation. It expects public-schema tables and is not compatible with
  the newer `transit` schema.
- Generated/runtime dependencies and bytecode have been removed from the
  publishable working tree and ignored. The generated frontend build and large
  data artifacts still require an explicit source-control policy.

## Current development environment

- Host observed during recovery: Linux/Ubuntu-compatible environment.
- System Python: 3.12.3.
- Declared production Python: 3.13.
- Checked-in virtual environment: Python 3.12.
- Node: 24.18.1.
- npm: 11.16.0.
- Frontend package manager: npm with lockfile v3.
- Express package manager: npm with lockfile v3.
- Databases represented in code: PostgreSQL public schema and PostgreSQL
  `transit` schema.
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
- The current résumé page also references an external sample PDF viewer and
  sample PDF.

No external service credentials belong in these documents.

## Stated in chat but not confirmed as implemented

- A working three-service Railway deployment consisting of NiceGUI web,
  Express transit API, and Python poller.
- A successful Railway database rebuild using the locally verified SQL
  migrations and static GTFS loader.
- A production React API base URL supplied at build time.
- Correct production hosting of the React bundle at
  `/calgary-transit-live`.
- Verification of local app + local database, local app + Railway database,
  and deployed app + Railway database modes.

## Contradicted by current code

- The chat describes separate Railway services as the completed deployment
  shape; the repository contains only a single Python `Procfile` command.

## Confirmed Railway state

- Railway currently has one application service named `portfolio` and one
  PostgreSQL service named `postgres`.
- The application deploys branch `main` with Railpack and is detected as a
  Python application.
- The observed failed build selected Python 3.13.14, installed
  `requirements.txt`, and selected `python -m app.main` from `Procfile`.
- The observed failure was caused by the deployed branch still requesting
  `psycopg[binary,pool]==3.2.1`; no matching Psycopg binary package was
  available for that environment.
- The local recovery tree requests Psycopg 3.3.4, whose complete dependency
  graph has been verified for Linux CPython 3.13.

## Unknown or unverified

- The current Railway public URL and live production behavior.
- Railway variable names, root-directory overrides, healthcheck, and database
  contents.
- Whether any database credentials in the checkpoint have been exposed or
  rotated.
- Whether the configured local or remote PostgreSQL databases are reachable or
  contain the schema/data represented in the snapshot.
- Whether Calgary's live feeds still have the same field availability observed
  in April 2026.
- Which database schema should be retained after recovery of the newer stack.
- Whether the broader portfolio content is ready for public presentation.
