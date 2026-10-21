"""ops/check_preview_env.py: preview services must name the approved disposable targets only."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from ops import check_preview_env as preview

APPROVED = {
    "environment_id": "env-preview", "production_environment_id": "env-prod",
    "database": {"host": "postgres.railway.internal", "port": "5432", "name": "preview_db", "role": "preview_user"},
    "api_base": "https://transit-api-preview.example/api",
}
URL = "postgresql://preview_user:synthetic-preview-Pw@postgres.railway.internal:5432/preview_db"
PG = {"PGHOST": "postgres.railway.internal", "PGPORT": "5432", "PGDATABASE": "preview_db", "PGUSER": "preview_user",
      "PGPASSWORD": "synthetic-preview-Pw"}
BASE = {"RAILWAY_ENVIRONMENT_ID": "env-preview", "BIZQLAB_RUNTIME": "production"}
GOOD = {
    "portfolio": {**BASE, "DATABASE_URL": URL, "VITE_TRANSIT_API_BASE_URL": "https://transit-api-preview.example/api"},
    "transit-api": {**BASE, **PG},
}
REDIRECTING = ["host=other-db.example", "hostaddr=203.0.113.9", "port=6543", "dbname=railway", "user=postgres",
               "service=prod", "options=-c%20search_path%3Devil", "sslmode=disable&sslmode=require",
               "target_session_attrs=any", "passfile=/tmp/x"]
MALFORMED = [
    "postgresql://preview_user:synthetic-preview-Pw@postgres.railway.internal:port/preview_db",
    "postgresql://preview_user:synthetic-preview-Pw@postgres.railway.internal/preview_db",
    "postgresql://preview_user:synthetic-preview-Pw@postgres.railway.internal:5432",
    "postgresql://preview_user:synthetic-preview-Pw@postgres.railway.internal:5432/preview_db#frag",
    "postgresql://preview_user:synthetic-preview-Pw@a.example,postgres.railway.internal:5432/preview_db",
    "mysql://preview_user:synthetic-preview-Pw@postgres.railway.internal:5432/preview_db",
    "not a url",
]


class PreviewEnvTests(unittest.TestCase):
    def run_main(self, service, env, approved=APPROVED):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "approved.json")
            if approved is not None:
                path.write_text(json.dumps(approved))
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = preview.main(["--service", service, "--approved", str(path)], env=env)
            return code, out.getvalue() + err.getvalue()

    def test_approved_preview_services_pass(self):
        for service, env in GOOD.items():
            with self.subTest(service):
                self.assertEqual(self.run_main(service, env), (0, f"preview environment approved for {service}\n"))

    def test_unapproved_configuration_is_blocked_without_printing_values(self):
        cases = [
            ("portfolio", {**GOOD["portfolio"], "RAILWAY_ENVIRONMENT_ID": "env-prod"}, "railway_environment_is_production"),
            ("portfolio", {**GOOD["portfolio"], "DATABASE_URL": URL.replace("preview_db", "railway")},
             "database_not_approved_preview [component=name]"),
            ("portfolio", {**GOOD["portfolio"], "DATABASE_URL": URL.replace("postgres.railway.internal", "x.proxy.rlwy.net")},
             "database_public_proxy_host"),
            ("portfolio", {**GOOD["portfolio"], "VITE_TRANSIT_API_BASE_URL": "https://transit-api-production.up.railway.app/api"},
             "browser_api_not_approved_preview"),
            ("portfolio", {**GOOD["portfolio"], "RESEND_API_KEY": "re_synthetic"}, "external_side_effect_configured [key=RESEND_API_KEY]"),
            ("portfolio", {k: v for k, v in GOOD["portfolio"].items() if k != "BIZQLAB_RUNTIME"}, "preview_must_run_attested_mode"),
            ("transit-api", {**BASE}, "database_settings_missing [key=PGHOST]"),
            ("transit-api", {**GOOD["transit-api"], "PGOPTIONS": "-c search_path=evil"},
             "unsupported_driver_setting [key=PGOPTIONS]"),
        ]
        for service, env, expected in cases:
            with self.subTest(expected):
                code, output = self.run_main(service, env)
                self.assertEqual(code, 1)
                self.assertIn(expected, output)
                self.assertNotIn("synthetic-preview-Pw", output)
                self.assertNotIn("preview_db", output)

    def test_transit_api_is_checked_on_the_pg_fields_it_actually_uses(self):
        # QA finding 1: an approved DATABASE_URL must not mask PG fields naming another database.
        safe_url_unsafe_pg = {**GOOD["transit-api"], "DATABASE_URL": URL, "PGHOST": "other-db.example"}
        code, output = self.run_main("transit-api", safe_url_unsafe_pg)
        self.assertEqual(code, 1)
        self.assertIn("database_not_approved_preview [component=host]", output)
        # pg ignores DATABASE_URL, so an unrelated URL beside approved PG fields does not change the target.
        unsafe_url_safe_pg = {**GOOD["transit-api"], "DATABASE_URL": URL.replace("postgres.railway.internal", "prod.example")}
        self.assertEqual(self.run_main("transit-api", unsafe_url_safe_pg)[0], 0)
        for key, value in (("PGDATABASE", "railway"), ("PGUSER", "postgres"), ("PGPORT", "6543")):
            with self.subTest(key):
                self.assertEqual(self.run_main("transit-api", {**GOOD["transit-api"], key: value})[0], 1)

    def test_portfolio_url_query_parameters_cannot_redirect_the_target(self):
        # QA finding 2: libpq honours query parameters over the URL authority.
        for query in REDIRECTING:
            with self.subTest(query):
                code, output = self.run_main("portfolio", {**GOOD["portfolio"], "DATABASE_URL": f"{URL}?{query}"})
                self.assertEqual(code, 1)
                self.assertIn("database_url_unsupported_or_malformed [key=DATABASE_URL]", output)
                self.assertNotIn("synthetic-preview-Pw", output)

    def test_portfolio_refuses_libpq_environment_fallbacks(self):
        for key in ("PGHOST", "PGHOSTADDR", "PGOPTIONS", "PGSERVICE", "PGPASSWORD"):
            with self.subTest(key):
                code, output = self.run_main("portfolio", {**GOOD["portfolio"], key: "x"})
                self.assertEqual(code, 1)
                self.assertIn(f"inherited_driver_setting [key={key}]", output)

    def test_portfolio_accepts_the_spellings_the_app_normalizes(self):
        for url in (URL.replace("postgresql://", "postgres://"), URL.replace("postgresql://", "postgresql+psycopg2://"),
                    URL + "?sslmode=require", URL + "?connect_timeout=10&sslmode=require"):
            with self.subTest(url.split("://")[0]):
                self.assertEqual(self.run_main("portfolio", {**GOOD["portfolio"], "DATABASE_URL": url})[0], 0)

    def test_malformed_urls_refuse_cleanly(self):
        # QA finding 4: no exception escapes; a sanitized non-zero refusal instead.
        for url in MALFORMED:
            with self.subTest(url[-30:]):
                code, output = self.run_main("portfolio", {**GOOD["portfolio"], "DATABASE_URL": url})
                self.assertEqual(code, 1)
                self.assertIn("database_url_unsupported_or_malformed", output)
                self.assertNotIn("synthetic-preview-Pw", output)

    def test_startup_writers_are_excluded_from_preview(self):
        # QA finding 3: the poller applies migrations before its polling controls, so even the
        # "disabled" settings below would write on startup.
        disabled = {**BASE, **PG, "POLL_ENABLED": "false", "GTFS_AUTO_SYNC_ENABLED": "false", "ADMIN_KILL_SWITCH": "true"}
        self.assertEqual(self.run_main("transit-poller", disabled), (1, "PREVIEW BLOCKED (transit-poller): poller_excluded_from_preview\n"))

    def test_command_line_refuses_malformed_url_without_traceback(self):
        import os
        import subprocess
        import sys

        import run_isolated

        with tempfile.TemporaryDirectory() as tmp:
            approved = Path(tmp, "approved.json")
            approved.write_text(json.dumps(APPROVED))
            env = {**run_isolated.isolated_env(), **GOOD["portfolio"], "DATABASE_URL": MALFORMED[0]}
            result = subprocess.run([sys.executable, "ops/check_preview_env.py", "--service", "portfolio", "--approved",
                                     str(approved)], cwd=preview.ROOT, env=env, capture_output=True, text=True,
                                    timeout=60, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertIn("database_url_unsupported_or_malformed", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("synthetic-preview-Pw", result.stdout + result.stderr)
        self.assertTrue(os.path.isdir(preview.ROOT / "ops"))

    def test_missing_or_incomplete_approval_blocks_the_preview(self):
        self.assertIn("approved_targets_missing_or_unreadable", self.run_main("portfolio", GOOD["portfolio"], None)[1])
        incomplete = {**APPROVED, "database": {**APPROVED["database"], "host": ""}}
        self.assertIn("approved_key_missing [key=database.host]", self.run_main("portfolio", GOOD["portfolio"], incomplete)[1])
        same = {**APPROVED, "production_environment_id": "env-preview"}
        self.assertIn("approved_environment_is_production", self.run_main("portfolio", GOOD["portfolio"], same)[1])

    def test_malformed_approval_shapes_refuse_with_codes(self):
        db = APPROVED["database"]
        cases = [
            ([], "approved_targets_not_an_object"),
            ("env-preview", "approved_targets_not_an_object"),
            (42, "approved_targets_not_an_object"),
            ({**APPROVED, "database": ["postgres.railway.internal"]}, "approved_key_invalid_type [key=database]"),
            ({**APPROVED, "database": "postgres.railway.internal"}, "approved_key_invalid_type [key=database]"),
            ({**APPROVED, "database": None}, "approved_key_missing [key=database]"),
            ({**APPROVED, "environment_id": ["env-preview"]}, "approved_key_invalid_type [key=environment_id]"),
            ({**APPROVED, "production_environment_id": 7}, "approved_key_invalid_type [key=production_environment_id]"),
            ({**APPROVED, "api_base": {"url": "x"}}, "approved_key_invalid_type [key=api_base]"),
            ({**APPROVED, "database": {**db, "host": ["a", "b"]}}, "approved_key_invalid_type [key=database.host]"),
            ({**APPROVED, "database": {**db, "port": True}}, "approved_key_invalid_type [key=database.port]"),
            ({**APPROVED, "database": {**db, "port": 5432.0}}, "approved_key_invalid_type [key=database.port]"),
            ({**APPROVED, "database": {**db, "name": None}}, "approved_key_missing [key=database.name]"),
        ]
        for approved, code in cases:
            with self.subTest(code=code, approved=type(approved).__name__):
                status, output = self.run_main("portfolio", GOOD["portfolio"], approved)
                self.assertEqual(status, 1)
                self.assertEqual(output, f"PREVIEW BLOCKED (portfolio): {code}\n")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        null = Path(tmp.name, "null.json")
        null.write_text("null")
        self.assertEqual(preview.load_approved(null), (None, ["approved_targets_not_an_object"]))
        deep = Path(tmp.name, "deep.json")
        deep.write_text("[" * 100000 + "]" * 100000)
        self.assertEqual(preview.load_approved(deep), (None, ["approved_targets_missing_or_unreadable"]))

    def test_valid_approval_shapes_are_unchanged(self):
        self.assertEqual(self.run_main("portfolio", GOOD["portfolio"])[0], 0)
        integer_port = {**APPROVED, "database": {**APPROVED["database"], "port": 5432}}
        self.assertEqual(self.run_main("transit-api", GOOD["transit-api"], integer_port)[0], 0)

    def test_command_line_refuses_malformed_approval_without_traceback(self):
        import subprocess
        import sys

        import run_isolated

        for content in ("[]", "null", '"x"', json.dumps({**APPROVED, "database": ["x"]}),
                        json.dumps({**APPROVED, "api_base": 1})):
            with self.subTest(content=content[:20]), tempfile.TemporaryDirectory() as tmp:
                approved = Path(tmp, "approved.json")
                approved.write_text(content)
                env = {**run_isolated.isolated_env(), **GOOD["portfolio"]}
                result = subprocess.run([sys.executable, "ops/check_preview_env.py", "--service", "portfolio",
                                         "--approved", str(approved)], cwd=preview.ROOT, env=env,
                                        capture_output=True, text=True, timeout=60, check=False)
                self.assertEqual(result.returncode, 1)
                self.assertRegex(result.stderr, r"^PREVIEW BLOCKED \(portfolio\): approved_")
                self.assertNotIn("Traceback", result.stderr)
                self.assertNotIn("synthetic-preview-Pw", result.stdout + result.stderr)

    def test_example_file_is_placeholders_only(self):
        example = json.loads((preview.Path(preview.__file__).parent / "preview-approved.example.json").read_text())
        self.assertEqual(sorted(example), sorted(preview.APPROVED_KEYS))
        self.assertTrue(all(v.startswith("<") for v in example["database"].values()))


if __name__ == "__main__":
    unittest.main()
