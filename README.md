# Bizqlab Portfolio and Calgary Transit

This repository contains Bizqlab, a NiceGUI data-engineering and analytics
portfolio with public case studies, optional registered-user Project Lab notes,
and an interactive Calgary Transit demonstration. The transit page uses a
React/Leaflet frontend, an Express API, a Python GTFS-Realtime poller, and
PostgreSQL.

The Calgary rider view supports active route and stop search, delayed
trip-safe vehicle playback, direction indicators, shape-aligned movement to the
next three predicted stops, explicit nearby-stop lookup, and 15-minute arrival
predictions. Browser location is requested only after the visitor chooses
“Near me” and is not retained by Bizqlab. Signed-in users can save stop IDs to
their portfolio account.

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

Do not commit `.env` files or database credentials. Copy `.env.example` into a
local, ignored environment file and replace its placeholder values.

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

Export either `DATABASE_URL` or the `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`,
and `PGPASSWORD` variables from `.env.example`.

Apply the `transit` schema migrations and download/load Calgary's current
static GTFS data:

```bash
python scripts/bootstrap_transit_db.py --load-static \
  --route-catalog data/Calgary_Transit_Routes_20260417.csv
```

Running the command again is supported. Static GTFS tables are replaced only
when `--load-static` is supplied; realtime tables are retained.

## Run locally

Run each long-lived component in a separate terminal with the same database
environment variables.

Current-state GTFS-Realtime poller:

```bash
python -m poller.poll_calgary_gtfs_rt_current
```

Use `--once` for a single ingestion pass. Polling behavior is controlled by
`POLL_INTERVAL_SECONDS`, `POLL_ENABLED`, `POLL_START_HOUR`, `POLL_END_HOUR`,
`POLL_TIMEZONE`, `ADMIN_KILL_SWITCH`, and `RAW_RETENTION_MINUTES`.

Express transit API:

```bash
npm start --prefix backend/transit_api
```

The API listens on `TRANSIT_API_PORT`, then `PORT`, then port 4000.
Its public transit routes include vehicle history/context, route paths and
search, stop search and arrivals, and a bounded `POST /api/stops/nearby`
coordinate lookup.

React development server:

```bash
npm run dev --prefix frontend
```

Set `VITE_TRANSIT_API_BASE_URL=http://localhost:4000/api` in
`frontend/.env.development.local` for local React development. Do not use
`frontend/.env.local`; Vite also loads that file during production builds.
When no override is supplied, the bundle uses the deployed public transit API;
it never falls back to NiceGUI's unrelated same-origin `/api` namespace.
Build the production bundle with:

```bash
npm run build --prefix frontend
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

The on-page résumé timeline and project case studies are separate from the PDF
Application validation rejects malformed content before rendering it.

## Checks

```bash
npm run lint --prefix frontend
npm run build --prefix frontend
npm run check --prefix backend/transit_api
npm test --prefix backend/transit_api
python -m unittest discover -s test -v
python -m compileall -q app poller scripts test
```

## Railway deployment

The accepted target is three services from this repository sharing one
Railway PostgreSQL database:

1. Web: build `frontend`, then run `python -m app.main`.
2. Transit API: run `npm start --prefix backend/transit_api` and expose its
   generated Railway domain.
3. Poller worker: run `python -m poller.poll_calgary_gtfs_rt_current`.

Set `VITE_TRANSIT_API_BASE_URL` to the public API domain plus `/api` during the
web build. Configure the database through Railway reference variables; never
put production values in this repository.

The web, API, poller worker, and database-backed transit page are deployed and
have passed the current production smoke checks. The superseded NiceGUI transit
runtime has been removed from source and production; the public legacy page and
control routes now return 404.
