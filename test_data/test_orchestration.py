"""Dagster orchestration (orchestration/definitions.py).

Everything but the last class needs no database and runs wherever .venv-data exists;
the gate and the loader are replaced by fakes, so nothing connects. The last class
materializes the assets against the data CI's throwaway Postgres only.

  .venv-data/bin/python -m unittest discover -s test_data
"""
import os
import secrets
import unittest
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

import psycopg2
import psycopg2.errors
import psycopg2.sql
import yaml
from dagster import (AssetCheckSeverity, AssetKey, DagsterEventType, DagsterInstance, DefaultScheduleStatus,
                     DefaultSensorStatus, Failure, RetryPolicy, build_run_status_sensor_context, instance_for_test,
                     materialize)
from dagster_dbt import DbtCliResource

from app import runtime_db, runtime_env
from orchestration import alerts, production
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

    def setup_in_production(self, connect):
        with mock.patch.dict(os.environ, {"DATABASE_URL": "set"}), mock.patch.object(production, "connect", connect):
            self.setup_with(mock.Mock(return_value=SimpleNamespace(mode="production")))

    def test_production_checks_the_role_instead_of_the_dev_identity(self):
        conn = mock.MagicMock()
        connect = mock.Mock(return_value=conn)
        self.setup_in_production(connect)
        connect.assert_called_once_with("set")
        conn.close.assert_called_once()
        self.connected.assert_not_called()

    def test_production_wrong_role_fails_without_retry(self):
        with self.assertRaises(Failure) as caught:
            self.setup_in_production(mock.Mock(side_effect=production.RoleRefused("wrong_role")))
        self.assertIn("wrong_role", str(caught.exception))
        self.assertFalse(caught.exception.allow_retries)

    def test_production_connect_error_shows_only_its_class(self):
        error = psycopg2.OperationalError('connection to server at "secret-host.internal" failed')
        with self.assertRaises(Failure) as caught:
            self.setup_in_production(mock.Mock(side_effect=error))
        self.assertIn("OperationalError", str(caught.exception))
        self.assertNotIn("secret-host", str(caught.exception))

    def test_production_without_database_url_fails(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(Failure, "database_url_missing"):
                self.setup_with(mock.Mock(return_value=SimpleNamespace(mode="production")))

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
                        return_value=SimpleNamespace(mode="development", development=SimpleNamespace(target=target))):
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

    def test_alert_sensors_exist_and_are_off_outside_production(self):
        self.assertEqual({s.name: s.default_status for s in d.defs.sensors},
                         {"email_on_run_failure": DefaultSensorStatus.STOPPED,
                          "email_on_failed_check": DefaultSensorStatus.STOPPED})
        self.assertTrue(production.in_production({"BIZQLAB_RUNTIME": "production"}))
        self.assertFalse(production.in_production({"BIZQLAB_RUNTIME": "development"}))

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


class ProductionRoleTests(unittest.TestCase):
    """orchestration/production.py without a database."""

    def test_only_the_unprivileged_dagster_role_passes(self):
        self.assertIsNone(production.role_problem(("bizqlab_dagster", False, "dagster", False)))
        cases = {"wrong_role": ("postgres", True, "public", True),
                 "privileged_role": ("bizqlab_dagster", True, "dagster", False),
                 "site_schema_access": ("bizqlab_dagster", False, "dagster", True),
                 "search_path_not_dagster": ("bizqlab_dagster", False, '"$user", public', False)}
        for code, row in cases.items():
            self.assertEqual(production.role_problem(row), code)

    def test_dbt_target_comes_from_the_service_url(self):
        user = production.ROLE
        password = secrets.token_hex(8)
        target = production.target(f"postgresql://{user}:{password}@postgres.railway.internal:5432/railway")
        self.assertEqual((target.host, target.port, target.database, target.user, target.password, target.sslmode),
                         ("postgres.railway.internal", 5432, "railway", user, password, "prefer"))

    def start(self, mode, connect=None):
        with mock.patch("app.runtime_state.bootstrap_entry_point", return_value=SimpleNamespace(mode=mode)), \
                mock.patch.dict(os.environ, {"DATABASE_URL": "set"}), \
                mock.patch.object(production, "connect", connect or mock.MagicMock()), \
                mock.patch.object(production.os, "execv") as execv, \
                mock.patch("sys.stderr") as stderr:
            code = production.main()
        return code, execv, "".join(str(c.args[0]) for c in stderr.write.call_args_list)

    def test_start_refuses_outside_production(self):
        code, execv, printed = self.start("development")
        self.assertEqual(code, 2)
        execv.assert_not_called()
        self.assertIn("not_production", printed)

    def test_start_refuses_the_wrong_role_before_dagster_starts(self):
        code, execv, printed = self.start("production", mock.Mock(side_effect=production.RoleRefused("wrong_role")))
        self.assertEqual(code, 2)
        execv.assert_not_called()
        self.assertIn("wrong_role", printed)

    def test_start_becomes_the_daemon_once_the_role_is_checked(self):
        _code, execv, _printed = self.start("production")
        execv.assert_called_once_with(production.DAEMON,
                                      [str(production.DAEMON), "run", "-m", "orchestration.definitions"])


