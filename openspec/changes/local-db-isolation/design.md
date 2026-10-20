# Design: local-db-isolation

Status: design revision 3, reconciled with the approved simplifications. Implemented and
independently QA'd offline on `feature/001-mac-parity`; rollout stages S1–S5 (`design.md` §12)
are pending, each with separate owner approval.
- Owner decisions: A1 (build attestation), B1 (root-owned policy), C1 (strict profile
  grammar) and D (synthetic tests).
- Production facts in §1.2 were reported by the operator from the hosting dashboard.
- An earlier draft's legacy-production stage is **removed**.
- **Reconciled 2026-10-16** with two simplifications approved in the technical
  assessment (wording maintenance, not a new design decision):
  - the build marker is one fixed file directly inside each build root (§3.1, §3.4);
  - policy ancestor directories are fingerprinted on identity, type, owner, group,
    mode and writability only (§8.1, §8.2).

  The module layout (§9) also reflects the approved split into small modules, and the
  browser API target is in scope. The rollout (§9, §11–§17) is one bounded feature
  with no mandatory two-PR split, and an ephemeral preview (web and transit-api
  only, synthetic data, no automatic poller or SEC writers) in place of a standing
  staging environment; the prerequisite ordering and owner approvals are unchanged.
  §1 remains the Rev 3 snapshot of the pre-M1 code.

Evidence base: SHA `b363024`. Installed library versions: python-dotenv 1.1.1,
SQLAlchemy 2.0.51, psycopg2-binary 2.9.10, pg 8.20.0, pg-pool 3.13.0.

Labels: **VERIFIED** (source or command), **OWNER-REPORTED**, **NOT VERIFIED**.

## 1. Current state

### 1.1 Code (VERIFIED)

| Consumer | DB source today | Gap |
|---|---|---|
| NiceGUI (`app/main.py:12`, `app/contact/database.py:11-16`, `lru_cache`) | `DATABASE_URL` via implicit `load_dotenv()` | ancestor `.env` can supply the URL; the cached engine bypasses later checks |
| Alembic (`migrations/env.py:17,23-25,50`) | `DATABASE_URL` via implicit `load_dotenv()` | `CREATE SCHEMA` runs against any target |
| SEC writers (`scripts/ingest_sec_company.py:41`, `scripts/run_sec_research_refresh.py:43-99`) | `DATABASE_URL` | no check |
| Poller (`poller/poll_calgary_gtfs_rt_current.py:422-476`) | `--database-url`/`DATABASE_URL`, else `PG*` | URL silently wins; DDL on start; one long-lived connection |
| Static bootstrap (`scripts/bootstrap_transit_db.py:39-49`) | same as poller | TRUNCATE |
| Express (`backend/transit_api/db/pool.js:3-9`; 14 `pool.query` call sites, no `pool.connect`) | `PG*`; pg falls back to `process.env` | no check |
| Launcher (`ops/dev.py:34-50`, untracked) | `.env.local` with interpolation **on** | re-imports inherited values |
| Tests (`test/test_accepted_boundaries.py:10`, `test/test_financial_research_presentation.py:6`) | via `import app.main` | test process inherits `.env` |

### 1.2 Production (OWNER-REPORTED)

| Service | Build root | Start | Pre-deploy | Schedule | DB config |
|---|---|---|---|---|---|
| `portfolio` | repo root | automatic (effective command NOT VERIFIED; `Procfile`: `python -m app.main`) | `alembic upgrade head` | — | `DATABASE_URL` |
| `transit-api` | `/backend/transit_api` | `npm start` (Node 22.23.3) | — | — | `PG*` |
| `transit-poller` | repo root | `python -m poller.poll_calgary_gtfs_rt_current` | — | — | `PG*` |
| `sec-research-refresh` | repo root | `python -m scripts.run_sec_research_refresh --write --trigger scheduled --max-attempts 3` | — | daily (external cron) | `DATABASE_URL` |

- All four use Railpack automatic builds from `main`, so **merge = deploy**.
- No `BIZQLAB_RUNTIME` is set today.
- `railway run` injects service variables locally.
- The SEC refresh runs on an external daily schedule.

### 1.3 Library facts (VERIFIED)

- **L1.** SQLAlchemy's dialect `on_connect` and `first_connect`/`initialize` are pool
  `connect` listeners registered inside `create_engine` (`engine/create.py:747-789`).
- **L2.** pg-pool 3.13.0 awaits `options.onConnect` before handing out a new client.
  On rejection it removes the client, calls `client.end()` and fails the acquire
  (`pg-pool/index.js:287-301`).
