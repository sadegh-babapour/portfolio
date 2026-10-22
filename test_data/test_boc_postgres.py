"""Bank of Canada loader and dbt models against a real, throwaway Postgres.

Runs only in the GitHub Actions data job, whose Postgres service container exists
for this job alone and is deleted afterwards. It refuses anywhere else: on a
workstation the loader reaches databases only through the runtime gate.

  python -m unittest discover -s test_data
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import unittest
from datetime import date
from unittest import mock
from decimal import Decimal
from pathlib import Path

import psycopg2

from pipelines import bank_of_canada as boc

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "test" / "fixtures" / "boc_valet_2025-12-20_2026-01-06.json"
DBT = ROOT / ".venv-data" / "bin" / "dbt"
CI_HOSTS = {"localhost", "127.0.0.1"}


def ci_target() -> dict:
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("DATA_CI_PG_HOST") not in CI_HOSTS:
        raise unittest.SkipTest("data CI only: needs the GitHub Actions throwaway Postgres")
    return {"host": os.environ["DATA_CI_PG_HOST"], "port": int(os.environ["DATA_CI_PG_PORT"]),
            "dbname": os.environ["DATA_CI_PG_DBNAME"], "user": os.environ["DATA_CI_PG_USER"],
            "password": os.environ["DATA_CI_PG_PASSWORD"]}


class RecordedSession:
    """Serves the recorded Valet response, optionally edited, or fails like a dead API."""

    def __init__(self, payload=None, status_code=200):
        self.payload = payload if payload is not None else json.loads(FIXTURE.read_text())
        self.status_code = status_code

    def get(self, url, params=None, timeout=None):
        session = self

        class Response:
            status_code = session.status_code

            def json(self):
                return session.payload

        return Response()


class PostgresLoadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.target = ci_target()

    def setUp(self):
        self.conn = psycopg2.connect(**self.target)
        with self.conn.cursor() as cur:
            cur.execute("drop schema if exists raw cascade; drop schema if exists staging cascade; "
                        "drop schema if exists marts cascade")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def query(self, sql, params=None):
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def load(self, session=None, series=boc.SERIES):
        return boc.run(self.conn, series=series, since=date(2025, 12, 20), session=session or RecordedSession())

    def test_second_run_changes_nothing(self):
        first = self.load()
        second = self.load()
        self.assertEqual((first["inserted"], first["updated"]), (55, 0))
        self.assertEqual((second["inserted"], second["updated"]), (0, 0))
        self.assertEqual(self.query("select count(*) from raw.boc_observations"), [(55,)])
        self.assertEqual(self.query("select status, rows_inserted from raw.load_runs order by run_id"),
                         [("succeeded", 55), ("succeeded", 0)])

    def test_revised_value_is_updated_and_marked(self):
        self.load()
        before = self.query("select last_changed_at from raw.boc_observations "
                            "where series_id = 'FXUSDCAD' and obs_date = '2025-12-22'")
        revised = copy.deepcopy(RecordedSession().payload)
        revised["observations"][0]["FXUSDCAD"] = {"v": "1.3750"}
        result = self.load(RecordedSession(revised))
        self.assertEqual((result["inserted"], result["updated"]), (0, 1))
        value, changed = self.query("select value, last_changed_at from raw.boc_observations "
                                    "where series_id = 'FXUSDCAD' and obs_date = '2025-12-22'")[0]
        self.assertEqual(value, Decimal("1.3750"))
        self.assertGreater(changed, before[0][0])

    def test_failure_after_writing_rolls_back_every_observation(self):
        real_upsert = boc.upsert

        def upsert_then_fail(conn, metadata, observations):
            real_upsert(conn, metadata, observations)  # all 55 rows written, not yet committed
            raise RuntimeError("connection lost")

        with mock.patch.object(boc, "upsert", upsert_then_fail), self.assertRaisesRegex(RuntimeError, "lost"):
            self.load()
        self.assertEqual(self.query("select count(*) from raw.boc_observations"), [(0,)])
        self.assertEqual(self.query("select status, error from raw.load_runs"),
                         [("failed", "RuntimeError: connection lost")])

    def test_bad_value_is_recorded_and_loads_nothing(self):
        broken = copy.deepcopy(RecordedSession().payload)
        broken["observations"][-1]["V39079"] = {"v": "n/a"}
        with self.assertRaises(boc.SourceError):
            self.load(RecordedSession(broken))
        self.assertEqual(self.query("select count(*) from raw.boc_observations"), [(0,)])
        (status, error), = self.query("select status, error from raw.load_runs")
        self.assertEqual(status, "failed")
        self.assertIn("V39079", error)

    def test_dead_api_is_recorded_as_failed(self):
        with self.assertRaisesRegex(boc.SourceError, "HTTP 503"):
            self.load(RecordedSession({"message": "down"}, status_code=503))
        self.assertEqual(self.query("select status from raw.load_runs"), [("failed",)])

    def test_unknown_series_fails_without_a_partial_load(self):
        with self.assertRaisesRegex(boc.SourceError, "NOPE123"):
            self.load(series=(*boc.SERIES, "NOPE123"))
        self.assertEqual(self.query("select count(*) from raw.boc_observations"), [(0,)])

    def test_dbt_build_passes_and_tests_catch_a_bad_value(self):
        self.load()
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PG", "DBT_"))}
        env.update({"DBT_PG_HOST": self.target["host"], "DBT_PG_PORT": str(self.target["port"]),
                    "DBT_PG_DBNAME": self.target["dbname"], "DBT_PG_USER": self.target["user"],
                    "DBT_ENV_SECRET_PG_PASSWORD": self.target["password"], "DBT_PG_SSLMODE": "disable"})
        project = ROOT / "warehouse"
        dbt = [str(DBT), "build", "--project-dir", str(project), "--profiles-dir", str(project)]

        build = subprocess.run(dbt, cwd=project, env=env, capture_output=True, text=True)
        self.assertEqual(build.returncode, 0, build.stdout[-4000:])
        self.assertEqual(self.query("select gov_10y, gov_2y, spread_10y_2y_bps from marts.mart_canada_rates_daily "
                                    "where obs_date = '2025-12-22'"),
                         [(Decimal("3.46"), Decimal("2.60"), Decimal("86"))])
        # New Year's Day has only the policy rate: one row, the rest null, nothing carried forward.
        self.assertEqual(self.query("select policy_rate, gov_10y from marts.mart_canada_rates_daily "
                                    "where obs_date = '2026-01-01'"), [(Decimal("2.25"), None)])

        # A loading bug (USD/CAD of 137.48) must fail the build, not reach a dashboard.
        with self.conn.cursor() as cur:
            cur.execute("update raw.boc_observations set value = 137.48 "
                        "where series_id = 'FXUSDCAD' and obs_date = '2025-12-22'")
        self.conn.commit()
        bad = subprocess.run(dbt, cwd=project, env=env, capture_output=True, text=True)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("assert_values_in_expected_range", bad.stdout)


if __name__ == "__main__":
    unittest.main()