class AlertTests(unittest.TestCase):
    """orchestration/alerts.py: the emails, and both sensors on real (in-memory) runs."""

    SETTINGS = {"DAGSTER_ALERT_RESEND_KEY": "re_test", "DAGSTER_ALERT_FROM": "Dagster <alerts@example.com>",
                "DAGSTER_ALERT_TO": "owner@example.com"}

    def test_send_posts_one_plain_email_with_the_service_key(self):
        post = mock.Mock()
        alerts.send("subject", "body", env=self.SETTINGS, post=post)
        (url,), kwargs = post.call_args
        self.assertEqual(url, alerts.RESEND_EMAILS_URL)
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer re_test")
        self.assertEqual(kwargs["json"], {"from": "Dagster <alerts@example.com>", "to": ["owner@example.com"],
                                          "subject": "subject", "text": "body"})

    def test_missing_settings_name_the_keys_only(self):
        with self.assertRaisesRegex(RuntimeError, "DAGSTER_ALERT_TO"):
            alerts.send("s", "b", env={**self.SETTINGS, "DAGSTER_ALERT_TO": ""}, post=mock.Mock())

    def test_error_lines_lose_urls_and_stay_short(self):
        user = "someone"
        password = secrets.token_hex(8)
        line = alerts.first_line(f"could not connect to postgresql://{user}:{password}@host/db\nsecond line")
        self.assertNotIn(password, line)
        self.assertNotIn("second", line)
        self.assertLessEqual(len(alerts.first_line("x" * 1000)), alerts.MAX_ERROR_CHARS + 1)

    def run_loader(self, instance, newest_age_days, **loader):
        with mock.patch.object(boc, "run", **loader), \
                mock.patch.object(d, "newest_observation", return_value=date.today() - timedelta(days=newest_age_days)):
            return materialize([d.loader_asset(None)], resources={"database": FakeDatabase()},
                               instance=instance, raise_on_error=False)

    def test_failure_sensor_emails_the_failed_step(self):
        instance = DagsterInstance.ephemeral()
        result = self.run_loader(instance, 0, side_effect=boc.SourceError("HTTP 503: down"))
        (failure,) = instance.all_logs(result.run_id, of_type=DagsterEventType.RUN_FAILURE)
        sensor = next(s for s in alerts.sensors(DefaultSensorStatus.STOPPED) if s.name == "email_on_run_failure")
        context = build_run_status_sensor_context(sensor_name=sensor.name, dagster_event=failure.dagster_event,
                                                  dagster_instance=instance,
                                                  dagster_run=instance.get_run_by_id(result.run_id))
        with mock.patch.object(alerts, "send") as send:
            sensor(context.for_run_failure())
        subject, body = send.call_args.args
        self.assertIn("run failed", subject)
        self.assertIn("step bank_of_canada", body)
        self.assertIn("HTTP 503", body)

    def test_an_error_check_emails_and_a_warning_does_not(self):
        instance = DagsterInstance.ephemeral()
        stale = self.run_loader(instance, 10, return_value=LOAD_RESULT)
        self.assertTrue(stale.success)
        self.assertEqual(alerts.failed_checks(instance, stale.run_id),
                         ["raw/boc_observations: newest_observation_recent"])
        warned = self.run_loader(instance, 5, return_value=LOAD_RESULT)
        self.assertEqual(alerts.failed_checks(instance, warned.run_id), [])

        sensor = next(s for s in alerts.sensors(DefaultSensorStatus.STOPPED) if s.name == "email_on_failed_check")
        for run, emails in ((stale, 1), (warned, 0)):
            (success,) = instance.all_logs(run.run_id, of_type=DagsterEventType.RUN_SUCCESS)
            context = build_run_status_sensor_context(sensor_name=sensor.name, dagster_event=success.dagster_event,
                                                      dagster_instance=instance,
                                                      dagster_run=instance.get_run_by_id(run.run_id))
            with mock.patch.object(alerts, "send") as send:
                sensor(context)
            self.assertEqual(send.call_count, emails)


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


