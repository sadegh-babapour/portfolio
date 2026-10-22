"""Bank of Canada loader and dbt wrapper: parsing, API errors and the dbt environment.

Offline: a recorded Valet response (test/fixtures) and a fake HTTP session. The
database behaviour (idempotency, revisions, no partial loads) runs against a real
Postgres in the data CI job (test_data/test_boc_postgres.py).
"""
from __future__ import annotations

import json
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

import requests

from pipelines import bank_of_canada as boc
from pipelines import run_dbt

FIXTURE = Path(__file__).with_name("fixtures") / "boc_valet_2025-12-20_2026-01-06.json"


def recorded() -> dict:
    return json.loads(FIXTURE.read_text())


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self._text = text

    def json(self):
        if self._text is not None:
            raise ValueError("not JSON")
        return self._payload


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        if self.error:
            raise self.error
        return self.response


class ParseTests(unittest.TestCase):
    def test_recorded_response_parses_every_series(self):
        metadata, observations = boc.parse(recorded(), boc.SERIES)
        self.assertEqual([s.series_id for s in metadata], list(boc.SERIES))
        self.assertEqual(metadata[0].unit, "Percent")
        # 9 business days x 6 series, plus the policy rate on New Year's Day.
        self.assertEqual(len(observations), 55)
        first = [o for o in observations if o.series_id == "FXUSDCAD"][0]
        self.assertEqual((first.obs_date, first.value), (date(2025, 12, 22), Decimal("1.3748")))

    def test_holiday_without_a_value_is_skipped_not_zero(self):
        _, observations = boc.parse(recorded(), boc.SERIES)
        new_year = [o.series_id for o in observations if o.obs_date == date(2026, 1, 1)]
        self.assertEqual(new_year, ["V39079"])  # only the policy rate is published on 1 January
        self.assertNotIn(Decimal(0), [o.value for o in observations])

    def test_empty_value_is_skipped(self):
        payload = recorded()
        payload["observations"][0]["FXUSDCAD"] = {"v": ""}
        _, observations = boc.parse(payload, boc.SERIES)
        self.assertEqual(len(observations), 54)

    def test_values_keep_their_published_precision(self):
        _, observations = boc.parse(recorded(), boc.SERIES)
        corra = [o.value for o in observations if o.series_id == "AVG.INTWO"]
        self.assertEqual(str(corra[0]), "2.2800")  # Decimal, not a float like 2.28000000001

    def test_missing_series_names_the_series(self):
        payload = recorded()
        del payload["seriesDetail"]["FXUSDCAD"]
        with self.assertRaisesRegex(boc.SourceError, "FXUSDCAD"):
            boc.parse(payload, boc.SERIES)

    def test_non_numeric_value_fails_the_load(self):
        payload = recorded()
        payload["observations"][0]["V39079"] = {"v": "n/a"}
        with self.assertRaisesRegex(boc.SourceError, "V39079 on 2025-12-22"):
            boc.parse(payload, boc.SERIES)

    def test_nan_is_not_a_number(self):
        for text in ("NaN", "Infinity"):
            payload = recorded()
            payload["observations"][0]["V39079"] = {"v": text}
            with self.subTest(text), self.assertRaisesRegex(boc.SourceError, "is not a number"):
                boc.parse(payload, boc.SERIES)

    def test_bad_date_fails_the_load(self):
        payload = recorded()
        payload["observations"][0]["d"] = "22/12/2025"
        with self.assertRaisesRegex(boc.SourceError, "valid date"):
            boc.parse(payload, boc.SERIES)

    def test_response_without_observations_fails(self):
        with self.assertRaisesRegex(boc.SourceError, "seriesDetail/observations"):
            boc.parse({"message": "maintenance"}, boc.SERIES)


class FetchTests(unittest.TestCase):
    def test_one_request_for_all_series_from_the_start_date(self):
        session = FakeSession(FakeResponse(payload=recorded()))
        boc.fetch(boc.SERIES, date(2025, 12, 20), session)
        (url, params, timeout), = session.calls
        self.assertTrue(url.endswith("/observations/V39079,AVG.INTWO,BD.CDN.2YR.DQ.YLD,BD.CDN.5YR.DQ.YLD,"
                                     "BD.CDN.10YR.DQ.YLD,FXUSDCAD/json"), url)
        self.assertEqual(params, {"start_date": "2025-12-20"})
        self.assertEqual(timeout, 30)

    def test_unknown_series_reports_the_api_message(self):
        response = FakeResponse(404, {"message": "Series NOPE123 not found."})
        with self.assertRaisesRegex(boc.SourceError, "HTTP 404: Series NOPE123 not found"):
            boc.fetch(("NOPE123",), date(2026, 1, 1), FakeSession(response))

    def test_server_error_without_json(self):
        with self.assertRaisesRegex(boc.SourceError, "HTTP 503: no message"):
            boc.fetch(boc.SERIES, date(2026, 1, 1), FakeSession(FakeResponse(503, text="<html>")))

    def test_network_failure_is_a_source_error(self):
        session = FakeSession(error=requests.ConnectionError("dns"))
        with self.assertRaisesRegex(boc.SourceError, "ConnectionError"):
            boc.fetch(boc.SERIES, date(2026, 1, 1), session)


class DbtEnvTests(unittest.TestCase):
    class Target:
        host, port, database, user = "10.0.0.2", 5432, "portfolio_dev", "dev_role"
        password, sslmode = "synthetic-pw", "disable"

    def test_inherited_database_settings_never_reach_dbt(self):
        inherited = {"PATH": "/bin", "PGHOST": "prod.example", "PGDATABASE": "railway",
                     "DATABASE_URL": "postgresql://x", "DBT_PG_HOST": "prod.example",
                     "DBT_PROFILES_DIR": "/elsewhere"}
        env = run_dbt.dbt_env(self.Target, inherited)
        self.assertEqual(env["PATH"], "/bin")
        self.assertEqual({k for k in env if k.startswith("PG") or k == "DATABASE_URL"}, set())
        self.assertNotIn("DBT_PROFILES_DIR", env)
        self.assertEqual((env["DBT_PG_HOST"], env["DBT_PG_PORT"], env["DBT_PG_DBNAME"], env["DBT_PG_USER"]),
                         ("10.0.0.2", "5432", "portfolio_dev", "dev_role"))
        # dbt scrubs DBT_ENV_SECRET_* values from its logs.
        self.assertEqual(env["DBT_ENV_SECRET_PG_PASSWORD"], "synthetic-pw")

    def test_dbt_reads_the_password_only_from_the_secret_variable(self):
        profile = (run_dbt.PROJECT_DIR / "profiles.yml").read_text()
        self.assertIn("env_var('DBT_ENV_SECRET_PG_PASSWORD')", profile)
        self.assertNotIn("synthetic", profile)


if __name__ == "__main__":
    unittest.main()
