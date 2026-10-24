"""Dagster orchestration (orchestration/definitions.py).

Everything but the last class needs no database and runs wherever .venv-data exists;
the gate and the loader are replaced by fakes, so nothing connects. The last class
materializes the assets against the data CI's throwaway Postgres only.

  .venv-data/bin/python -m unittest discover -s test_data
"""
import os
import unittest
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import psycopg2
import yaml
from dagster import AssetCheckSeverity, AssetKey, DefaultScheduleStatus, Failure, RetryPolicy, materialize
from dagster_dbt import DbtCliResource

from app import runtime_db, runtime_env
from orchestration import definitions as d
from pipelines import bank_of_canada as boc
from pipelines import run_dbt
from test_boc_postgres import ROOT, RecordedSession, ci_target

LOAD_RESULT = {"run_id": 7, "start_date": date(2026, 1, 1), "rows_read": 55, "inserted": 55, "updated": 0}


class FakeDatabase(d.ApprovedDatabase):
    """No gate and no connection: for tests that patch out the loader."""

    def setup_for_execution(self, context) -> None:
        pass

    def connect(self):
        return mock.MagicMock()

    def dbt_env(self) -> dict[str, str]:
        return {}


def dbt_resource() -> DbtCliResource:
    return DbtCliResource(project_dir=str(d.WAREHOUSE), profiles_dir=str(d.WAREHOUSE), dbt_executable=str(d.DBT))


class GateTests(unittest.TestCase):
    """The resource each run sets up: a refusal fails the run before any connection."""

    def setup_with(self, bootstrap, connect=None):
        with mock.patch("app.runtime_state.bootstrap_runtime", bootstrap), \
                mock.patch.object(runtime_db, "connect_verified", connect or mock.MagicMock()) as connected:
            try:
                d.ApprovedDatabase().setup_for_execution(None)
            finally:
                self.connected = connected

    def test_gate_refusal_fails_without_retry_or_connection(self):
        refuse = mock.Mock(side_effect=runtime_env.RuntimeConfigError("policy_missing"))
        with self.assertRaises(Failure) as caught:
            self.setup_with(refuse)
        self.assertIn("policy_missing", str(caught.exception))
        self.assertFalse(caught.exception.allow_retries)
        self.connected.assert_not_called()

    def test_production_mode_refuses(self):
        with self.assertRaisesRegex(Failure, "production"):
            self.setup_with(mock.Mock(return_value=SimpleNamespace(mode="production")))
        self.connected.assert_not_called()

    def test_failed_identity_check_shows_only_the_code(self):
        fail = mock.Mock(side_effect=runtime_db.RuntimeConnectError("connect_failed", sqlstate="08001",
                                                                     redacted_target="user@host:5432/db"))
        with self.assertRaises(Failure) as caught:
            self.setup_with(mock.Mock(return_value=SimpleNamespace(mode="development")), fail)
        self.assertIn("connect_failed", str(caught.exception))
        self.assertNotIn("host", str(caught.exception))
        self.assertFalse(caught.exception.allow_retries)

    def test_dbt_gets_only_dbt_settings_for_the_approved_target(self):
        target = SimpleNamespace(host="10.0.0.2", port=5432, database="portfolio_dev", user="role",
                                 password="pw", sslmode="prefer")
        with mock.patch("app.runtime_state.assert_usable",
                        return_value=SimpleNamespace(development=SimpleNamespace(target=target))):
            env = d.ApprovedDatabase().dbt_env()
        self.assertTrue(all(k.startswith("DBT_") for k in env), sorted(env))
        self.assertEqual((env["DBT_PG_DBNAME"], env["DBT_ENV_SECRET_PG_PASSWORD"]), ("portfolio_dev", "pw"))