- **L3.** pg's `val()` falls back to `process.env['PG'+KEY]` for any falsy config
  field, including `options` (PGOPTIONS). When `ssl` is undefined it reads
  `PGSSLMODE` (`pg/lib/connection-parameters.js:9-26,85`), and `PGCONNECT_TIMEOUT`
  separately (`:115`).
- **L4.** libpq reads many `PG*` environment variables at connect time and accepts
  multi-host, `hostaddr`, `service` and `options`.
- **L5.** SQLAlchemy renders the URL `database` component unescaped
  (`db?host=evil.example` redirects libpq). `URL.create` accepts positional
  arguments (a review note claiming keyword-only arguments was disputed); keywords are used anyway.
- **L6.** `Engine.dispose()` closes only *checked-in* connections. Checked-out
  connections stay open and are merely disassociated (`engine/base.py:3174-3222`).
  `PoolEvents.checkout` fires on every checkout, including reuse of idle pooled
  connections. `ConnectionEvents.before_cursor_execute` fires before every
  statement on any `Connection`/`Session`/ORM path.
- **L7.** Python `raise X from None` sets `__suppress_context__` but **keeps**
  `__context__` (CONFIRMED in review).
- **L8.** The SEC scripts run only as `python -m scripts.<name>`.
  `python scripts/bootstrap_transit_db.py` works today only because it imports
  nothing from `app`. `alembic.ini` sets `prepend_sys_path = .`.

## 2. Invariants

- **I1 Separate inputs.** Mode comes from inherited environment, build attestation
  and workstation indicators. Credentials come only from the strict profile.
  Approval comes only from the root-owned policy.
- **I2 One development identity**, or failure before connecting.
- **I3 No silent winner.**
- **I4 Verify before use.** On every new development connection the identity query
  is the first statement.
- **I5 Production by positive evidence only.** No combination of absent variables
  or files authorizes production. After the gate, production connection parameters
  equal today's.
- **I6 No secret egress**, including in exception chains.
- **I7 Fail closed with defined revocation boundaries** (§8).

## 3. Mode selection and production authorization

### 3.1 Inputs (identical in Python and Node)

| Input | Source |
|---|---|
| `BIZQLAB_RUNTIME` | inherited environment only (reserved in the profile): `production`, `development`, or unset |
| Markers M = {`RAILWAY_PROJECT_ID`, `RAILWAY_ENVIRONMENT_ID`, `RAILWAY_SERVICE_ID`} | inherited: **complete** (all non-empty), **partial**, or **absent** |
| Attestation A | `<build_root>/.bizqlab-build-attestation.json`, one file directly in the build root (§3.4): **valid**, **invalid:\<code\>**, or **absent** |
| Workstation indicators W | existence only (`lstat`): W1 = the root policy path exists; W2 = `<repo_root>/.env.local` exists |

### 3.2 Decision table (ordered; the first match wins; no legacy row)

| # | Condition | Result |
|---|---|---|
| 1 | `BIZQLAB_RUNTIME` set and not exactly `production` or `development` | ERROR invalid mode |
| 2 | M partial | ERROR incomplete Railway context |
| 3 | M complete and W present | ERROR Railway context on a workstation |
| 4 | `BIZQLAB_RUNTIME=production` and M complete and A valid | **production** |
| 5 | `BIZQLAB_RUNTIME=production` otherwise | ERROR production not attested |
| 6 | `BIZQLAB_RUNTIME` unset or `development`, and M complete | ERROR Railway context without attested production mode |
| 7 | `BIZQLAB_RUNTIME` unset or `development`, and M absent | **development** (it still requires a valid profile and policy, §4) |

Expected results for named contexts (normative; drives V4):

| Context | Row | Result |
|---|---|---|
| Plain local run, no markers | 7 | development; then fails closed if the profile or policy is missing or invalid |
| `railway run` on a development workstation (policy and/or `.env.local` present), any mode value | 3 | ERROR |
| `railway run` on a fresh machine (no W), mode unset | 6 | ERROR |
| `railway run` on a fresh machine (no W), mode `production` injected, no attestation | 5 | ERROR |
| `railway run` on a fresh machine (no W), mode `production`, **deliberately forged** valid attestation | 4 | production (residual R-F, §3.5) |
| Railway service before rollout (mode unset) | 6 | ERROR, which is why strict code ships only after S3 (§12) |
| Railway service after S3, attestation valid | 4 | production |
| Railway service with mode unset after enforcement | 6 | ERROR; rollback is by artifact, not by variable (§13) |

### 3.3 No transitional exception

The Rev 2 legacy stage is deleted, and no code path connects without either
development approval or attested production. Production compatibility comes from
**ordering the rollout** (§12): attestation and explicit mode are established and
verified while the current code is still deployed, and the strict code is merged
last.

### 3.4 Build attestation (A1)

