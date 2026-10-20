# Change proposal: local-db-isolation

Status: design revision 3, reconciled with the approved simplifications. Implemented and
independently QA'd offline on `feature/001-mac-parity`; rollout stages S1–S5 (`design.md` §12)
are pending, each with separate owner approval.

Base: `feature/001-mac-parity` @ `b3630248004d7c2462b49f48f1306598abf8a846`.

## Why

- **Implicit discovery.** NiceGUI and Alembic call `load_dotenv()` with no path.
- **Interpolation.** The launcher loads the profile with interpolation enabled.
- **Two unchecked representations.** Python reads `DATABASE_URL` and the transit
  services read `PG*`; nothing checks that they agree. Ambient `PG*` variables
  silently redirect both libpq and pg.
- **No guard on direct entry points.**
- **Railway variables can't prove location.** `railway run` injects them locally.
- **Merge equals deploy.** All four Railway services build automatically with
  Railpack from `main`. Today no service sets a runtime mode, the portfolio runs
  Alembic as a pre-deploy step, and the SEC refresh runs on a daily cron.

## What changes

1. **Production by positive evidence only.**
   - Requires `BIZQLAB_RUNTIME=production`, complete Railway markers, and a build
     attestation bound to the service and environment.
   - Workstation indicators refuse.
   - **No legacy or fail-open stage:** an earlier draft's transitional exception is removed.
2. **Compatibility through rollout ordering**, as one bounded feature (no mandatory
   two-PR split).
   - An ephemeral preview proves Railpack behavior: `portfolio` and `transit-api`
     only, synthetic data, no automatic poller or SEC writers.
   - Production gets health checks, attestation wiring (with the generators already
     in the deployed code) and explicit mode while the **current** code is still
     deployed. A separate inert-tooling merge is one optional way to get the
     generators there first.
   - Only then does the release merge deploy the strict gates. Rollback is by artifact.
3. **Root-owned approval policy (B1)**, including an ACL-aware writability check on
   every ancestor directory.
4. **One strict `.env.local` grammar (C1)** shared by Python and Node:
   - quoted values may contain ` #`;
   - `DATABASE_URL` is rejected if present at all;
   - `PGSSLMODE` is required, as `disable` or `require`, with an explicit Node
     mapping.
5. **Identity verified first** on every new development connection (Python and
   Express). Errors are sanitized so that `__context__` is `None`.
6. **Defined revocation boundaries** in both languages and the raw drivers:
   - new connection, pooled checkout, every statement, and commit;
   - covers retained or idle handles and metadata-only file changes;
   - any non-identical (including invalid) re-bootstrap revokes.
7. **Mandatory synthetic tests (D)**, with a clear split between what synthetic
   tests prove and what needs the ephemeral preview (`design.md` §16).

## Non-goals

- No Railway, build, cron, variable, migration, schema or data change in M1 code.
  Stages S1–S4 each need separate owner approval.
- No unrelated security, transit, SEC, email or UI work.
- No new dependencies.

## Impact

- File list: `design.md` §9.
- Rollout: `design.md` §12. Owner decisions: §17.
- Production stays unchanged until S4, which runs only after the S2 preview has
  proven the attestation path and S3 has wired it.
