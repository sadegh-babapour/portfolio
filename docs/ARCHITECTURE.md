# Architecture

Last reconciled with code and history: 2026-08-13

## Overview

The repository is a NiceGUI personal portfolio containing a newer React-based
Calgary Transit project. During development the transit feature moved from a
Python-only prototype to a three-component design:

```text
Calgary GTFS/GTFS-RT -> Python poller -> PostgreSQL transit schema
                                             |
Browser React app <- JSON <- Express API ----+
       |
       +-- built bundle served by NiceGUI/FastAPI
```

This three-service design is deployed and functioning. The legacy public-schema
NiceGUI transit runtime has been removed from source and production.

## Repository layout

- `app/`: NiceGUI portfolio pages, shared layout components, résumé delivery,
  authentication/contact domain foundations, and the React static mount.
- `content/`: versioned, source-controlled JSON for the on-page résumé timeline
  and public project case studies.
- `frontend/`: React/Vite/Leaflet Calgary Transit application and checked-in
  production build.
- `backend/transit_api/`: Express API, PostgreSQL pool, configuration, and SQL
  service functions for the `transit` schema.
- `poller/`: standalone Python ingestion worker for the transit stack.
- `scripts/db/`: ordered, idempotent migrations for the `transit`
  schema.
- `migrations/`: Alembic migrations for ORM-owned contact and authentication
  tables in the isolated `portfolio` schema.
- `scripts/bootstrap_transit_db.py`: schema migration and static GTFS loader.
- `data/`: static Calgary GTFS and route-category files.
- `database_backup.sql`: schema-only dump of the newer `transit` model.
- `dashboard_cache.json`: committed sample data for the unrelated theme-park
  dashboard.
- `docs/`: recovery state, architecture, decisions, next actions, session log,
  source suggestions, and raw historical conversation.

## Application entry points

### NiceGUI web application

- Command: `python -m app.main`.
- Module: `app/main.py`.
- Responsibilities:
  - register NiceGUI portfolio pages;
  - serve the volume-backed résumé route;
  - mount `static/` and the React build.
- Port: `$PORT` or 8086.

### React application

- Development command: `npm run dev` from `frontend/`.
- Production build: `npm run build` from `frontend/`.
- Entry: `frontend/src/main.jsx` rendering `frontend/src/App.jsx`.
- Production API base: `VITE_TRANSIT_API_BASE_URL`, falling back to `/api`.
- The same Vite build also emits `pdf-viewer.html`, a non-React PDF.js canvas
  viewer used by the NiceGUI résumé page. Its bundled worker and display layer
  are served under `/calgary-transit-live/assets/`.

### Express transit API

- Command: `npm start --prefix backend/transit_api`.
- Port precedence: `$TRANSIT_API_PORT`, `$PORT`, then 4000.
- PostgreSQL configuration: individual `PGHOST`, `PGPORT`, `PGDATABASE`,
  `PGUSER`, and `PGPASSWORD` variables.

### Standalone current-state poller

- Module: `poller/poll_calgary_gtfs_rt_current.py`.
- It consumes VehiclePositions, TripUpdates, and Alerts feeds and writes the
  newer `transit` tables.
- Database configuration accepts `DATABASE_URL`, individual `PG*` variables,
  or matching command-line arguments; scheduling, kill switch, and retention
  settings use environment variables.
- This poller is not started by the current `Procfile`.

## Components and responsibilities

### Portfolio shell

NiceGUI provides navigation, page layouts, static portfolio content, the
theme-park sample dashboard, and résumé delivery. FastAPI is exposed through
NiceGUI and owns the document route and static mounts.

Stable portfolio copy follows a small content pipeline:

```text
content/*.json -> app/content.py validation -> NiceGUI résumé/projects pages
```

The JSON is intentionally read-only at runtime and remains reviewable in Git.
The deployed application must not attempt to rewrite files inside its image.
When admin editing is introduced, editable content and operational records
(users, contact state, jobs, service checks, and audit events) will live in an
ORM-owned portfolio schema in PostgreSQL. Transit continues to own its existing
schema and explicit SQL independently.