**Generators** (tracked, inert until wired; each hardcodes its `build_root`):

| Generator | Build root | `build_root` value |
|---|---|---|
| `ops/write_build_attestation.py` | repo root (Python services) | `"."` |
| `backend/transit_api/scripts/writeBuildAttestation.js` | `backend/transit_api` | `"backend/transit_api"` |

Standalone read-only checkers `ops/check_build_attestation.py` and
`backend/transit_api/scripts/checkBuildAttestation.js` print a non-secret
classification. They connect to nothing; they're used in the S2 preview and S3.

**Schema** (exact keys, types validated):

```json
{"schema": 1, "kind": "bizqlab-railway-build", "build_root": "<. | backend/transit_api>",
 "railway_service_id": "<string>", "railway_environment_id": "<string>",
 "git_commit": "<40-hex string or null>", "generated_at": "<UTC ISO-8601>"}
```

**Generator rules.**
- `railway_service_id` and `railway_environment_id` are **required** at build:
  non-empty and matching `^[A-Za-z0-9-]{1,64}$`. If either is missing, the build
  fails.
- `git_commit` comes from `RAILWAY_GIT_COMMIT_SHA` if present at build, else null.
- Existing output: kept unchanged only if it records the same build (every field
  except `generated_at`, which a rebuild cannot reproduce); otherwise the build fails.
  A symlink or non-regular file at the marker path fails the build.
- Output is created exclusively (`O_EXCL`, no-follow) with mode 0444, then read back
  through the runtime reader; it holds no secrets.
- The generator refuses on a workstation (W1 or W2 present).

**Runtime validation** (valid only if all hold):
- The marker is the single file `.bizqlab-build-attestation.json` directly inside
  the build root; there is no subdirectory and no legacy fallback (the retired
  `.bizqlab/build-attestation.json` is never read). Python opens the root as a
  directory and the file relative to that descriptor; both languages open the file
  with no-follow, then `fstat`/read on the same descriptor: a regular file of at most
  1 KiB.
- Strict JSON with exact keys and types.
- `schema == 1`; `kind` matches; `build_root` equals the consumer's constant.
- `railway_service_id == RAILWAY_SERVICE_ID` and
  `railway_environment_id == RAILWAY_ENVIRONMENT_ID`.
- If `git_commit` is non-null, `RAILWAY_GIT_COMMIT_SHA` must be present and equal.
  If `git_commit` is null, the runtime variable is ignored.

**Guarantee.**
- Proves: the process runs from an artifact built for **this service in this
  environment**, which rejects cross-service and cross-environment reuse. A
  commit-bound attestation also rejects stale artifacts.
- Does not prove: the artifact can't be forged deliberately (R-F), or that the
  trusted build root itself was not deliberately replaced. The build root is an
  explicit trust anchor; the marker guards against accidental use.

### 3.5 Residuals

- **R-F.** Someone holding a Railway token on a machine without W who *deliberately
  writes* a matching attestation file can obtain production mode. This is
  deliberate, not silent, and requires production credentials already. Accepted as
  outside the threat model; owner acceptance requested (§17).
- **R-W.** Deleting W on a workstation to evade row 3 is also deliberate. Row 6 or 5
  still refuses unless R-F is also performed.

## 4. Development inputs

### 4.1 Strict profile `<repo_root>/.env.local` (C1)

- **Path.** Derived from module location. Node additionally confirms the repo root
  by checking that `scripts/bootstrap_transit_db.py` exists.
- **Read.** Open with no-follow, `fstat` on the same descriptor (regular file, at
  most 64 KiB), then read from that descriptor. There is no TOCTOU between the
  check and the read.
- **Grammar** (identical in Python and Node; no python-dotenv):

| Element | Rule |
|---|---|
| Bytes | valid UTF-8 (invalid sequences are an error); no BOM; CRLF → LF; a lone CR is an error; lines at most 4096 bytes |
| Blank | empty, or spaces and tabs only |
| Comment | optional spaces or tabs, then `#` |
| Assignment | `KEY=VALUE` at column 0; `KEY` matches `[A-Z][A-Z0-9_]*`; no `export`; no spaces around `=` |
| Quoted value | first and last characters are the same `"` or `'`, and the inner text contains no instance of that quote. The inner text is verbatim, and **may contain ` #`** |
| Unquoted value | verbatim; no leading or trailing whitespace; **must not contain ` #`** (ambiguous with an inline comment); must not start or end with a quote character |
| All values | no `${`; no NUL or control characters other than tab; no multiline values |
| Keys | duplicates are an error |

Errors report line number and key name only. The fixture
`test/fixtures/profile_grammar_cases.json` includes quoted and unquoted ` #`, mixed
quotes, empty quoted values, invalid UTF-8 and byte-limit cases.