class RailwayRoleTests(unittest.TestCase):
    """ops/sql/railway_dagster_role.sql, and the whole job as bizqlab_dagster, in CI's Postgres."""

    @classmethod
    def setUpClass(cls):
        cls.target = ci_target()

    def setUp(self):
        self.admin = psycopg2.connect(**self.target)
        self.addCleanup(self.admin.close)
        password = secrets.token_hex(16)
        with self.admin.cursor() as cur:
            cur.execute("drop schema if exists raw, staging, marts, dagster, portfolio, transit cascade")
            cur.execute("create schema portfolio; create table portfolio.users (email text); "
                        "insert into portfolio.users values ('someone@example.com'); create schema transit")
            cur.execute((ROOT / "ops" / "sql" / "railway_dagster_role.sql").read_text())
            set_password = psycopg2.sql.SQL("alter role bizqlab_dagster password {}")
            cur.execute(set_password.format(psycopg2.sql.Literal(password)))
        self.admin.commit()
        t = self.target
        self.url = f"postgresql://bizqlab_dagster:{password}@{t['host']}:{t['port']}/{t['dbname']}"

    def query(self, sql):
        with self.admin.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()

    def test_the_role_passes_its_check_and_cannot_read_the_site(self):
        conn = production.connect(self.url)
        self.addCleanup(conn.close)
        with self.assertRaises(psycopg2.errors.InsufficientPrivilege), conn.cursor() as cur:
            cur.execute("select email from portfolio.users")

    def test_the_ci_superuser_and_a_role_with_site_access_are_refused(self):
        t = self.target
        with self.assertRaisesRegex(production.RoleRefused, "wrong_role"):
            production.connect(f"postgresql://{t['user']}:{t['password']}@{t['host']}:{t['port']}/{t['dbname']}")
        with self.admin.cursor() as cur:
            cur.execute("grant usage on schema portfolio to bizqlab_dagster")
        self.admin.commit()
        with self.assertRaisesRegex(production.RoleRefused, "site_schema_access"):
            production.connect(self.url)

    def test_job_runs_as_the_role_with_history_in_the_dagster_schema(self):
        url = self.url

        class RoleDatabase(d.ApprovedDatabase):
            """The production connections, without the gate (CI has no attestation)."""

            def setup_for_execution(self, context) -> None:
                pass

            def connect(self):
                return production.connect(url)

            def dbt_env(self) -> dict[str, str]:
                return run_dbt.dbt_env(production.target(url), base={})

        real_run = boc.run
        recorded = mock.patch.object(boc, "run", lambda conn: real_run(conn, since=date(2025, 12, 20),
                                                                       session=RecordedSession()))
        with instance_for_test(overrides={"storage": {"postgres": {"postgres_url": url}}}) as instance, recorded:
            result = materialize([d.loader_asset(None), d.warehouse], instance=instance,
                                 resources={"database": RoleDatabase(), "dbt": dbt_resource()})
        self.assertTrue(result.success)
        self.assertEqual(self.query("select gov_10y from marts.mart_canada_rates_daily where obs_date = '2025-12-22'"),
                         [(Decimal("3.46"),)])
        self.assertGreater(self.query("select count(*) from pg_tables where schemaname = 'dagster'")[0][0], 0)
        self.assertEqual(self.query("select count(*) from pg_tables where schemaname = 'public'")[0][0], 0)
        self.assertEqual(self.query("select distinct tableowner from pg_tables "
                                    "where schemaname in ('raw', 'marts', 'dagster')"), [("bizqlab_dagster",)])


if __name__ == "__main__":
    unittest.main()