class EnvironmentTests(unittest.TestCase):
    def test_dbt_environment_replaces_dbt_settings_and_restores_them(self):
        before = {"DBT_PROFILES_DIR": "/elsewhere", "PGHOST": "approved-host"}
        with mock.patch.dict(os.environ, before, clear=True):
            with d.dbt_environment({"DBT_PG_HOST": "approved-host"}):
                self.assertEqual(dict(os.environ), {"DBT_PG_HOST": "approved-host", "PGHOST": "approved-host"})
            self.assertEqual(dict(os.environ), before)

    def test_manifest_parse_inherits_no_database_settings(self):
        secrets = {"PGPASSWORD": "real-secret", "DATABASE_URL": "postgresql://real-secret",
                   "DBT_ENV_SECRET_PG_PASSWORD": "real-secret"}
        with mock.patch.dict(os.environ, secrets), mock.patch.object(d.subprocess, "run") as run:
            d.parse_manifest()
        env = run.call_args.kwargs["env"]
        self.assertNotIn("real-secret", " ".join(env.values()))
        self.assertTrue(env["DBT_PG_HOST"].endswith(".invalid"))


class DefinitionTests(unittest.TestCase):
    def test_lineage_runs_from_the_loader_through_dbt(self):
        graph = d.defs.resolve_asset_graph()
        self.assertIn(d.RAW_OBSERVATIONS, graph.get(AssetKey(["staging", "stg_boc__observations"])).parent_keys)
        self.assertIn(d.RAW_SERIES, graph.get(AssetKey(["marts", "dim_series"])).parent_keys)

    def test_only_the_loader_retries(self):
        self.assertEqual(d.bank_of_canada.op.retry_policy, RetryPolicy(max_retries=2, delay=600))
        self.assertIsNone(d.warehouse.op.retry_policy)

    def test_schedule_is_weekday_evenings_calgary_and_off_until_turned_on(self):
        (schedule,) = d.defs.schedules
        self.assertEqual((schedule.cron_schedule, schedule.execution_timezone),
                         ("0 18 * * 1-5", "America/Edmonton"))
        self.assertEqual(schedule.default_status, DefaultScheduleStatus.STOPPED)

    def test_no_configuration_can_hold_a_credential(self):
        self.assertEqual(d.ApprovedDatabase.model_fields, {})

    def test_instance_settings(self):
        settings = yaml.safe_load((ROOT / "orchestration" / "dagster.yaml").read_text())
        self.assertFalse(settings["telemetry"]["enabled"])
        self.assertEqual(settings["concurrency"]["runs"]["max_concurrent_runs"], 1)

    def test_freshness_follows_the_sources_rule(self):
        today = date(2026, 10, 23)
        cases = {3: (True, None), 4: (False, AssetCheckSeverity.WARN), 7: (False, AssetCheckSeverity.ERROR)}
        for age, (passed, severity) in cases.items():
            check = d.freshness(today - timedelta(days=age), today)
            self.assertEqual(check.passed, passed, age)
            if severity is not None:
                self.assertEqual(check.severity, severity, age)
        self.assertFalse(d.freshness(None, today).passed)


class LoaderAssetTests(unittest.TestCase):
    """The loader asset with the loader itself patched out: nothing connects."""

    def test_success_reports_both_raw_tables_and_freshness(self):
        with mock.patch.object(boc, "run", return_value=LOAD_RESULT), \
                mock.patch.object(d, "newest_observation", return_value=date.today()):
            result = materialize([d.loader_asset(None)], resources={"database": FakeDatabase()})
        self.assertTrue(result.success)
        self.assertEqual({e.asset_key for e in result.get_asset_materialization_events()},
                         {d.RAW_SERIES, d.RAW_OBSERVATIONS})
        (check,) = result.get_asset_check_evaluations()
        self.assertTrue(check.passed)

    def test_failed_load_skips_dbt(self):
        with mock.patch.object(boc, "run", side_effect=boc.SourceError("HTTP 503: down")):
            result = materialize([d.loader_asset(None), d.warehouse], raise_on_error=False,
                                 resources={"database": FakeDatabase(), "dbt": dbt_resource()})
        self.assertFalse(result.success)
        self.assertEqual(result.get_failed_step_keys(), {"bank_of_canada"})
        # A step whose upstream failed never starts (in-process runs log no "skipped" event).
        started = {e.step_key for e in result.all_events if e.event_type_value == "STEP_START"}
        self.assertEqual(started, {"bank_of_canada"})


