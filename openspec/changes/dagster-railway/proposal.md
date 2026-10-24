# Change proposal: dagster-railway (data platform stage 2, production step)

Status: **approved by the owner, 2026-10-23** (all four approvals below). Branch `feature/dagster-railway`, base `main` @ `ae3f88d` (#27).
PR 1 (code) is next; no Railway or database changes until the owner's steps after it.

## Why

#27 runs the Bank of Canada load and dbt under Dagster, but only on the Mac against PC
`portfolio_dev`. Production has no warehouse, so `/markets` says "not available" and
stays out of the nav. This step runs the same Dagster job on Railway every weekday and
writes the warehouse into the production Postgres. Once that works, `/markets` shows real
data with no site code change (`app/markets/service.py` already reads `marts.*`).

## Facts this design rests on

- **VERIFIED:** `/markets` reads `marts.mart_canada_rates_daily` and `raw.load_runs`
  through the site's own session (`app/markets/service.py:27-42`, `app/contact/database.py`).
  Schemas in the **same database** need no second connection in the site.
- **VERIFIED:** the loader creates `raw` with `CREATE SCHEMA IF NOT EXISTS` (`pipelines/sql/raw_bank_of_canada.sql:4`).
  dbt builds `staging` and `marts` (`warehouse/profiles.yml`). The first production run loads
  from 2015-01-01 (`pipelines/bank_of_canada.py:27,140`), about 17,000 rows.
- **VERIFIED:** today `ApprovedDatabase` refuses production (`orchestration/definitions.py:82`),
  and so does the loader's CLI (`pipelines/bank_of_canada.py:228`).
- **VERIFIED:** production proves itself with Railway's ID variables plus a build
  attestation bound to **its own service ID** (`app/runtime_env.py:151-180,568`). A new
  service needs its own build step that writes the attestation.
- **VERIFIED:** dagster-postgres 0.29.26 has no "schema" setting. It takes a URL or
  host/user/password/db plus optional `params` (`dagster_postgres/utils.py:29-61`). Dagster's
  own tables go wherever the role's `search_path` points.
- **VERIFIED (Mac, 2026-10-23):** memory while idle, with no runs:
  - daemon: 129 MB, plus its code server at 207 MB;
  - webserver: 155 MB, plus its code server at 206 MB;
  - one definitions load (each run starts one): 216 MB peak.
- **VERIFIED (docs.railway.com, 2026-10-23):** Hobby costs $5/month, which includes $5 of usage. RAM is $10 per GB-month, CPU $20 per vCPU-month, volumes $0.15 per GB-month.
- **NOT VERIFIED:**
  - which role the site and the poller use on Railway (probably the default superuser);
  - today's monthly bill;
  - whether `railway ssh` into the Postgres service gives a `psql` prompt (the TCP proxy is off).
  The owner checks these on the PC.
- **Owner direction (2026-10-23):** same Railway Postgres, separate schemas, no new server.
  - This **supersedes** stage 1's line "production gets its own reporting Postgres in stage 2"
    (`openspec/changes/boc-reporting-pipeline/proposal.md:39`).

## What changes

### 1. One new Railway service: `dagster` (decision 1)

**Recommended, option A: the daemon only, with no public web UI.**

- The service runs `dagster-daemon run`. It fires the weekday 18:00 Calgary schedule,
  applies the loader's retries and keeps run history in Postgres.
- It has no domain and no open port, so nothing on the internet can reach it.
- **Failures are sent to the owner by email** (decision 3). Freshness is also public:
  `/markets` already shows the time of the last load.
- To see the UI, the owner runs `make dagster` on the Mac as today, against dev. The
  production UI is option C, later.

| Option | What runs | Est. cost / month | Trade-off |
|---|---|---|---|
| **A (recommended)** | daemon, always on | ≈ $3.5–4.5 (0.34 GB idle, plus short runs) | Real Dagster scheduling, retries and sensors; no production UI |
| B | Railway cron starts `dagster job execute` once a day | < $0.10 | Cheapest, but Railway's cron replaces Dagster's scheduler: no sensors, so no failure email from Dagster |
| C | A + the web UI behind Cloudflare Access (owner-only Google login) | ≈ $5.5–7 | A production UI, but the service must also check Cloudflare's token itself, or anyone who calls Railway's edge directly skips the login. Its own proposal, later |

- Costs are HYPOTHESIS until measured on Railway. They use Mac memory figures, which
  roughly match Linux, and Railway's prices. Each costs on top of today's bill.
- A public UI with no login is **not** offered. Dagster OSS has no login, and anyone
  with the UI can start runs that write to production.

### 2. Its own least-privilege database role (decision 2)

A new login role, `bizqlab_dagster`, that is **not a superuser** and can do the following:

- own the schemas `raw`, `staging`, `marts` and `dagster` (run history), pre-created;
- `CREATE` on the database, because `CREATE SCHEMA IF NOT EXISTS` needs it even when the schema exists (HYPOTHESIS, to be proven in CI);
- nothing in `portfolio` or `transit`: no `USAGE`, so it can't read users, sessions or contact messages;
- `ALTER ROLE ... SET search_path = dagster`, so Dagster's own tables land in `dagster`.

It is created by **one reviewed SQL file** (`ops/sql/railway_dagster_role.sql`, no
password in it), run once by the owner on the PC.

- The password is set at a `\password` prompt and never typed into a file or a command line.
- It is stored only as a sealed Railway variable on the `dagster` service.
- That service's `DATABASE_URL` is assembled from Railway references (private host, port, database) plus that variable. It is **not** the site's `DATABASE_URL`.

**Why it matters:** if the Dagster service or a dependency is compromised, it can damage
only the rebuildable warehouse, never the site's users or sessions.

### 3. The gate learns a production branch

`ApprovedDatabase` gets a production branch:

- In an attested production run, it connects with the service's `DATABASE_URL`.
- Before anything else, it asks the server who it is connected as. It **refuses** if:
  - the user is not `bizqlab_dagster`;
  - the role is a superuser;
  - the role can use the `portfolio` or `transit` schema.
- This catches the most likely mistake: someone pastes the site's superuser URL.
- dbt gets the same target as `DBT_*` settings, as in development.
- Development behaviour is unchanged.

### 4. Dagster's storage in Postgres

- An `orchestration/dagster.production.yaml` uses dagster-postgres. Its connection comes from the environment, so the file holds no values.
- Telemetry stays off, and `max_concurrent_runs: 1` as today.
- Run-history retention: schedule ticks are kept for 30 days. Event logs are small, a few MB a year at one run a day.

### 5. Build and start

- An **`orchestration/Dockerfile`**:
  - Python 3.13 slim; installs only `requirements-data.txt` plus `dagster-postgres`;
  - (as built) the dbt manifest is parsed when the definitions load, as on the Mac; no build-time parse;
  - writes the build attestation.
- Why a Dockerfile and not Railway's auto-detection: the auto-builder would install the root `requirements.txt`, the web app's environment. dbt needs protobuf 6 and the app pins 5.
- HYPOTHESIS: Railway passes `RAILWAY_SERVICE_ID` and the environment and commit IDs to a Docker build when they are declared as `ARG`s. Checked on the first deploy; if it fails, the attestation is written at start instead (design note in the PR).
- Start: `python -m orchestration.production`. It bootstraps the gate and checks the role, then becomes `dagster-daemon run`. **(Added while building:** Dagster's own storage connects with `DATABASE_URL` before any run, so a wrong URL must stop the service before Dagster creates tables.) One replica, never more: two daemons fire every schedule twice.
- The schedule and both alert sensors are **on by default only when `BIZQLAB_RUNTIME=production`**, since there is no UI there to turn them on. On the Mac they stay off.

### 6. Failure email (decision 3)

- A Dagster `run_failure_sensor` sends one short email per failed run (job name, step, time and a link-free summary) through **Resend**, which the contact form already uses.
- It uses a **separate send-only Resend key**, so the Dagster service never holds the site's key.
- No email for success. **(Changed while building:)** only checks that fail at ERROR severity send an email, so the freshness check emails at 7 days, not 4. At 4–6 days it only warns; a long weekend reaches 4 and would send a false alarm.

### 7. Tests and CI

- **CI builds the Docker image** and starts it twice: as the CI superuser (it must refuse with `wrong_role`) and as `bizqlab_dagster` (the daemon starts; Dagster's tables land in `dagster`, none in `public`; the random password never appears in the log).
- **CI runs the same SQL file** against its throwaway Postgres.
- It then runs the whole job **as `bizqlab_dagster`** with `dagster.production.yaml` storage, and proves:
  - the job succeeds;
  - Dagster's tables land in `dagster`;
  - that role gets "permission denied" on a `portfolio` table.
- Gate tests (no database):
  - the site's superuser URL is refused;
  - an unattested Railway context is refused;
  - development is unchanged.
- The sensor is tested with a fake sender. No real email in tests.

## Rollout (two PRs, owner steps between them)

1. **PR 1: code.**
   - It contains points 3–7 and lesson 14.
   - **Merging deploys nothing that runs**, because the `dagster` service doesn't exist yet.
2. **Owner, on the PC** (a checklist in the PR):
   - run the role SQL;
   - create the `dagster` service: GitHub repo, Dockerfile path, no domain, 1 replica;
   - set its variables (references plus the two sealed secrets);
   - deploy; the first run is the next weekday 18:00 tick (the schedule is on in production). No one-shot flag.
3. **Check, public only:**
   - `/markets` shows data;
   - `raw.load_runs` (through the page's "last load") is recent.
4. **PR 2: small.**
   - Put `/markets` in the nav and remove its "production has no warehouse" text.
   - Separate, so the page goes public only after the data is proven.

## Exact DB impact (production, after the owner's steps)

- **Target:** Railway Postgres, the existing database. New role `bizqlab_dagster` and schemas `raw`, `staging`, `marts`, `dagster`.
- **Writes:** about 17,000 rows on the first run, then about 60–130 a day; dbt rebuilds 1 view and 4 tables of a few thousand rows each. Dagster run history is a few hundred rows per run.
- **Untouched:** `portfolio`, `transit`, the site's role, Alembic. No migration in this change.
- **Backups:** the new schemas are in the same Railway Postgres, so its existing backup (if any) covers them. Everything except run history can be rebuilt from the Bank's API.

## Must hold (negative scenarios, each with a test or a recorded check)

- **Wrong credentials pasted:** the `dagster` service started with the site's superuser URL refuses at the first run, before any write.
- **Role escape:** as `bizqlab_dagster`, `select` on `portfolio.users` fails with permission denied (CI).
- **No attestation, or an attestation from another service:** the gate refuses; nothing connects.
- **Bank API down:** retries, then the run fails. One email; `/markets` keeps the last good data.
- **dbt test fails:** the mart `/markets` reads keeps its last good data (the #27 behaviour). One email.
- **Two daemons by mistake (replicas = 2):** HYPOTHESIS: `max_concurrent_runs: 1` queues the duplicate, which then repeats an idempotent load. The checklist pins 1 replica.
- **Service down for days:** no runs, so no failure email (a known gap; see Non-goals). `/markets` shows the old "last load" date, and the dbt freshness test warns at the next run.
- **Rollback:**
  - stop or delete the `dagster` service;
  - the warehouse schemas can stay (the page keeps showing the last data) or be dropped by a reviewed script;
  - no site change to undo. Git revert of PR 1 is harmless.
- **Secrets:** no password in the repo, the Docker image, Dagster config, run logs or emails (CI grep, as in #27).

## Non-goals

- The production web UI (option C), sensors beyond failure email, new data sources (stage 3).
- A **read-only role for the site:** the site's role is unchanged here. That's a separate small proposal; it means changing the site's `DATABASE_URL`, which is riskier than anything in this one.
- A "dead man's switch" (an alert when no run happened at all): it needs something outside the `dagster` service. Noted for later.
- No change to `portfolio`, `transit`, the poller or the API.

## Cost summary

- Option A: about $3.5–4.5 a month on top of today's bill (HYPOTHESIS).
- Resend: within its free tier, a handful of emails a month at most.
- The first week's Railway usage page gives the real figure, recorded in the receipt.

## Owner approvals this proposal asks for (one at a time)

1. **Service shape:** option A (daemon only, no public UI). **Approved 2026-10-23.**
2. **Database:** the `bizqlab_dagster` role and four schemas in the existing database, created by the reviewed SQL file that you run once on the PC. **Approved 2026-10-23.** How to reach the database from the PC (the proxy is off) goes in PR 1's checklist.
3. **Failure email** through Resend with a separate send-only key. **Approved 2026-10-23.**
4. **Tracking this file in git** (one `.gitignore` exception line, as for #27's proposal). **Approved 2026-10-23.**