### Contact workflow

FastAPI owns three same-origin contact endpoints for CSRF state, pending-message
creation, and email verification. SQLAlchemy owns contact messages, keyed abuse
attempts, and audit events in the `portfolio` schema; Alembic owns only that
schema's migration history. The accepted message lifecycle is:

```text
browser -> CSRF/origin/validation/rate limit -> Cloudflare Siteverify
        -> PostgreSQL pending message -> Resend HTTPS verification email
        -> one-time verification -> Resend owner delivery with verified Reply-To
```

The browser receives only the Turnstile sitekey. Database, token, Turnstile
secret, and Resend credentials remain server-side environment variables. Missing
configuration disables submission and makes the API fail closed.
The widget is rendered explicitly but does not execute until a valid form is
submitted. Its success callback sends the resulting single-use token, which the
server immediately validates through Siteverify.

### Authentication and protected content

FastAPI owns Google authorization-code OIDC endpoints, while SQLAlchemy owns
Google identities, user roles, opaque server sessions, login states, and
bounded events in the existing `portfolio` schema. The official `google-auth`
library verifies signed ID tokens; Requests performs the one-time HTTPS code
exchange. Google access and refresh tokens are never modeled or retained.

The browser receives only opaque session, CSRF, and short-lived login-binding
values. PostgreSQL stores their SHA-256 digests. State, nonce, browser binding,
verified email, Google stable subject, expiry, disabled-user state, and
root-relative return paths are checked before a local session is issued.

Every successful first login creates a local user and `registered` role.
`admin` comes only from configured subject/email allowlists. Projects remains
public, while a validated Calgary Project Lab renders deeper technique,
trade-off, and AI-assisted working-method notes only after server-side role
enforcement. `/account` provides logout and local-account deletion;
`/privacy` and `/terms` describe the boundary. Missing Google configuration
keeps login disabled without affecting public pages. See
`docs/AUTH_SECURITY.md`.

### Calgary Transit frontend

React and React Leaflet provide the interactive map. The application:

- requests recent histories and route geometry from Express;
- plays observations approximately 75 seconds behind the newest data;
- interpolates only between real observations;
- marks small movement as stopped and old observations as stale;
- renders route lines, selected vehicle context, stops, and alerts;
- distinguishes fresh data, a degraded feed, and expected after-hours downtime;
- displays the City of Calgary open-data licence attribution with the map;
- adapts the map/detail layout for mobile screens.

The frontend never connects directly to PostgreSQL.

### Transit API

Express owns frontend-facing queries. `db/pool.js` creates the `pg` pool, while
`services/transitService.js` contains SQL and response grouping. The API reads
views and tables in the `transit` schema and exposes:

- `GET /` and `GET /api/health`;
- `GET /api/vehicles`;
- `GET /api/vehicles/history`;
- `GET /api/routes/paths`;
- `GET /api/vehicles/:vehicleId/context`;
- `GET /api/vehicles/:vehicleId/stops`;
- `GET /api/vehicles/:vehicleId/alerts`.

Health is a data-freshness contract, not only a database-connectivity probe. It
reports recent vehicle count and latest feed timestamps and classifies the
service as `healthy`, `degraded`, or `outside_operating_hours` using the poller's
08:00-21:00 America/Edmonton schedule.

### Data ingestion

The intended poller uses three Calgary feeds:

- VehiclePositions for vehicle/trip/coordinate observations;
- TripUpdates for route references and stop predictions;
- Alerts for active periods, text, affected routes, and affected stops.

It retains current-state tables for fast API queries and a short raw position
history for delayed playback and debugging.
Each realtime feed owns its transaction within a polling cycle. A malformed or
temporarily unavailable feed is rolled back and logged without discarding
successful updates from the other two feeds; total feed failure still raises a
cycle-level error.

## Data flow

### Transit flow

