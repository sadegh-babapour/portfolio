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
- [x] Add matching desktop/mobile portfolio navigation inside the standalone
  React transit bundle.
- [x] Match the NiceGUI desktop/mobile navigation to the deployed React header.
- [x] Configure React to use the Express API in local and production modes.
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
- [x] Remove the oversized tracked `data/stop_times.txt`; the reproducible
  bootstrap downloads current static GTFS instead.

## Deployment

- [x] Record the current Railway service count, builder, Python version,
  dependency failure, and detected start command.
- [x] Obtain the public production URL and remaining app-service settings.
- [x] Configure three Railway services after all three local processes are
  reproducible.
- [x] Provide the public Express URL as `VITE_TRANSIT_API_BASE_URL` in the
  tracked recovery bundle.
- [x] Verify poller hours, timezone, retention, `POLL_ENABLED`, and
  `ADMIN_KILL_SWITCH` in Railway.
- [ ] Finish visual verification of route/vehicle selection, alerts, browser
  console, and the desktop/mobile layouts in production. API health, database
  freshness, selected-vehicle context, history, paths, and stops are verified;
  no active alert was available during the latest check.
- [ ] Deploy and visually verify the sticky NiceGUI/React headers, shared
  light/dark preference, and iframe-based mobile résumé viewer.
- [x] Upload `static/resume.pdf` to `/data/resume.pdf` on the `portfolio`
  volume, set `RESUME_PDF_PATH`, deploy, and verify inline/download behavior.

## Later

- [ ] Replace the sample résumé timeline with confirmed employment and
  education entries.
- [ ] Replace sample project, contact, privacy, and terms content with intended
  portfolio behavior.
- [ ] Decide whether route density/quadrant curation remains a product goal.
- [ ] Revisit Calgary LRT only if live vehicle positions become available.
- [ ] Treat future Toronto TTC subway/train work as a separate feature and
  architecture decision.
- [x] Rewrite the root README after clean startup and deployment commands are
  verified.

## Blocked

- [ ] Verify an active production alert and its selected-vehicle UI when the
  feed next provides one.
- [ ] Confirm which older transit implementation can be deleted — blocked
  until the newer production path's live polling/selection is verified.

## Current recommended next task

Publish the sticky navigation, shared theme, and mobile résumé viewer changes,
then visually smoke-test `/resume` and `/calgary-transit-live/` on desktop and
mobile, including theme persistence and the browser console. Verify an active
alert when the feed next provides one.

Use `docs/NEXT_SESSION_PROMPT.md` as the ready-to-paste handoff prompt.