class CiDatabase(d.ApprovedDatabase):
    """The data CI's throwaway Postgres in place of the gate (CI has no approval policy)."""

    def setup_for_execution(self, context) -> None:
        pass

    def connect(self):
        return psycopg2.connect(**ci_target())

    def dbt_env(self) -> dict[str, str]:
        t = ci_target()
        return run_dbt.dbt_env(SimpleNamespace(host=t["host"], port=t["port"], database=t["dbname"], user=t["user"],
                                               password=t["password"], sslmode="disable"), base={})


class PostgresMaterializeTests(unittest.TestCase):
    """The whole job against a real database, the Valet API replaced by the recorded answer."""

    @classmethod
    def setUpClass(cls):
        cls.target = ci_target()

    def setUp(self):
        self.conn = psycopg2.connect(**self.target)
        with self.conn.cursor() as cur:
            cur.execute("drop schema if exists raw cascade; drop schema if exists staging cascade; "
                        "drop schema if exists marts cascade")
        self.conn.commit()
        real_run = boc.run
        recorded = mock.patch.object(boc, "run", lambda conn: real_run(conn, since=date(2025, 12, 20),
                                                                       session=RecordedSession()))
        recorded.start()
        self.addCleanup(recorded.stop)

    def tearDown(self):
        self.conn.close()

    def query(self, sql):
        with self.conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()

    def materialize(self, assets):
        return materialize(assets, raise_on_error=False,
                           resources={"database": CiDatabase(), "dbt": dbt_resource()})

    def test_job_loads_builds_and_checks(self):
        result = self.materialize([d.loader_asset(None), d.warehouse])
        self.assertTrue(result.success)
        self.assertIn(AssetKey(["marts", "mart_canada_rates_daily"]),
                      {e.asset_key for e in result.get_asset_materialization_events()})
        self.assertEqual(self.query("select gov_10y, gov_2y, spread_10y_2y_bps from marts.mart_canada_rates_daily "
                                    "where obs_date = '2025-12-22'"),
                         [(Decimal("3.46"), Decimal("2.60"), Decimal("86"))])
        checks = {(c.asset_key, c.check_name): c for c in result.get_asset_check_evaluations()}
        # The recorded answer ends 2026-01-06, so the freshness check fails; every dbt test passes.
        fresh = checks.pop((d.RAW_OBSERVATIONS, d.FRESHNESS_CHECK))
        self.assertEqual((fresh.passed, fresh.severity), (False, AssetCheckSeverity.ERROR))
        self.assertTrue(checks)
        self.assertTrue(all(c.passed for c in checks.values()), [k for k, c in checks.items() if not c.passed])

    def test_failed_dbt_test_keeps_bad_data_from_the_page(self):
        self.assertTrue(self.materialize([d.loader_asset(None), d.warehouse]).success)
        mart = "select usd_cad from marts.mart_canada_rates_daily where obs_date = '2025-12-22'"
        good = self.query(mart)
        with self.conn.cursor() as cur:
            cur.execute("update raw.boc_observations set value = 137.48 "
                        "where series_id = 'FXUSDCAD' and obs_date = '2025-12-22'")
        self.conn.commit()

        result = self.materialize([d.warehouse])
        self.assertFalse(result.success)
        # dbt tests a table after building it, so fct_rates_daily now holds the bad row,
        # but the mart the /markets page reads is built after the test and was skipped.
        self.assertEqual(self.query("select value from marts.fct_rates_daily "
                                    "where series_id = 'FXUSDCAD' and obs_date = '2025-12-22'"),
                         [(Decimal("137.48"),)])
        self.assertEqual(self.query(mart), good)


if __name__ == "__main__":
    unittest.main()