1. The Python poller downloads the three Calgary GTFS-Realtime protobuf feeds.
2. Vehicle positions are upserted by `vehicle_id`; trip updates by `trip_id`;
   alerts by feed entity ID.
3. Static GTFS tables enrich live `trip_id`, route, shape, and stop references.
4. PostgreSQL views classify in-service and unmatched movements and expose
   frontend-ready route/stop/alert data.
5. Express queries PostgreSQL and returns JSON.
6. React fetches history and paths every 30 seconds, renders delayed playback,
   and fetches details for the selected vehicle.

## Database structure

### `transit` schema

The schema-only dump represents these groups:

- Static GTFS: routes, trips, stops, stop times, shapes, calendar, and calendar
  dates.
- Route catalog/category data.
- Current realtime state: vehicle positions, trip updates and stop times,
  alerts and informed entities.
- Raw realtime history for diagnostics and delayed playback.
- Views such as `v_vehicle_dashboard`, `v_trip_upcoming_stops`, route/position
  enrichment, and active alerts.

The dump does not provide static or realtime rows. The split migrations and
static loader have been verified against an isolated PostgreSQL 16 database
using Calgary's current downloadable GTFS archive.

## External integrations

- Calgary open-data GTFS static ZIP.
- Calgary VehiclePositions, TripUpdates, and Alerts GTFS-Realtime endpoints.
- PostgreSQL locally and on the intended Railway environment.
- Railway for intended web/API/worker hosting.
- OpenStreetMap and CARTO tiles.
- Unpkg-hosted Leaflet marker images.
- A Railway volume attached to the NiceGUI `portfolio` service for private
  runtime documents. The résumé is proxied through the same-origin
  `/resume/document.pdf` route and is never addressed by its volume path in
  browser code.

External integrations must be configured without committing credentials.

## Local development flow

The local workflow uses three terminals after loading local
environment variables:

1. Run the standalone current-state poller against local PostgreSQL.
2. Run `node backend/transit_api/server.js`.
3. Run `npm run dev` in `frontend/`, or build React and run
   `python -m app.main` for integrated static serving.

This workflow has been verified from clean Python and Node dependency installs
against an isolated PostgreSQL 16 database. A current static GTFS load, one
complete live poll, all Express endpoint families, and the NiceGUI production
React mount succeeded on 2026-08-03.

## Deployment flow

The accepted target is one Git repository with three Railway services sharing
one PostgreSQL database:

1. Web: install Python and frontend dependencies, build React, then run
   `python -m app.main`.
2. Transit API: install `backend/transit_api` dependencies, then run its
   `server.js`.
3. Poller worker: install Python dependencies, then run the standalone
   current-state poller.

The web build must receive the public Express API URL through
`VITE_TRANSIT_API_BASE_URL` at build time. The poller should observe configured
Calgary operating hours and administrative disable flags.

Service-specific Railway commands remain configured in the Railway dashboard
rather than `railway.json`. The public portfolio and Express API domains and
poller scheduling/freshness have been verified at the deployed baseline.

## Runtime file storage

The repository ignores personal/runtime documents such as
`static/resume.pdf`. Development keeps a local copy at that path; production
keeps a separate copy on the `portfolio` Railway volume and selects it through
`RESUME_PDF_PATH`. The browser obtains the document only through the same-origin
route, and the locally bundled PDF.js viewer renders it into canvases. This
policy does not apply to build inputs or database data.
See `docs/FILE_STORAGE.md` for the operational procedure.

## Planned evolution (not yet architecture)

The review, source-level legacy cleanup, and initial structured content layer
are complete. Proposed future areas include an ORM-owned portfolio domain,
verified contact delivery, Google identity, protected content, admin
operations, privacy-aware analytics, scheduled data snapshots, live analytical
queries, a Toronto subway schematic, and Calgary nearby-stop arrivals.

These are product goals, not current components. Technology and schema choices
must be recorded as ADRs at their decision gates. See `docs/ROADMAP.md` for
sequencing.
