# Bizqlab Portfolio and Calgary Transit

This repository contains Bizqlab, a NiceGUI data-engineering and analytics
portfolio with public case studies, optional registered-user Project Lab notes,
an owner-published blog, and an interactive Calgary Transit demonstration. The
transit page uses a React/Leaflet frontend, an Express API, a Python
GTFS-Realtime poller, and PostgreSQL.

The Calgary rider view supports route and stop-number search, delayed trip-safe
vehicle playback, direction indicators, shape-aligned movement, explicit
nearby-stop lookup, per-stop route choices, and the next three scheduled or
predicted arrivals per route within three hours. Browser location is requested
only after the visitor chooses “Near me” and is not retained by Bizqlab.
Signed-in users can save stop IDs and reopen those stops from the transit page.

The public analytics dashboard demonstrates two delivery contracts: short-lived,
timeout-bounded PostgreSQL aggregates for Calgary pipeline quality and a small
validated JSON snapshot for stable theme-park analysis. The owner-only health
page charts anonymous allow-listed page renders without expanding the stored
path-and-time event schema.

The transit data flow is:

```text
Calgary GTFS/GTFS-RT -> Python poller -> PostgreSQL -> Express API -> React
                                                                    |
                                               NiceGUI serves the built app
```

The repository README is intentionally the only public Markdown document.
Operational handoff notes, security reviews, decision records, and deployment
runbooks are maintained privately and are excluded from Git.

## Prerequisites

- Python 3.13 for parity with production (3.12 is also locally verified)
- Node.js and npm
- PostgreSQL 16 or another currently supported PostgreSQL release

Do not commit `.env` files or database credentials. Copy `.env.example` to the
ignored root `.env.local` and replace its placeholder values.

### Local database isolation

Every command that opens a database resolves its target itself, before any
connection, from two inputs:

- the root `.env.local` profile, read with a strict `KEY=value` grammar (no
  `export`, no interpolation, no `DATABASE_URL`); its `PGHOST`, `PGPORT`,
  `PGDATABASE`, `PGUSER`, `PGPASSWORD` and `PGSSLMODE` name the development
  database;
- a root-owned approval policy at
  `/Library/Application Support/Bizqlab/db-policy.json` (Linux:
  `/etc/bizqlab/db-policy.json`) that names the same host, port, database and
  role, plus the address and port the server reports. It holds no password;
  `ops/db-policy.example.json` shows its shape.

Do not export database variables or `source` environment files. An inherited
`DATABASE_URL` or `PG*` value, or a command-line database flag, that differs from
the approved target is refused rather than silently replaced, and every new
connection checks the server's database, role, address and port before running
anything else. Railway context variables on a workstation are refused too.

## Install

Create a Python environment and install the backend dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Install the two JavaScript dependency sets:

```bash
npm ci --prefix frontend
npm ci --prefix backend/transit_api
```

## Bootstrap PostgreSQL

Check the approved target first (read-only: it opens one connection and runs only
the identity query):

```bash
python ops/dev.py check --expected-db portfolio_dev
```

Apply the `transit` schema migrations and download/load Calgary's current
static GTFS data:

```bash
python scripts/bootstrap_transit_db.py --load-static \
  --route-catalog data/Calgary_Transit_Routes_20260417.csv
```

Running the command again is supported. Static GTFS tables are replaced only
when `--load-static` is supplied; realtime tables are retained. The large raw
`stop_times.txt` does not need to be kept in the repository: the loader reads
it from Calgary's downloadable GTFS ZIP.

## Run locally

Run each long-lived component in a separate terminal. Each command resolves the
approved target on its own, so no environment exports are needed. Optionally start
one through the launcher, which checks the target first and refuses on any
mismatch:

```bash
python ops/dev.py run --expected-db portfolio_dev -- python -m app.main
```

Current-state GTFS-Realtime poller:

```bash
python -m poller.poll_calgary_gtfs_rt_current
```

Use `--once` for a single realtime ingestion pass. The long-running worker also
applies the idempotent transit migrations on startup and checks Calgary's
static GTFS every six hours. It uses HTTP ETags and an archive SHA-256 to avoid
unnecessary reloads, and replaces the static tables plus its import state in
one transaction when the source changes. Polling behavior is controlled by
`POLL_INTERVAL_SECONDS`, `POLL_ENABLED`, `POLL_START_HOUR`, `POLL_END_HOUR`,
`POLL_TIMEZONE`, `ADMIN_KILL_SWITCH`, `RAW_RETENTION_MINUTES`,
`GTFS_AUTO_SYNC_ENABLED`, `GTFS_SYNC_INTERVAL_SECONDS`, `GTFS_STATIC_URL`,
`GTFS_ROUTE_CATALOG`, and `TRANSIT_APPLY_MIGRATIONS`.

Express transit API:

```bash
npm start --prefix backend/transit_api
```

