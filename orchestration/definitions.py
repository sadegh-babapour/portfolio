"""Dagster definitions: the Bank of Canada load, then the dbt warehouse, on a schedule.

What Dagster sees (one lineage graph):
  Valet API -> raw/boc_series, raw/boc_observations   (pipelines/bank_of_canada.py)
            -> dbt staging and marts                  (warehouse/, via dagster-dbt)
Every dbt test becomes an asset check, and raw/boc_observations has a freshness check
with the same 4/7-day rule as warehouse/models/staging/_sources.yml.

Safety: Dagster never holds a password. Each run bootstraps the runtime gate itself
(ApprovedDatabase), opens only verified connections, and gives dbt only the approved
target, for the length of the dbt call. Loading these definitions (the UI, `dagster
definitions validate`) needs no database: the dbt manifest is parsed with placeholder
settings that point nowhere.

Usage (development, through the approved database only):
  make dagster
"""
# No `from __future__ import annotations`: Dagster reads the context and resource
# annotations at definition time and needs them as real types.
import os
import subprocess
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetCheckSpec,
    AssetExecutionContext,
    AssetKey,
    AssetSelection,
    AssetSpec,
    ConfigurableResource,
    Definitions,
    Failure,
    MaterializeResult,
    RetryPolicy,
    ScheduleDefinition,
    define_asset_job,
    in_process_executor,
    multi_asset,
)
from dagster_dbt import DbtCliResource, dbt_assets

from pipelines import bank_of_canada as boc
from pipelines import run_dbt

WAREHOUSE = run_dbt.PROJECT_DIR
DBT = run_dbt.DBT
MANIFEST_DIR = WAREHOUSE / "target" / "dagster_manifest"
# Settings for `dbt parse` only. Parsing never connects; the .invalid host (RFC 6761)
# could not be reached even if something tried.
PARSE_ONLY = {
    "DBT_PG_HOST": "parse-only.invalid", "DBT_PG_PORT": "5432", "DBT_PG_DBNAME": "parse_only",
    "DBT_PG_USER": "parse_only", "DBT_ENV_SECRET_PG_PASSWORD": "", "DBT_PG_SSLMODE": "disable",
    "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
}

RAW_SERIES = AssetKey(["raw", "boc_series"])
RAW_OBSERVATIONS = AssetKey(["raw", "boc_observations"])  # = dbt source raw.boc_observations
FRESHNESS_CHECK = "newest_observation_recent"
WARN_AFTER_DAYS, ERROR_AFTER_DAYS = 4, 7  # as in _sources.yml: weekends and holidays have no rates
# Network blips are worth retrying; a failed dbt test is a data problem and is not retried.
LOADER_RETRY = RetryPolicy(max_retries=2, delay=600)


class ApprovedDatabase(ConfigurableResource):
    """The approved development database, through the runtime gate. No configuration.

    Set up once per run process: bootstrap the gate (a refusal fails the run before any
    connection), refuse production, and verify the database's identity once.
    """

    def setup_for_execution(self, context) -> None:
        from app import runtime_db, runtime_env, runtime_state

        try:
            state = runtime_state.bootstrap_runtime("dagster")
        except runtime_env.RuntimeConfigError as exc:
            raise Failure(f"runtime gate refused: {exc}", allow_retries=False) from None
        if state.mode != "development":
            raise Failure("production has no reporting database yet; refusing", allow_retries=False)
        try:
            runtime_db.connect_verified().close()
        except runtime_env.RuntimeConfigError as exc:  # the message is a code, never a value
            raise Failure(f"database identity check failed: {exc}", allow_retries=False) from None

    def connect(self):
        """A verified psycopg2 connection. The caller closes it."""
        from app import runtime_db

        return runtime_db.connect_verified()

    def dbt_env(self) -> dict[str, str]:
        """The DBT_* settings for the approved target (the password as DBT_ENV_SECRET_)."""
        from app import runtime_state

        return run_dbt.dbt_env(runtime_state.assert_usable().development.target, base={})


@contextmanager
def dbt_environment(values: dict[str, str]):
    """os.environ with every DBT_* setting replaced by `values`, restored afterwards.

    dagster-dbt hands dbt a copy of os.environ and has no way to filter it. PG* and
    DATABASE_URL are left alone: the gate has checked they equal the approved target,
    and changing them would revoke it.
    """
    saved = {k: v for k, v in os.environ.items() if k.startswith("DBT_")}
    for key in saved:
        del os.environ[key]
    os.environ.update(values)
    try:
        yield
    finally:
        for key in values:
            os.environ.pop(key, None)
        os.environ.update(saved)


