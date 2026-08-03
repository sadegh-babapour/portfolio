# Portfolio and Calgary Transit

This repository contains a NiceGUI personal portfolio and an interactive
Calgary Transit demonstration. The transit page uses a React/Leaflet frontend,
an Express API, a Python GTFS-Realtime poller, and PostgreSQL.

The newer transit data flow is:

```text
Calgary GTFS/GTFS-RT -> Python poller -> PostgreSQL -> Express API -> React
                                                                    |
                                               NiceGUI serves the built app
```

See `docs/PROJECT_STATE.md` for current limitations and
`docs/ARCHITECTURE.md` for the detailed design.

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

React development server:

```bash
npm run dev --prefix frontend
```

Set `VITE_TRANSIT_API_BASE_URL=http://localhost:4000/api` for local React
development. Build the production bundle with:

```bash
npm run build --prefix frontend
```

NiceGUI portfolio and production React mount:

```bash
python -m app.main
```

The portfolio listens on `PORT` or 8086. The built React application is served
at `/calgary-transit-live/`.

The NiceGUI process still starts an older public-schema transit poller and GTFS
updater. Those legacy services use `DATABASE_URL` and are separate from the
newer `transit` schema workflow described above.

## Checks

```bash
npm run lint --prefix frontend
npm run build --prefix frontend
npm run check --prefix backend/transit_api
npm test --prefix backend/transit_api
python -m compileall -q app poller scripts
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

Railway service configuration and successful production behavior remain to be
verified against the actual Railway project before they are described here as
complete.