- **Key classes.**
  - Required DB keys: `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`,
    **`PGSSLMODE`**.
  - Optional DB keys: `PGCONNECT_TIMEOUT`, `PGAPPNAME`.
  - Any other `PG*` is rejected.
  - Reserved, rejected **if present at all, even empty**: `DATABASE_URL`,
    `BIZQLAB_*`, `RAILWAY_*`, process-control keys.
  - Non-DB keys must be on the allowlist and are applied only where unset, after the
    mode and approval decisions.

- **Option values and their Python/Node mapping** (explicit in both; neither
  falls back to the environment):

| Key | Allowed | Python (psycopg2 keyword) | Node (pg config) |
|---|---|---|---|
| `PGSSLMODE` | `disable`, `require` | `sslmode=` the same value | `ssl: false` / `ssl: {rejectUnauthorized: false}` |
| `PGCONNECT_TIMEOUT` | integer 1–60; default 10 | `connect_timeout=` | `connectionTimeoutMillis = s*1000` |
| `PGAPPNAME` | `[A-Za-z0-9_.-]{1,63}`; default `bizqlab-dev-<purpose>` | `application_name=` | `application_name` |

`verify-full` is excluded because the CA stores differ between libpq and Node, so
parity can't be guaranteed (backlog). Today's profile lacks `PGSSLMODE`, so the
owner adds one line (names-only check).

### 4.2 Root-owned approval policy (B1)

- **Path.**
  - macOS: `/Library/Application Support/Bizqlab/db-policy.json`.
  - Linux (future): `/etc/bizqlab/db-policy.json`.
  - Other platforms: refused.
  - Fixed: no environment override. Tests inject both the path and the stat/access
    provider.
- **Checks** (every read and every revocation check):
  - `realpath == path`.
  - The file and **every ancestor directory** have uid 0 and `mode & 0o022 == 0`,
    **and** `access(W_OK)` is false for the current user. This catches macOS ACL
    grants that mode bits don't show.
  - The file is regular, at most 4 KiB, opened with no-follow and read through
    `fstat`.
  - Exact schema; no `password` key.
- **Schema** (unchanged): `development_target` = {`host`, `port`, `database`,
  `role`, `server_addresses`, `server_port`}.
- **Threat model.**
  - It protects against same-user, non-root processes, including AI agents, IDE
    integrations and scripts.
  - It does not protect against root or `sudo`.
  - Synthetic tests prove the checks. Only owner-approved metadata inspection of the
    real installed file proves the deployment (§16).

### 4.3 Components (unchanged from Rev 2)

- host: an IP literal or RFC 1123 `[a-z0-9-.]` hostname; no `? # / @ % ,`,
  whitespace, public IP, or Railway suffix.
- port: digits only, 1–65535, no leading zero.
- database and role: `[A-Za-z0-9_.-]{1,63}`; database not in the reserved list.
- password: 1–1024 characters, no NUL.
- Profile `PG*` must equal the policy target.

### 4.4 Inherited environment (development)

- Core and optional `PG*` must be absent or equal to the profile value (or to the
  default, for optional keys).
- Every other `PG*` must be absent. This covers pg's `PGOPTIONS` and `PGSSL*`
  fallbacks (L3) and libpq's (L4).
- `DATABASE_URL` must be absent or component-equal to the composed URL.
- CLI DB flags must be absent or equal.
- Alembic `sqlalchemy.url` and `-x` overrides must be unused.

## 5. Connection construction

**Development.**
- psycopg2: keyword arguments, including `sslmode`, `connect_timeout` and
  `application_name`, plus `connection_factory=GuardedConnection` (§8).
- SQLAlchemy: a `URL.create(drivername=..., ...)` object plus `creator=`.
- Exported `DATABASE_URL`: double round-trip validated.
- Node: an explicit-field pool, with every field from §4.1 set explicitly.

**Production.** Unchanged after the gate passes.

## 6. Identity verification and sanitization

**Query.**
`SELECT current_database(), current_user, host(inet_server_addr()), inet_server_port()`.

**Pass conditions.** Database and role equal the policy; the address is non-NULL and
its normalized form is in `server_addresses`; the port equals `server_port`.

**Ordering** (first statement after the driver handshake):

| Consumer | Hook | Success cleanup | Failure |
|---|---|---|---|
| `connect_verified()` | between connect and return | `rollback()` | `close()`; sanitized error; revoke |
| SQLAlchemy engine | `creator=`, before all pool `connect` listeners (L1); re-runs on recycle and pre-ping reconnects | same | no pool record; checked-out count 0 |
| Alembic online | `NullPool` + `creator`; before `CREATE SCHEMA` (`migrations/env.py:50`) and the version table | same | nothing executed |
| Poller / bootstrap / launcher | `connect_verified()` | same | exit non-zero |
| Express | `onConnect` on **every** new client (L2); startup probe before `listen`; pg-pool ≥ 3.13.0 | — | the client is removed and ended, the query rejects unexecuted, revoke, `pool.end()`, exit non-zero |

