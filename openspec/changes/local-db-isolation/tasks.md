# Tasks: local-db-isolation (Rev 3)

Status: batches 1–5 are implemented and passed independent offline QA on
`feature/001-mac-parity`; the boxes below track the formal record and the rollout.
Work touches only the files in `design.md` §9.

Every batch is local and offline: no pushes, installs, migrations, DB connections,
Railway changes or build wiring. Each batch ends with an offline test run and a
private record of the results.

## 0. Preconditions (owner)
- [ ] 0.1 Accept `design.md` §17 decisions 1–7, and record the A–D approval in the private decision log.
- [ ] 0.2 Record the start SHA and `git status --short --branch`.

## Attestation tooling (inert until wired)
- [ ] P1.1 `ops/write_build_attestation.py` and `backend/transit_api/scripts/writeBuildAttestation.js`:
  - service and environment IDs required
  - hardcoded `build_root`
  - optional commit
  - same-build idempotency (all fields except `generated_at`); workstation refusal
  - mode 0444
- [ ] P1.2 `ops/check_build_attestation.py` and `backend/transit_api/scripts/checkBuildAttestation.js`: read-only classification output.
- [ ] P1.3 `test/fixtures/attestation_cases.json` (every binding combination; structural cases); Python and Node tests agree; Node generator test runs from a build-root-only copy.
- [ ] P1.4 `.gitignore`: `/.bizqlab-build-attestation.json`, `/backend/transit_api/.bizqlab-build-attestation.json`.

## Strict isolation

### Batch 1 — Pure resolver and shared fixtures
- [ ] 1.1 Fixtures:
  - `runtime_mode_cases.json`: every §3.2 row plus every named context
  - `profile_grammar_cases.json`: quoted and unquoted ` #`, invalid UTF-8, byte limits
  - `validation_cases.json`
  - `policy_cases.json`: stat and access combinations, including ACL-only writability
- [ ] 1.2 `app/runtime_env.py` pure functions:
  - mode table and attestation classifier
  - descriptor-based strict parser and key classes, with the `PGSSLMODE`, `PGCONNECT_TIMEOUT` and `PGAPPNAME` rules and mapping
  - policy loader with injectable stat, access and realpath
  - validators, inherited rules, and URL double round-trip
- [ ] 1.3 `backend/transit_api/config/runtimeEnv.js` with the same functions (Node 22 APIs only).
- [ ] 1.4 Parity tests over every fixture.

### Batch 2 — State, revocation boundaries, engine and Alembic
- [ ] 2.1 `RuntimeState`:
  - committed fingerprint (environment snapshot, security metadata, digests)
  - `assert_usable()`
  - terminal revocation
  - any non-identical or invalid re-bootstrap revokes
  - `_reset_for_tests()`
- [ ] 2.2 `connect_verified()` with `GuardedConnection`/`GuardedCursor`:
  - every execute/copy path is guarded
  - commit is guarded
  - non-guarded cursor factories are rejected
- [ ] 2.3 Engine:
  - `creator`
  - `PoolEvents.checkout` and `checkin`
  - `ConnectionEvents.before_cursor_execute` and `commit` (verify that `commit` fires before `do_commit`, using a fake DBAPI)
- [ ] 2.4 `migrations/env.py`: `NullPool` with `creator`; gate in production.
- [ ] 2.5 Sanitized boundary errors raised outside the `except` block.
- [ ] 2.6 Isolation: `test/run_isolated.py`, `test/shims/sitecustomize.py`, and a base class using `addCleanup`.
- [ ] 2.7 `test/test_lifecycle.py`:
  - idle checkout after a file change
  - retained `Session`/`Connection` after revocation
  - long-lived psycopg2 `execute` and `copy_expert` after revocation
  - commit refused and rollback allowed
  - metadata-only changes (chmod, chown, ACL-simulated access, symlink swap, deletion)
  - environment drift with a cached engine
  - invalid re-bootstrap
  - failed initial bootstrap leaves the environment byte-identical
- [ ] 2.8 Tests for SQLAlchemy ordering, the failing creator, reconnect re-verification, Alembic failure before `CREATE SCHEMA`, and `__cause__`/`__context__` being `None`.

### Batch 3 — NiceGUI and SEC
- [ ] 3.1 `app/main.py`: no `load_dotenv`; bootstrap or gate in the run block; imported-ASGI outcome.
- [ ] 3.2 Both SEC scripts: bootstrap or gate before `EdgarClient` when `--write`.
- [ ] 3.3 Subprocess tests of the exact commands (cron form included) in each stage of `design.md` §10.

### Batch 4 — Poller, bootstrap and Express
- [ ] 4.1 Poller and static bootstrap per `design.md` §7.
- [ ] 4.2 Express:
  - `verifyRuntime()`
  - explicit-field pool with SSL, timeout and app-name mapping
  - `onConnect` with identity and `assertUsable`
  - guarded client `query` and pool proxy
  - sanitized `'error'` handlers
  - probe and pg-pool version assertion
- [ ] 4.3 Tests:
  - real pg-pool 3.13.0 with a fake Client: second-client mismatch
  - `process.env` mutation followed by `pool.query`
  - async error sanitization
  - startup paths in every attestation case, including from a build-root-only copy

### Batch 5 — Launcher, docs, tracking, full regression
- [ ] 5.1 `ops/dev.py` (`check` prints only non-secret observed identity); `ops/db-policy.example.json`.
- [ ] 5.2 Docs and config:
  - `.env.example`: `DATABASE_URL` removed; `PGSSLMODE` added
  - `README.md`: local sequence and rollout pointer
  - `.gitignore`: four OpenSpec negations
- [ ] 5.3 Static scans:
  - no dotenv calls
  - connect call sites restricted to the reviewed list
  - injected paths in tests
  - no test-only overrides
  - no `cursor_factory=` bypass in the development paths
- [ ] 5.4 Full offline suites through the isolated runner, plus the Node and frontend suites; secret scan; diff ⊆ §9.
- [ ] 5.5 Record the results privately.

## Independent QA
- [ ] C.1 Execute the private verification contract, including the no-network sandbox run.

## Rollout track (each stage needs separate owner approval; `design.md` §12)
- [ ] S1 *(optional)* Merge the inert attestation tooling separately; confirm unchanged builds and healthy services. Not required, but the generators must be in the deployed code before S3b.
- [ ] S2 Ephemeral preview (`portfolio` and `transit-api` only; synthetic data; no automatic poller or SEC writers; approved targets checked by `ops/check_preview_env.py`): every item in `design.md` §16 column 2, written up privately; then delete the preview environment.
- [ ] S3a Production health checks: portfolio `/robots.txt`, transit-api `/`.
- [ ] S3b Production attestation wiring, using the mechanism proven in S2, with the generators already in the deployed code; build-log evidence.
- [ ] S3c Set `BIZQLAB_RUNTIME=production` on all four services; the old code ignores it.
- [ ] S4 Release merge of the M1 feature, only after S3a–S3c:
  - pre-deploy gate passes before Alembic
  - health checks pass
  - the poller logs a passed gate
  - the next scheduled SEC run logs a passed gate (observed, not triggered)
  - rollback is by artifact
- [ ] S5 Closing record; M1 complete.
