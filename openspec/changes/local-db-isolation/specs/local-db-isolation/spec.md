# local-db-isolation

## ADDED Requirements

### Requirement: Production is authorized only by positive, bound evidence
Every Python and Node process SHALL apply the ordered decision table in `design.md`
§3.2, which has no legacy or compatibility row. Production SHALL require
`BIZQLAB_RUNTIME=production`, complete markers (`RAILWAY_PROJECT_ID`,
`RAILWAY_ENVIRONMENT_ID`, `RAILWAY_SERVICE_ID`) and a valid attestation. No
combination of absent variables or files SHALL authorize any database connection.

#### Scenario: Attested production
- **WHEN** `BIZQLAB_RUNTIME=production`, the markers are complete, the attestation is valid, and no workstation indicator exists
- **THEN** the mode is production, and connection parameters equal the base commit's

#### Scenario: Railway context without explicit mode
- **WHEN** the markers are complete and `BIZQLAB_RUNTIME` is unset or `development`, with or without a policy or profile
- **THEN** the process exits before any database connection

#### Scenario: Production without valid attestation
- **WHEN** `BIZQLAB_RUNTIME=production` with complete markers, and the attestation is absent or invalid
- **THEN** the process exits before any database connection

#### Scenario: Production without markers
- **WHEN** `BIZQLAB_RUNTIME=production` and the markers are absent
- **THEN** the process exits before any database connection

#### Scenario: Partial markers
- **WHEN** one or two markers are set, in any mode
- **THEN** the process exits before any database connection

#### Scenario: `railway run` on this workstation
- **WHEN** complete markers are injected, the root policy or `.env.local` exists, and `BIZQLAB_RUNTIME` has any value, even with a valid attestation
- **THEN** the process exits before any database connection

#### Scenario: `railway run` on a fresh machine
- **WHEN** complete markers are injected with no workstation indicators, and either the mode is unset, or the mode is `production` with no attestation
- **THEN** the process exits before any database connection

#### Scenario: Invalid mode value
- **WHEN** `BIZQLAB_RUNTIME` is any other value, including different case or surrounding whitespace
- **THEN** the process exits before any database connection

#### Scenario: Plain local execution
- **WHEN** the markers are absent and the mode is unset or `development`
- **THEN** the mode is development, and connections still require a valid profile and policy

#### Scenario: Enforced service loses its mode variable
- **WHEN** an enforced Railway service has `BIZQLAB_RUNTIME` removed
- **THEN** it refuses to start; it never falls back to unattested behavior

#### Scenario: Identical decisions across languages
- **WHEN** the shared mode fixture, including every named context in `design.md` §3.2, is evaluated by Python and Node
- **THEN** both produce identical outcomes

### Requirement: Build attestation is inert, bound and strictly validated
Generators SHALL be inert in M1 code. They SHALL require the service and environment
IDs at build time, hardcode their build root, refuse on a workstation, and keep
existing output only when it records the same build. The marker SHALL be the single
file `.bizqlab-build-attestation.json` directly inside the build root, with no
subdirectory and no legacy fallback. Runtime validation SHALL require exact schema
and types, a matching build root, service and environment IDs equal to the runtime
values, and a matching commit when one is recorded.

#### Scenario: Generator preconditions
- **WHEN** a generator runs without `RAILWAY_SERVICE_ID` or `RAILWAY_ENVIRONMENT_ID`, on a workstation, or over existing output that records a different build or is not a regular file
- **THEN** it exits non-zero without writing

#### Scenario: Idempotent rebuild
- **WHEN** existing output records the same build (every field except `generated_at`)
- **THEN** the generator succeeds without rewriting

#### Scenario: Binding combinations
- **WHEN** the service or environment ID is null, missing, wrong-typed, malformed, or different from the runtime value; or `git_commit` is non-null and the runtime commit is absent or different; or `git_commit` is wrong-typed
- **THEN** the attestation is `invalid:<code>`

#### Scenario: Null commit
- **WHEN** `git_commit` is null and both IDs match
- **THEN** the attestation is valid, and the runtime commit variable is ignored

