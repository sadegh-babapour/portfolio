# Change proposal: dagster-orchestration (data platform stage 2, local step)

Status: **approved by the owner, 2026-10-23** (all three approvals below). Branch `feature/dagster-local`, base `main` @ `cc1a431` (#24).
No PR until the local work is complete and reviewed (owner direction).

## Why

Stage 1 (#15) gave us a loader and a dbt project, but someone has to type three commands
to run them, and nobody notices when the Bank's API is down or a dbt test fails. Stage 2
adds an **orchestrator**: it runs the steps in order on a schedule, retries what's worth
retrying, keeps run history, and shows failures in one UI. Dagster was the owner's pick
(2026-10-21) because its "assets" match how dbt thinks: tables, not tasks.

**Local first** (owner, 2026-10-23): it runs on the Mac against PC `portfolio_dev`. The
Railway service is a separate, later proposal.

## What changes

1. **Dagster project** in a new package `orchestration/` (about 3 small files):
   - **Asset `raw/boc_observations`**: calls the existing `pipelines.bank_of_canada.run()`.
     Its key matches the dbt source `raw.boc_observations`, so Dagster draws one lineage
     graph: Valet API → raw → staging → marts.
   - **dbt assets** (`dagster-dbt`): every model and seed in `warehouse/` becomes an asset;
     every dbt test becomes an **asset check**. Downstream of a failed test is skipped.
   - **Freshness check** on `raw/boc_observations` (same 4/7-day rule as `_sources.yml`).
   - **Job + schedule:** load, then `dbt build`; weekdays 18:00 Calgary time, after the
     Bank's end-of-day publication.
   - **Retry policy** on the loader only: 2 retries, 10 minutes apart (network blips).
     dbt failures are not retried: a failed test is a data problem, not a blip.
   - **One run at a time** (a concurrency limit), so a manual run can't overlap the schedule.
2. **Same safety gate as stage 1.** A Dagster resource bootstraps the runtime gate inside
   each run, opens `runtime_db.connect_verified()`, and hands dbt only the approved target
   (reusing `pipelines/run_dbt.dbt_env`). Production mode refuses, as the loader does today.
   **No credentials in Dagster config**: they would show in the UI's launchpad.
3. **Dagster's own storage (run history, logs, schedule state): SQLite files on the Mac** in
   `.dagster_home/` (git-ignored), with telemetry off in `dagster.yaml`. No new database.
4. **Launch:** `make dagster` →
   `ops/dev.py run --expected-db portfolio_dev -- .venv-data/bin/dagster dev -h 127.0.0.1 -p 3000 ...`
   The UI listens on localhost only; it has no login and must never be exposed.
5. **Dependencies** in `requirements-data.txt` / `.venv-data` only (never the web service):
   `dagster==1.13.26`, `dagster-webserver==1.13.26`, `dagster-dbt==0.29.26`, plus explicit
   `SQLAlchemy==2.0.51`, `requests==2.32.3`, `psycopg2-binary==2.9.10` at the app's pins (the
   gate needs them). VERIFIED 2026-10-23: `pip install --dry-run` with the current dbt pins
   resolves cleanly (116 packages, protobuf 6.33.6; nothing installed).
6. **Data CI** (`data` job, same name, still required): installs the new pins,
   `dagster definitions validate`, and one test that materializes the job against the
   throwaway Postgres with the recorded Valet fixture (no network).
7. **Lesson 13** (private): assets vs tasks, schedules, retries, asset checks, lineage, and
   why the orchestrator doesn't hold the passwords.

## Exact DB impact (local step)

- **Target:** PC 10.0.0.2, database `portfolio_dev`, role `postgres`, through the gate only.
- **Reads/writes:** the same as running stage 1 by hand today: upserts into `raw.*`, one
  `raw.load_runs` row per run, dbt rebuilds the `staging` view, seed and `marts` tables.
- **No new database, schema, role or migration.** Nothing in `portfolio` or `transit` is touched.

## Must hold (negative scenarios, each with a test or a recorded manual check)

- **API down / bad answer:** loader asset fails after its retries, `raw.load_runs` says
  failed, no observations committed, dbt assets skipped, failure visible in the UI.
- **dbt test fails:** the asset check is red; downstream marts are not rebuilt from bad data.
- **PC off or gate refuses** (policy missing, wrong DB): the run fails before any connection; nothing written.
- **Mac asleep at 18:00:** that tick is missed; the next run's 30-day lookback fills the gap
  (no gap in `raw` once any run succeeds).
- **Manual run during a scheduled run:** the second waits; never two loads at once.
- **Secrets:** no password in Dagster config, run tags, logs or `.dagster_home/` (grep check).
- **Production mode:** the resource refuses, exactly like `pipelines.bank_of_canada.main`.
- **Deleting `.dagster_home/`:** loses only run history; data unaffected.

## Cost

- **Local:** $0.
- **Railway (later proposal, HYPOTHESIS until measured):** one more service (web UI + daemon),
  likely ~0.5–1 GB RAM, so roughly $5–10/month on top of today's bill.

## Non-goals (this step)

- No Railway service, variables, schemas or read-only site role: that's the next
  proposal, after this works locally.
- **Open for that proposal** (owner, 2026-10-23: "same Postgres, different schema"): the
  existing Railway Postgres either way, no new server. The choice is schemas (`raw`,
  `staging`, `marts`, `dagster`) in the site's database, or separate databases on the same
  server. Schemas fit the code as it is: `/markets` reads `marts.*` through the site's own
  session (`app/markets/service.py:17,30`). Separate databases would need a second
  connection in the site.
- No new data sources (stage 3), no sensors, no partitions, no Dagster+ (paid cloud).
- No change to `/markets` or any site code. Merging this would deploy nothing that runs
  in production (no service starts Dagster), but it still goes through a normal PR.

## Known friction

- Codex is working on Dependabot alerts in `chore/security-alert-review`. If it changes
  `requirements-data.txt`, this branch rebases onto `main` after that merges.
- `.venv-data` grows from ~20 to ~116 packages; the CI `data` job gets about a minute slower (estimate).

## Owner approvals this proposal asks for

1. Dagster's storage as SQLite on the Mac for the local step (no new database). **Approved 2026-10-23.**
2. The three new Dagster dependencies in `.venv-data` only. **Approved 2026-10-23.**
3. Tracking this file in git like stage 1's proposal (one `.gitignore` exception line). **Approved 2026-10-23.**
