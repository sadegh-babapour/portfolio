# Session Log

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