The API listens on `TRANSIT_API_PORT`, then `PORT`, then port 4000.
Its public transit routes include vehicle history/context, route paths and
search, stop search, saved-stop detail hydration, routes serving a stop, and
scheduled/live arrivals, plus a bounded `POST /api/stops/nearby` coordinate
lookup. Nearby lookup is capped at eight stops and accepts a server-validated
100–2,000 metre radius; the frontend uses an 800 metre walkable radius and
renders the returned stops on the map.

React development server:

```bash
npm run dev --prefix frontend
```

Set `VITE_TRANSIT_API_BASE_URL=http://localhost:4000/api` in
`frontend/.env.development.local` for local React development. Do not use
`frontend/.env.local`; Vite also loads that file during builds. The API target is
always explicit: the dev server and every build refuse to start without a valid
one, and nothing falls back to the deployed API or to NiceGUI's unrelated
same-origin `/api` namespace. Each build records its target in
`dist/transit-api-target.json`.

Build the production bundle (it targets the deployed transit API explicitly):

```bash
npm run build --prefix frontend
```

Build a bundle for an isolated preview API instead, and check it before serving:

```bash
VITE_TRANSIT_API_BASE_URL=https://<preview-api-domain>/api npm run build:preview --prefix frontend
python ops/check_frontend_bundle.py --expect-api https://<preview-api-domain>/api
```

NiceGUI portfolio and production React mount:

```bash
python -m app.main
```

The portfolio listens on `PORT` or 8086. The built React application is served
at `/calgary-transit-live/`.

Apply portfolio-domain database migrations before enabling contact submission:

```bash
alembic upgrade head
```

The résumé is read locally from the ignored `static/resume.pdf` by default.
Production reads it from the Railway volume using
`RESUME_PDF_PATH=/data/resume.pdf`.
An administrator replaces it from `/admin/resume` (PDF only, 5 MB or smaller); the
new file is written beside the old one and swapped in, and `/resume` links it
with a version query so browsers and Cloudflare fetch the new copy.

The on-page résumé timeline is separate from the PDF. An administrator edits it
at `/admin/resume` (add, edit, hide, reorder, delete); entries are stored in
`portfolio.resume_entries` and show on `/resume` as soon as they are saved, with
no deployment. With no visible entries the page shows only the PDF.

Project case studies live in `content/projects.json`. That is a source-controlled
file, so changing it requires validation, commit/push and a web deployment.
Application validation rejects malformed content before rendering it.

Blog articles use a different workflow. An allowlisted administrator can open
`/admin/blog`, write Markdown, preview the sanitized result, save drafts, and
publish, or permanently delete a selected article after confirmation. Published
articles appear at `/blog` immediately because posts and their revision history
live in PostgreSQL; article deletion cascades to that revision history. Adding,
editing, publishing, or deleting article content does not require rebuilding or
redeploying the services. Code or schema changes still require the normal
deployment and `alembic upgrade head`.

Contact uses a visible managed Cloudflare Turnstile check, same-origin CSRF,
database throttling, one-time inbox verification, and Resend HTTPS delivery.
Signed-in name/email are prefilled; account-deletion requests lock that identity
and enter the reviewed privacy-request workflow rather than immediately deleting
data. The shared navigation displays the signed-in user's first name, while all
authorization remains enforced by server-side sessions and roles.

## Checks

```bash
npm run lint --prefix frontend
npm test --prefix frontend
npm run check --prefix backend/transit_api
npm test --prefix backend/transit_api
python test/run_isolated.py
python -m compileall -q app poller scripts test migrations ops
```

`test/run_isolated.py` runs the Python suite with database connections, network
sockets, dotenv discovery and reads of the real profile and policy blocked; the
transit API tests run behind the equivalent Node shim. To check a build without
touching the tracked `frontend/dist`, add `-- --outDir <temporary directory>`.
The same checks run in `.github/workflows/checks.yml`.

## Railway deployment

The accepted target is three services from this repository sharing one
Railway PostgreSQL database:

1. Web: build `frontend`, then run `python -m app.main`.
2. Transit API: run `npm start --prefix backend/transit_api` and expose its
   generated Railway domain.
3. Poller worker: run `python -m poller.poll_calgary_gtfs_rt_current`.

The React bundle served by the web service is built with `npm run build`, which
targets the public API domain plus `/api` explicitly. Configure the database
through Railway reference variables; never put production values in this
repository. Deployed processes reach the database only in the attested production
mode: `BIZQLAB_RUNTIME=production`, Railway's service identifiers, and a build
attestation generated during that service's Railway build
(`ops/write_build_attestation.py` for the repository root,
`npm run attest:write` for `backend/transit_api`). Without them a process refuses
to start before connecting.

The web, API, poller worker, and database-backed transit page are deployed and
have passed the current production smoke checks. The superseded NiceGUI transit
runtime has been removed from source and production; the public legacy page and
control routes now return 404.