#### Scenario: Structural failures
- **WHEN** the attestation is a symlink, over 1 KiB, malformed, has unknown or missing keys, or has the wrong `schema`, `kind` or `build_root`
- **THEN** it is `invalid:<code>`

#### Scenario: Retired marker path
- **WHEN** only `.bizqlab/build-attestation.json` exists, directly or through a `.bizqlab` symlink to a directory outside the build root, including while `.bizqlab` is swapped during the read
- **THEN** the attestation is `absent` (B1 regression)

#### Scenario: Node build-root discriminator
- **WHEN** the Node generator runs from a build-root-only copy of `backend/transit_api`
- **THEN** it writes `build_root` = `backend/transit_api`, and the Node validator rejects a `.` attestation

#### Scenario: Shared attestation fixture
- **WHEN** the shared attestation fixture is evaluated by Python and Node
- **THEN** both classify every case identically

### Requirement: Approval comes from a root-owned, password-free policy
The development target SHALL come only from the fixed-path policy. The file and every
ancestor SHALL be uid 0, not group- or world-writable, and not writable by the
current user via `access(W_OK)`. No environment variable SHALL redirect the path.

#### Scenario: Valid policy
- **WHEN** all ownership, mode, access, realpath, size and schema checks pass
- **THEN** the policy is accepted

#### Scenario: Invalid or writable policy
- **WHEN** the file or any ancestor is not uid 0, is group- or world-writable, is writable by the user through an ACL, has a symlink component, is oversized or malformed, has unknown, missing or wrong-typed keys, or has a `password` key
- **THEN** development resolution fails without connecting

#### Scenario: Credentials and approval changed together
- **WHEN** a same-user process rewrites `.env.local` to another target and tries to write a matching policy
- **THEN** the policy write requires root, and resolution fails on the mismatch

#### Scenario: Unsupported platform or redirected home
- **WHEN** the platform has no defined path, or `HOME` points elsewhere
- **THEN** resolution fails, or is unaffected by `HOME`, respectively

### Requirement: One strict profile grammar shared by Python and Node
`.env.local` SHALL follow `design.md` §4.1 exactly and identically in both languages,
with descriptor-based read checks and no interpolation. Quoted values MAY contain
` #`; unquoted values SHALL NOT. `DATABASE_URL` SHALL be rejected if present at all.
`PGSSLMODE` SHALL be required as `disable` or `require`, mapped explicitly in both
languages.

#### Scenario: Grammar conformance
- **WHEN** the shared grammar fixture is parsed, including quoted and unquoted ` #`, empty quoted values, mixed quotes, invalid UTF-8 and byte limits
- **THEN** Python and Node produce identical mappings or identical error codes

#### Scenario: Malformed entries
- **WHEN** the profile has a BOM, a lone CR, `export`, spaces around `=`, a lowercase key, mismatched quotes, an unquoted value containing ` #`, `${`, a control character, an over-long line or a duplicate key
- **THEN** parsing fails, reporting line and key only

#### Scenario: Missing, symlinked or oversized profile
- **WHEN** the profile is absent, a symlink, unreadable, empty or over 64 KiB
- **THEN** resolution fails without connecting

#### Scenario: Reserved or unknown keys
- **WHEN** the profile contains `DATABASE_URL` (even empty), `BIZQLAB_*`, `RAILWAY_*`, a process-control key, a non-allowlisted `PG*`, or an unknown key
- **THEN** resolution fails naming the key

#### Scenario: Optional connection settings parity
- **WHEN** `PGSSLMODE` is missing or not `disable`/`require`, `PGCONNECT_TIMEOUT` is outside 1–60, or `PGAPPNAME` violates its pattern
- **THEN** resolution fails; valid values (and defaults) produce the documented Python and Node parameters

#### Scenario: Non-DB keys cannot change decisions
- **WHEN** allowlisted non-DB keys are present
- **THEN** they are applied only where unset and after the decisions, and never change the mode or target

