# Next Actions

Last updated: 2026-08-03

## Immediate

- [ ] Prevent the local checkpoint from being pushed unchanged.
  - Remove `.env.remote` and any other secret-bearing environment files from
    tracked history before publishing.
  - Rotate configured remote database credentials if they may be real or
    exposed.
  - Do not print secret values while auditing them.
- [x] Preserve a recoverable reference to the current local checkpoint before
  restructuring its contents (`recovery-checkpoint-eeb44cf`).
- [x] Remove dependency directories, virtual environments, bytecode, caches,
  and secret-bearing environment files from the publishable working tree.
- [x] Rebuild the newer `transit` database bootstrap from the authoritative
  schema-only dump and current query requirements.
  - Populate table, view, and index migration files.
  - Establish a reproducible static GTFS and route-catalog loader.
  - Exclude old realtime rows from migration; let the poller refill them.
- [x] Establish the exact clean local startup procedure without redesigning
  the application.
  - Create a fresh environment from declared dependencies.
  - Start PostgreSQL from a reproducible bootstrap.
  - Start poller, Express API, React/Vite, and NiceGUI separately.
  - Record every failure before fixing it.

## Integration recovery

- [x] Make the Vite production build safe at `/calgary-transit-live`.
- [x] Change NiceGUI navigation from the nonexistent `/map` route to the
  accepted transit route.
- [ ] Configure React to use the Express API in local and production modes.
- [x] Add explicit start scripts to the Express package; document all
  service commands.
- [x] Declare `requests` and the selected Psycopg 2 package directly because the
  standalone poller remains the worker entry point.
- [x] Update Psycopg 3 to 3.3.4 and verify that the complete requirements set
  resolves to Linux CPython 3.13 wheels.
- [ ] Decide when the older public-schema poller, GTFS updater, Python transit
  API, and NiceGUI transit map can be retired. Do not remove them until the
  newer path is verified.

## Verification and quality

- [x] Fix current React lint errors without changing map behavior.
- [x] Add initial database-boundary contract tests for vehicles, history,
  route paths, context, and alerts.
- [ ] Expand API tests to cover HTTP routing, health, stops, and database
  failure behavior.
- [ ] Add poller parsing/upsert tests using saved protobuf fixtures and a test
  database boundary.
- [ ] Add frontend tests for delayed playback, stopped/stale classification,
  selection persistence, filters, and empty/error responses.
- [ ] Automate the manually verified NiceGUI mount and production asset smoke
  test.
- [x] Recheck current Calgary feed field availability before describing it as
  current behavior.

## Deployment

- [x] Record the current Railway service count, builder, Python version,
  dependency failure, and detected start command.
- [ ] Obtain the public production URL and remaining app-service settings.
- [ ] Configure three Railway services only after all three local processes are
  reproducible.
- [ ] Provide the public Express URL as `VITE_TRANSIT_API_BASE_URL` during the
  web service build.
- [ ] Verify poller hours, timezone, retention, `POLL_ENABLED`, and
  `ADMIN_KILL_SWITCH` in Railway.
- [ ] Verify the web page, API health, database freshness, route selection,
  stops, alerts, and mobile layout in production.

## Later

- [ ] Replace sample résumé, project, contact, privacy, and terms content with
  intended portfolio behavior.
- [ ] Decide whether route density/quadrant curation remains a product goal.
- [ ] Revisit Calgary LRT only if live vehicle positions become available.
- [ ] Treat future Toronto TTC subway/train work as a separate feature and
  architecture decision.
- [x] Rewrite the root README after clean startup and deployment commands are
  verified.

## Blocked

- [ ] Verify current production behavior — blocked by the missing Railway/site
  public URL and lack of Railway project access.
- [ ] Confirm the remote database contents — blocked until credentials and
  authorization are handled safely.
- [ ] Confirm which older transit implementation can be deleted — blocked
  until the newer end-to-end path runs against a reproducible database.

## Current recommended next task

Publish the reviewed recovery commit to `main` so Railway can rebuild the
existing NiceGUI service with Psycopg 3.3.4. Verify that service before adding
the Express API and poller services.
