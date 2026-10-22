# Change proposal: boc-reporting-pipeline (data platform stage 1)

Status: approved by the owner 2026-10-21; implemented on `feature/boc-reporting-pipeline`. Base: `main` @ `7bb2a37`.

## Why

This is the first stage of the lab's data platform: public finance and energy data → reporting database → dbt → dashboards. It starts with one simple source that needs no key, so the whole flow can be built, tested and explained before scheduling (stage 2), more sources and SCD2 (stage 3), and CDC (stage 4) build on it.

The source is the Bank of Canada Valet API. It is free and needs no key. It provides:
- the policy (target overnight) rate and CORRA;
- 2-, 5- and 10-year Government of Canada bond yields;
- USD/CAD.

Exact series IDs are confirmed against the API during implementation.

## What changes

1. **Loader** (`pipelines/bank_of_canada.py`, Python):
   - Fetches each configured series and upserts it into `raw.boc_observations`, one row per (series, date).
   - Re-running is safe: no duplicate rows (idempotent).
   - Each run re-reads the last 30 days, so values the bank revises are picked up. `--since` backfills history.
   - Series names and descriptions go into `raw.boc_series`.
   - Every run writes one row to `raw.load_runs`: source, start, end, status, rows changed, error.
2. **dbt project** (`warehouse/`, dbt-core 1.12.5, dbt-postgres 1.11.0):
   - Source definitions with a freshness rule.
   - Seed `boc_series_catalog`: our name, category and allowed value range per series.
   - Staging model `stg_boc__observations`: types, names, no blanks.
   - Marts, with the grain written on each:
     - `dim_series`;
     - `fct_rates_daily`: one row per series per date;
     - `mart_canada_rates_daily`: one row per date, with the yield-curve spread (10y − 2y) and USD/CAD.
   - Tests: unique, not null, relationships, accepted ranges.
3. **Same safety gate as the app:**
   - The loader connects through `runtime_db.connect_verified()`.
   - dbt is started through a small wrapper that bootstraps the same gate and hands dbt only the approved target.
   - **No new database target.**
4. **Development storage:** three new schemas, `raw`, `staging` and `marts`, in the already-approved `portfolio_dev` (host 10.0.0.2, role `postgres`).
   - Writes there create and fill only these new schemas. No existing schema or table is touched.
   - Production gets its own reporting Postgres in stage 2, not here.
5. **Data CI:** a GitHub Actions job that:
   - starts a throwaway Postgres;
   - runs the loader on recorded API responses (no network);
   - runs `dbt build` (models and tests);
   - runs the loader's pytest tests.
6. **Dependencies:**
   - `dbt-core` and `dbt-postgres` go in `requirements-data.txt` and a separate `.venv-data`.
   - They are not installed in the web service, to avoid version clashes with the app (for example protobuf).
7. **Lesson** `docs/lessons/06-*.md` (private): a code walkthrough, interview questions and a "you try" exercise.

## Must hold (negative scenarios, each with a test)

- **Run twice:** the second run changes no rows and adds no duplicates.
- **Revised value:** the row is updated, and its `last_changed_at` changes.
- **No value for a day** (holidays, blanks): skipped, not stored as zero.
- **API down or bad response:**
  - the run is recorded as failed with the error;
  - none of that run's observations are committed;
  - the exit code is non-zero.
- **Unknown series ID:** the run fails with that ID named; no partial load.
- **Unapproved target:** the loader or dbt wrapper pointed at any database other than the approved one refuses before connecting.
- **dbt tests:** a duplicate (series, date) or a null rate fails the build.

## Non-goals

- No Railway services, variables, cron or production data.
- No scheduling (stage 2), no dashboard page (stage 2, once a production reporting DB exists), no SCD2 (stage 3), no CDC (stage 4).

## Owner approvals this proposal asks for

1. The two new dependencies, kept out of the web service.
2. Creating the `raw`, `staging` and `marts` schemas in `portfolio_dev`.