#### Scenario: Ancestor or root `.env`
- **WHEN** a `.env` containing `DATABASE_URL` exists in the repo root or an ancestor
- **THEN** no process reads it

### Requirement: One coherent, strictly validated development identity
The profile `PG*` SHALL equal the policy target, satisfy the component character sets,
and produce URL forms that pass SQLAlchemy and libpq round-trips. Divergent inherited
or CLI values, and every non-allowlisted inherited `PG*` (including `PGOPTIONS` and
`PGSSL*`), SHALL be rejected.

#### Scenario: Reserved characters in components
- **WHEN** the database, role or host contains `? # / @ % ,` or whitespace, or a non-allowlisted character, or the database name is reserved
- **THEN** resolution fails naming the key

#### Scenario: Port bounds
- **WHEN** the port is empty, `0`, `65536`, signed, has a leading zero, or uses non-ASCII digits
- **THEN** resolution fails

#### Scenario: Inherited divergent or ambient settings
- **WHEN** inherited `DATABASE_URL` or core/optional `PG*` values differ from the profile, or any other `PG*` is inherited
- **THEN** resolution fails naming only the key

#### Scenario: Conflicting CLI flag
- **WHEN** the poller or bootstrap receives a differing DB flag
- **THEN** it exits before connecting

#### Scenario: URL double round-trip
- **WHEN** the password contains `@ : / % # ? & = +`, spaces, quotes, backslashes or non-ASCII
- **THEN** the exported URL round-trips exactly through both parsers, or resolution fails without showing values

### Requirement: Identity is the first statement on every new development connection
The identity query SHALL be the first statement after the driver handshake. Success
SHALL leave no open transaction. Failure SHALL close the connection and revoke.

#### Scenario: SQLAlchemy ordering
- **WHEN** the development engine opens a DBAPI connection
- **THEN** the identity query precedes every dialect-initialization and pre-ping statement

#### Scenario: Mismatch
- **WHEN** the server reports a different database or role, an address outside `server_addresses`, a different port, or a NULL address
- **THEN** the connection is closed, no checked-out or pooled connection remains, and state is revoked

#### Scenario: Reconnects re-verified
- **WHEN** a connection is recycled or replaced after a failed pre-ping
- **THEN** the replacement is verified first

#### Scenario: Alembic failure before schema creation
- **WHEN** verification fails during an online development migration
- **THEN** `CREATE SCHEMA IF NOT EXISTS portfolio` and the version-table queries never execute

#### Scenario: Verification transaction cleanup
- **WHEN** verification succeeds on psycopg2
- **THEN** no transaction remains open

#### Scenario: Express second client
- **WHEN** a later new pool client reports a different identity
- **THEN** it is removed and ended, its query rejects unexecuted, state is revoked, and the process exits non-zero

#### Scenario: Express startup probe
- **WHEN** the probe fails, or pg-pool is older than 3.13.0
- **THEN** the process exits before listening

### Requirement: Revocation is enforced at every defined boundary
In development the system SHALL run `assert_usable()` at new connection, pooled
checkout, every statement and commit, in SQLAlchemy, raw psycopg2 and Node, as
specified in `design.md` §8.3. Revocation SHALL be terminal. After revocation, no
further statement or commit SHALL succeed on any handle; rollback and close SHALL be
permitted.

#### Scenario: Idle pooled reuse after a file change
- **WHEN** the profile or policy changes and an idle pooled connection is checked out, with no new physical connection
- **THEN** checkout fails and state is revoked

#### Scenario: Retained handle after revocation
- **WHEN** a retained `Engine`, `Connection` or `Session` executes a statement after revocation
- **THEN** the statement is rejected before reaching the driver

#### Scenario: Long-lived raw connection
- **WHEN** a poller-style psycopg2 connection executes or calls `copy_expert` after revocation
- **THEN** it is rejected, and a non-guarded cursor factory cannot bypass this

#### Scenario: Commit after revocation
- **WHEN** an in-flight transaction attempts to commit after revocation
- **THEN** the commit is refused, rollback succeeds, and the connection is invalidated on checkin