**Sanitization contract (corrected for L7).**
- At each connect, identity and driver boundary, Python catches the driver
  exception **without binding it** and records only a classification code and the
  SQLSTATE. It then raises `RuntimeConnectError(code, redacted_target)` **after**
  the `except` block, so `__cause__` and `__context__` are both `None` and the
  original exception is not referenced.
- Node constructs a new `Error` with no `cause` and attaches nothing from the
  original.
- Node's pool and client `'error'` events (async errors on idle clients) are
  handled by a sanitized logger that records class and code only.
- Tests assert: `__cause__ is None`, `__context__ is None`, formatted-traceback text
  is clean, logs are clean, and `repr` is masked.

## 7. Entry points (verified invocation forms)

| Entry point | Development | Production (row 4) |
|---|---|---|
| `python -m app.main` (portfolio start; effective command verified in the S2 preview) | no `load_dotenv`; `bootstrap_runtime("web")` in the run block, before `ui.run` | gate evaluated in the run block before `ui.run`; a refusal exits before serving |
| Imported ASGI (`uvicorn app.main:app`) | DB access raises "runtime not bootstrapped" | gate evaluated lazily at the first `get_engine()`; a refusal raises |
| `alembic upgrade head` (portfolio pre-deploy) | bootstrap; verified engine | gate before `CREATE SCHEMA` |
| SEC cron command and `ingest_sec_company --write` | bootstrap before `EdgarClient` | gate before any network or DB access |
| Poller | bootstrap before parser; flag conflicts; `connect_verified` | gate, then today's precedence |
| `python scripts/bootstrap_transit_db.py` and the `-m` form | `__main__`-only root insertion | gate |
| `ops/dev.py check / run` | thin CLI | refused |
| `npm start` | `verifyRuntime()`, profile (C1), policy, explicit pool, guarded query proxy, probe | gate before Pool construction, then today's pool config |

## 8. Lifecycle and revocation boundaries (development; both languages; raw drivers)

### 8.1 State

- Two-phase initialization: phase 1 is pure validation; phase 2 commits under a lock.
- `RuntimeState` is immutable and has a status: `active` or `revoked` (terminal).
- **Committed fingerprint:**
  - the mode, target and password digest;
  - the process DB-environment snapshot: the presence and value of `DATABASE_URL`
    and every `PG*`;
  - the security metadata of the profile and the policy file:
    `(dev, ino, mode, uid, gid, size, mtime_ns, ctime_ns)`, existence, and the
    `access(W_OK)` result;
  - for each policy ancestor directory: `(dev, ino, mode including type, uid, gid)`,
    existence, and the `access(W_OK)` result. Size and times are excluded because
    they change whenever an unrelated sibling is created;
  - the content digests of the profile and policy.

### 8.2 `assert_usable()` (Python) / `assertUsable()` (Node)

Fails, and **revokes**, if:
- the status is not active; or
- the environment snapshot differs; or
- any tracked path's security metadata differs: chmod, chown, an ACL change (via
  `ctime` or `access` for the profile and policy; via `access` for ancestors),
  symlink replacement, directory replacement, or deletion. A metadata change revokes
  even when the content digest is unchanged. Creating an unrelated entry inside an
  ancestor directory does not revoke.

The content digest is recomputed only when metadata changes, and any change revokes.

### 8.3 Boundaries where `assert_usable()` runs

| Boundary | Python, SQLAlchemy | Python, raw psycopg2 | Node |
|---|---|---|---|
| New physical connection | `creator` (plus identity) | `connect_verified` (plus identity) | `onConnect` (plus identity) |
| Checkout or reuse of an idle pooled connection | `PoolEvents.checkout`; failure raises a non-retryable `RuntimeRevokedError` | n/a (no pool) | guarded `pool.query` proxy (the only call path; §1.1) |
| **Every statement**, including on retained Engine/Connection/Session handles and long-lived connections | `ConnectionEvents.before_cursor_execute` | `GuardedConnection.cursor()` always returns a `GuardedCursor`; `execute`, `executemany`, `callproc`, `copy_expert`, `copy_from` and `copy_to` check first; a non-guarded `cursor_factory` is rejected | the guarded `query` wrapper is installed on each client in `onConnect`, and on the pool proxy |
| Commit | `ConnectionEvents.commit`: raises if revoked, before `do_commit` (hook ordering verified in a Batch 2 test) | `GuardedConnection.commit()` raises if revoked | n/a (no transactions in the transit API) |
| Rollback and close | always allowed | always allowed | always allowed |
| Pool checkin | `PoolEvents.checkin`: if revoked, invalidate (close) | n/a | n/a |
| Entry calls (`get_engine`, `session_scope`, `connect_verified`) | checked on every call, outside any cache | checked | `verifyRuntime` (once) |