def freshness(newest: date | None, today: date) -> AssetCheckResult:
    """The _sources.yml rule on the newest observation date: warn at 4 days, error at 7."""
    if newest is None:
        return AssetCheckResult(check_name=FRESHNESS_CHECK, asset_key=RAW_OBSERVATIONS, passed=False,
                                severity=AssetCheckSeverity.ERROR, metadata={"newest": "none"})
    age = (today - newest).days
    severity = AssetCheckSeverity.ERROR if age >= ERROR_AFTER_DAYS else AssetCheckSeverity.WARN
    return AssetCheckResult(check_name=FRESHNESS_CHECK, asset_key=RAW_OBSERVATIONS,
                            passed=age < WARN_AFTER_DAYS, severity=severity,
                            metadata={"newest": newest.isoformat(), "age_days": age})


def newest_observation(conn) -> date | None:
    with conn.cursor() as cur:
        cur.execute("select max(obs_date) from raw.boc_observations")
        return cur.fetchone()[0]


def loader_asset(retry_policy: RetryPolicy | None = LOADER_RETRY):
    """The loader as a Dagster asset. Tests build it without the 10-minute retries."""

    @multi_asset(
        name="bank_of_canada",
        specs=[
            AssetSpec(RAW_SERIES, description="Valet series metadata, one row per series.", kinds={"postgres"}),
            AssetSpec(RAW_OBSERVATIONS, description="Valet observations, one row per series per date.",
                      kinds={"postgres"}),
        ],
        check_specs=[AssetCheckSpec(FRESHNESS_CHECK, asset=RAW_OBSERVATIONS,
                                    description="Newest observation date: warn at 4 days old, error at 7.")],
        group_name="bank_of_canada",
        retry_policy=retry_policy,
    )
    def bank_of_canada(context: AssetExecutionContext, database: ApprovedDatabase):
        """One idempotent load (30-day lookback). Each attempt leaves a row in raw.load_runs."""
        conn = database.connect()
        try:
            result = boc.run(conn)
            newest = newest_observation(conn)
        finally:
            conn.close()
        context.log.info(f"run {result['run_id']} from {result['start_date']}: {result['rows_read']} read, "
                         f"{result['inserted']} inserted, {result['updated']} updated")
        yield MaterializeResult(asset_key=RAW_SERIES)
        yield MaterializeResult(asset_key=RAW_OBSERVATIONS, metadata={
            "load_run_id": result["run_id"], "start_date": result["start_date"].isoformat(),
            "rows_read": result["rows_read"], "inserted": result["inserted"], "updated": result["updated"],
        })
        yield freshness(newest, date.today())

    return bank_of_canada


bank_of_canada = loader_asset()


def parse_manifest() -> Path:
    """dbt's manifest, parsed with placeholder settings and nothing inherited about databases."""
    if not DBT.exists():
        raise RuntimeError(".venv-data is missing; create it with: python3.13 -m venv .venv-data && "
                           ".venv-data/bin/pip install -r requirements-data.txt")
    env = {k: v for k, v in os.environ.items() if not k.startswith(run_dbt.DROP_PREFIXES)}
    env.update(PARSE_ONLY)
    subprocess.run([str(DBT), "--quiet", "parse", "--project-dir", str(WAREHOUSE), "--profiles-dir",
                    str(WAREHOUSE), "--target-path", str(MANIFEST_DIR), "--log-path", str(MANIFEST_DIR)],
                   cwd=WAREHOUSE, env=env, check=True)
    return MANIFEST_DIR / "manifest.json"


@dbt_assets(manifest=parse_manifest())
def warehouse(context: AssetExecutionContext, dbt: DbtCliResource, database: ApprovedDatabase):
    """`dbt build`: seeds, models and tests in dependency order; a failed test skips what follows."""
    with dbt_environment(database.dbt_env()):
        yield from dbt.cli(["build"], context=context).stream()


daily = define_asset_job("boc_daily", selection=AssetSelection.all(),
                         description="Load the Bank of Canada, then dbt build.")

defs = Definitions(
    assets=[bank_of_canada, warehouse],
    jobs=[daily],
    # Weekdays after the Bank's end-of-day publication. Off until turned on in the UI.
    schedules=[ScheduleDefinition(job=daily, cron_schedule="0 18 * * 1-5",
                                  execution_timezone="America/Edmonton")],
    resources={
        "database": ApprovedDatabase(),
        "dbt": DbtCliResource(project_dir=str(WAREHOUSE), profiles_dir=str(WAREHOUSE), dbt_executable=str(DBT)),
    },
    # One process per run: the gate bootstraps once and the steps run in order.
    executor=in_process_executor,
)