#### Scenario: Metadata-only change
- **WHEN** chmod, chown, a writability-changing ACL, symlink replacement, replacement or deletion occurs on the profile, the policy or a policy ancestor, with content unchanged
- **THEN** the next boundary check revokes

#### Scenario: Unrelated activity in a policy ancestor
- **WHEN** an unrelated entry is created in a policy ancestor directory, changing only its size and times
- **THEN** no boundary check revokes

#### Scenario: Environment drift in Python and Node
- **WHEN** `DATABASE_URL` or any `PG*` changes in `os.environ` or `process.env` after commit
- **THEN** the next boundary check revokes, including with a cached engine or the existing pool

#### Scenario: Re-bootstrap
- **WHEN** `bootstrap_runtime()` is called after commit with identical inputs
- **THEN** nothing changes; with different **or invalid** inputs, the active state is revoked and the call raises

#### Scenario: Failed initial bootstrap
- **WHEN** the first bootstrap fails validation
- **THEN** `os.environ` is byte-identical, no state, engine or connection exists, and nothing is cached

#### Scenario: Children and test reset
- **WHEN** a launcher or reload child starts, or a test calls `_reset_for_tests()`
- **THEN** the child re-bootstraps from files; the reset disposes engines and restores state, caches and the environment

### Requirement: Every entry point enforces the contract in its verified invocation form
NiceGUI, imported ASGI usage, Alembic (including pre-deploy), both SEC `--write` forms
(including the cron command), the poller, the static bootstrap (both forms), the
launcher and Express SHALL apply the table and their mode's rules.

#### Scenario: Direct NiceGUI start
- **WHEN** `python -m app.main` runs with an invalid profile or policy (development) or fails the gate (production)
- **THEN** it exits before serving or connecting

#### Scenario: Imported ASGI
- **WHEN** `app.main` is imported without the run block
- **THEN** development DB access raises "runtime not bootstrapped"; in production the gate runs at the first `get_engine()`

#### Scenario: SEC writer
- **WHEN** an SEC `--write` command fails resolution or the gate
- **THEN** it exits before any SEC network request or DB session

#### Scenario: Exact CLI invocations
- **WHEN** each documented command runs as a sanitized subprocess with synthetic inputs and boundary shims
- **THEN** it imports successfully and reaches the specified outcome without real network or DB access

#### Scenario: Synthetic production startup paths
- **WHEN** the four start commands and the portfolio pre-deploy run with a valid attestation, with an absent, invalid, cross-service, cross-environment or stale-commit attestation, and with markers but no mode
- **THEN** the valid case reaches its first mocked connect with base-identical parameters, and every other case exits before connecting

#### Scenario: transit-api build-root independence
- **WHEN** Express starts from a copy of `backend/transit_api` alone
- **THEN** production stages behave as specified without any file outside that root

### Requirement: Secrets never leave the process
Errors SHALL name keys only. Sanitized connect-boundary errors SHALL be raised outside
the handling block, with `__cause__` and `__context__` both `None` (Python) and no
`cause` (Node). Asynchronous pool and client errors SHALL be logged sanitized.
Representations SHALL mask passwords.

#### Scenario: Resolver errors
- **WHEN** any resolution, policy, attestation or identity failure occurs with a synthetic password
- **THEN** no password or DSN appears in exceptions, logs, stdout or stderr

#### Scenario: Driver and parser exceptions
- **WHEN** a mocked driver or DSN parser raises an exception containing a synthetic password and DSN
- **THEN** the surfaced error has `__cause__` and `__context__` equal to `None` (or no Node `cause`), and the formatted traceback and logs contain neither

#### Scenario: Asynchronous pool errors
- **WHEN** an idle pg client emits an `'error'` event containing a synthetic DSN
- **THEN** the log records only the class and code

#### Scenario: Redacted representations
- **WHEN** state, a target or an engine URL is shown with `repr`, `str` or `toJSON`, or is logged
- **THEN** the password is masked