### 8.4 Revocation semantics (normative)

- **Triggers:**
  - any `assert_usable()` failure;
  - an identity mismatch on a new connection;
  - **any** `bootstrap_runtime()` call after commit that is not fingerprint-identical,
    including a call that **fails validation**.
- **Effects:**
  - The status becomes revoked.
  - `engine.dispose()` closes checked-in connections.
  - Retained checked-out handles are **not** closed by `dispose()` (L6), but their
    next statement or commit raises (§8.3), and checkin invalidates them.
  - Node calls `pool.end()` and exits non-zero.
- **In-flight work.** A statement already sent to the server completes, and its
  result may be read. No further statement and no commit are permitted; rollback
  and close are permitted. Uncommitted work is therefore never committed after
  revocation.
- **Initial bootstrap failure:** nothing is committed (environment byte-identical, no
  state) and nothing is cached; a later call re-runs everything.
- **Children** re-bootstrap from files and accept inherited values only if equal.
  The NiceGUI/uvicorn reload worker re-bootstraps.
- **Tests:** `_reset_for_tests()` disposes engines, clears state and caches, and
  restores the environment snapshot. It is used via `addCleanup`.

### 8.5 Cost

Each statement costs a few `lstat`/`access` calls (profile, policy and about four
ancestors) plus an environment snapshot compare. This is accepted because it applies
in **development only**; production has no per-statement checks.

## 9. Files proposed for modification

Delivered as one bounded feature (§12). The files are grouped for review only; a
separate merge of the inert tooling is optional, not required. Strict enforcement reaches production only after the generators are in the deployed code, wired into each production build and verified, and explicit mode is set, all while the current code is still serving (§12).

**Attestation tooling** (inert until a build calls it; no runtime behavior change):
- `ops/write_build_attestation.py`, `ops/check_build_attestation.py`
- `backend/transit_api/scripts/writeBuildAttestation.js`,
  `backend/transit_api/scripts/checkBuildAttestation.js`
- `.gitignore`: `/.bizqlab-build-attestation.json`, `/backend/transit_api/.bizqlab-build-attestation.json`
- tests for the generators and checkers, plus `test/fixtures/attestation_cases.json`

**Strict isolation** (everything else):

| File | Change |
|---|---|
| `app/runtime_env.py` **(new)** | mode table, attestation reader, strict parser, policy loader, validators, resolver, composition (pure; no state, no connections) |
| `app/runtime_state.py` **(new)** | state/fingerprint/revocation, `bootstrap_runtime`, `bootstrap_entry_point`, `assert_usable`, `_reset_for_tests` |
| `app/runtime_db.py` **(new)** | `connect_verified`, identity verification, `GuardedConnection`/`GuardedCursor`, SQLAlchemy engine and event wiring, sanitized connect errors |
| `app/main.py`, `app/contact/database.py`, `migrations/env.py` | per §7 and §8 |
| `scripts/ingest_sec_company.py`, `scripts/run_sec_research_refresh.py`, `poller/poll_calgary_gtfs_rt_current.py`, `scripts/bootstrap_transit_db.py` | per §7 |
| `backend/transit_api/config/runtimeEnv.js` **(new)**, `config/runtimeState.js` **(new)**, `db/pool.js`, `server.js` | resolver; state, identity and guarded pool; per §6–§8; Node 22 APIs only |
| `frontend/src/apiConfig.js`, `frontend/vite.config.js`, `frontend/package.json`, `frontend/test/apiConfig.test.js`; `ops/check_frontend_bundle.py`, `ops/check_preview_env.py` | explicit browser API target per build mode, no production default; preview bundle and preview environment checks |
| `backend/transit_api/package.json` | `test` script covers all of `test/`; no `build` script |
| `ops/dev.py` (→ tracked), `ops/db-policy.example.json` **(new)** | launcher; placeholders |
| `test/fixtures/{runtime_mode,profile_grammar,validation,policy}_cases.json` **(new)** | shared fixtures |
| `test/run_isolated.py`, `test/shims/sitecustomize.py`, `backend/transit_api/test/shims/isolate.js` **(new)** | isolation and shims |
| `test/test_runtime_env.py`, `test/test_lifecycle.py`, `test/test_entrypoints.py`, `test/test_build_attestation.py`, `test/test_frontend_bundle.py`, `test/test_preview_env.py`, `test/shims/entrypoint_harness.py`; `backend/transit_api/test/{runtimeEnv,runtimeState,startup,buildAttestation}.test.js`, `backend/transit_api/test/helpers/runtimeFakes.js` **(new)** | tests (exact entry commands run as subprocesses behind the shims) |
| `.github/workflows/checks.yml` **(new)** | offline CI: isolated Python suite, transit API check/tests, frontend tests, lint and builds; no secrets or deployment |
| `.env.example`, `README.md` | template (`DATABASE_URL` removed; `PGSSLMODE` added) and local sequence |
| `.gitignore` | four OpenSpec file negations and two marker ignores (§11) |

Not in M1: `railpack.json`, Railway settings, migrations, frontend features beyond
the explicit API target, the config modules, SQL files, `.env.local` and private
working notes.

## 10. Test strategy (D)

- Shared fixtures for mode, grammar, validation, attestation and policy; Python and
  Node must agree on every case.
- `test/run_isolated.py` installs the `psycopg2.connect`, socket and environment
  guards **before** any test import. Node tests load the isolate shim first.
- Exact-CLI subprocess tests run behind the shims (`PYTHONPATH` → `sitecustomize`;
  `NODE_OPTIONS=--require`). Production code contains no test-only overrides.
- Startup paths for all four services plus the portfolio pre-deploy, under:
  enforced (valid attestation), refused (absent, invalid, cross-service,
  cross-environment, stale-commit), and Railway-context-without-mode.
  - transit-api runs from a build-root-only copy. Its Node generator must emit
    `backend/transit_api`, and a `.` attestation must be rejected there.
- **Lifecycle tests reuse handles without a new physical connection:**
  - an idle pooled checkout after a file change
  - a retained `Session`/`Connection` statement after revocation
  - a poller-style long-lived psycopg2 connection after revocation
  - commit refused after revocation
  - rollback allowed
  - Node environment mutation followed by `pool.query`
  - invalid re-bootstrap revokes
  - metadata-only changes (chmod, chown, ACL-simulated `access`, symlink swap,
    deletion) with unchanged content revoke
- Every binding combination of null, missing, wrong type and mismatch is tested in
  both languages.
- An OS-level no-network proof by independent QA.

## 11. Git tracking exceptions

- Four file-specific negations publish this change's proposal, design, tasks and
  spec; the two attestation markers are ignored.
- The QA contract and private working notes are not published.

## 12. Staged rollout (each stage needs separate owner approval)

| Stage | What happens | Deployed app code | Verification | Rollback boundary |
|---|---|---|---|---|
| **S0** offline | implement the feature on the branch; independent feature-level QA | none | synthetic suites (§16 column 1) | discard the branch |
| **S1** *(optional)* inert tooling merge | the generators and checkers reach `main` and deploy unused | old code; scripts unused | build logs unchanged; services healthy | revert |
| **S2** ephemeral preview (disposable Railway environment with its own Postgres; `portfolio` and `transit-api` only; synthetic data; no automatic poller or SEC writers; targets checked by `ops/check_preview_env.py`) | wire generators with the candidate mechanism; deploy the feature branch with `BIZQLAB_RUNTIME=production` | feature branch (preview only) | all items in §16 column 2 | delete the preview environment |
| **S3a** production health checks | portfolio health check on `/robots.txt` (DB-free); transit-api on `/` (DB-free) | old code | a failed start keeps the previous deployment serving | remove the health checks |
| **S3b** production attestation wiring | the proven mechanism from S2; requires the generators in the deployed code (S1, or an owner-approved equivalent sequence) | old code (attestation present, unread) | build logs; owner-approved `check_build_attestation` metadata runs if needed | remove the wiring |
| **S3c** production explicit mode | `BIZQLAB_RUNTIME=production` on all four services | old code (ignores it) | variable names present | unset (old code is unaffected) |
| **S4** release merge of the M1 feature | strict gates go live on all four services at once (monorepo) | M1 feature | portfolio pre-deploy passes the gate before `alembic`; web and transit-api pass health checks; the poller logs a passed gate; the **next scheduled** SEC run logs a passed gate (observed, not triggered) | **artifact rollback:** Railway "redeploy previous" per service, then revert. Unsetting the variable is *not* a rollback (row 6 refuses). |
| **S5** close | verify all four services; M1 complete | — | closing record | — |

S4 failure behavior:
- **portfolio:** a pre-deploy refusal aborts the deploy (previous stays). A start
  refusal fails the health check (previous stays, if S3a is configured).
- **transit-api:** fails the health check (previous stays).
- **poller:** no health check, so a refusal crash-loops. The owner redeploys the
  previous artifact. This outage window is accepted or mitigated by watching S4 live.
- **SEC:** a refusal fails that day's run. The owner redeploys the previous
  artifact; no data is written.

## 13. Rollback summary

| Change | Rollback |
|---|---|
| Optional inert tooling merge (S1) | revert |
| S3 settings | remove them (old code is unaffected) |
| M1 feature merge (S4) | artifact rollback, then revert |

There are no schema or data changes in M1.

## 14. Decisions (Rev 3)

| ID | Decision | Rejected |
|---|---|---|
| D1‴ | Strict table with no legacy row; production only via explicit mode + complete markers + valid service/environment-bound attestation; compatibility via rollout ordering | earlier legacy stage (fail-open); merge-time enforcement without preparation |
| D4″ | Root-owned policy plus `access(W_OK)` ACL check on the file and every ancestor | mode bits only |
| D5‴ | Revocation at new-connection, checkout, statement and commit boundaries in both languages and raw drivers; any non-identical re-bootstrap revokes | new-connection-only checks (Rev 2) |
| D6′ | C1 grammar with quoted ` #` allowed; `DATABASE_URL` rejected on presence; required `PGSSLMODE` ∈ {`disable`, `require`} with explicit Node mapping | optional SSL defaulting to libpq `prefer` (no Node parity) |
| D11″ | One bounded feature. Strict enforcement reaches production only after the generators are in the deployed code, wired into each production build and verified, and explicit mode is set, all while the current code is still serving; a separate inert-tooling merge first is optional | mandatory two-PR split (Rev 3); enforcement before markers are wired; wiring inside M1 code |
| D12′ | Sanitized errors raised outside handlers (`__context__` is `None`) | `from None` (L7) |
| D13 | Health checks before S4 (S3a) | rely on crash detection |

Decisions D2, D3, D7′, D8, D9′ and D10 are unchanged from the previous revision and not repeated here.

## 15. Backlog (outside M1)

| P | Item |
|---|---|
| P0 | Operator: read-only review of historical local database access |
| P1 | R2 poller reconnect; R4 monotonic upsert and `stop_sequence` 0; R3a header mapping |
| P2 | R3b, R5, R6, R8, R10 frozen feed; migration ownership/ordering review; SEC cron schema dependency |
| P3 | SEC S1–S7; R7; shell helpers and assets; DB-side marker; `verify-full` TLS parity; poller health check |
| P3 | BK-EMAIL-001 (SMTP retirement) |

## 16. What is proven where

| Synthetic offline tests and independent QA | Ephemeral preview (S2) | Owner-approved metadata inspection | Never as QA |
|---|---|---|---|
| decision table and named contexts; grammar; validation; Python/Node parity; policy checks with an injected stat/access provider; attestation classifier, bindings and generator logic (preconditions, idempotency, `build_root`); identity ordering (fake DBAPI); revocation at every boundary with retained and idle handles; Express per-client; sanitization (`__context__`); exact-CLI subprocesses; startup paths for the four services and pre-deploy with synthetic attestation; build-root-only transit-api; no-network sandbox | Railpack plan equivalence (before/after); generator runs in automatic builds; file in the final image; visibility in pre-deploy (before DDL) and the `portfolio`/`transit-api` runtimes (poller and SEC visibility only in a separately approved preview writer run); marker availability at build, runtime and pre-deploy; cached rebuild and existing output; stale and cross-service attestations refused; failing generator fails the build; health-check rollback; `railway run` refusal end-to-end; Node 22.23.3; effective portfolio start command | real root policy ownership, ancestors, ACLs and path viability on the workstation | production migrations, production SEC writes, triggering production cron |

## 17. Owner decisions

1. Approve the strict staged rollout S0–S5 (replacing the legacy stage) as one
   bounded feature, with no mandatory two-PR split (S1 is optional).
2. **The ephemeral S2 preview is required.** Several items can only be proven there.
   The alternative, production observation, cannot prove plan equivalence or failure
   behavior. It runs `portfolio` and `transit-api` only, with synthetic data and no
   automatic poller or SEC writers, and is deleted afterwards.
3. Approve the S3a health checks (a Railway change, made only at S3).
4. Approve `PGSSLMODE` as required, with values {`disable`, `require`}.
5. Accept residuals R-F/R-W (§3.5) and the poller crash-loop window at S4.
6. **Approval record.** Decisions are recorded in the project's private decision log.
7. Confirm the macOS policy path, and approve a later metadata-only inspection.
8. **Contingency.** If S2 shows that `RAILWAY_SERVICE_ID`/`RAILWAY_ENVIRONMENT_ID`
   are unavailable at build, A1 cannot bind as specified, and the design returns to
   the owner.
