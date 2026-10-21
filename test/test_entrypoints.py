"""Exact entry-command tests: every DB entry point runs as a real subprocess.

Each command runs exactly as an operator or Railway would start it, behind the
test isolation shim (test/shims/sitecustomize.py) plus a scenario harness
(test/shims/entrypoint_harness.py). The harness supplies a synthetic profile,
policy and attestation, and a fake psycopg2 driver whose statements are logged;
real psycopg2 connections, sockets and real configuration reads stay blocked.
Nothing here reaches PostgreSQL, the network or a real profile.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import run_isolated
import test_lifecycle as tl
from app import runtime_db

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
PROD_URL = "postgresql://prod_user:synthetic-prod-Pw@db.railway.internal:5432/railway"
MARKERS = tl.MARKERS
ATTESTATION = tl.t.load_fixture("attestation_cases.json")["base_doc"]

WEB = [PY, "-m", "app.main"]
ALEMBIC = [PY, "-m", "alembic", "upgrade", "head"]
POLLER = [PY, "-m", "poller.poll_calgary_gtfs_rt_current", "--once"]
STATIC_SCRIPT = [PY, "scripts/bootstrap_transit_db.py"]
STATIC_MODULE = [PY, "-m", "scripts.bootstrap_transit_db"]
LAUNCHER = [PY, "ops/dev.py", "check", "--expected-db", "portfolio_dev"]

ALL_COMMANDS = {
    "web": WEB, "alembic": ALEMBIC, "poller": POLLER, "static-script": STATIC_SCRIPT,
    "static-module": STATIC_MODULE, "launcher": LAUNCHER,
}
CONNECT_EVENTS = {"dev_connect", "production_connect", "production_engine", "sql"}


class Run:
    def __init__(self, completed: subprocess.CompletedProcess, events: list[dict]):
        self.code = completed.returncode
        self.stdout = completed.stdout
        self.stderr = completed.stderr
        self.events = events

    def of(self, kind: str) -> list[dict]:
        return [e for e in self.events if e["event"] == kind]

    def statements(self) -> list[str]:
        return [e["statement"] for e in self.of("sql")]

    def output(self) -> str:
        return self.stdout + self.stderr


def run(command, *, env=None, fs=None, stub_ui_run=False, identity=None, timeout=120) -> Run:
    with tempfile.TemporaryDirectory() as tmp:
        log = os.path.join(tmp, "events.jsonl")
        scenario = {"log": log, "fs": fs or {}, "stub_ui_run": stub_ui_run}
        if identity is not None:
            scenario["identity"] = list(identity)
        path = os.path.join(tmp, "scenario.json")
        Path(path).write_text(json.dumps(scenario))
        child_env = run_isolated.isolated_env()
        # The shims and the test fakes only; the repository root is not on the path, so the
        # script forms must find the app package themselves.
        child_env["PYTHONPATH"] = os.pathsep.join([str(REPO / "test" / "shims"), str(REPO / "test")])
        child_env["BQ_ENTRYPOINT_SCENARIO"] = path
        child_env.update(env or {})
        completed = subprocess.run(command, cwd=REPO, env=child_env, capture_output=True, text=True,
                                   timeout=timeout, check=False)
        events = []
        if os.path.exists(log):
            events = [json.loads(line) for line in Path(log).read_text().splitlines()]
        return Run(completed, events)


def production_env(**extra) -> dict:
    return {"BIZQLAB_RUNTIME": "production", **MARKERS, **extra}


class EntrypointCase(unittest.TestCase):
    def assert_refused_before_connect(self, result: Run, code: str, name: str):
        self.assertNotEqual(result.code, 0, name)
        self.assertIn(code, result.output(), name)
        touched = [e for e in result.events if e["event"] in CONNECT_EVENTS]
        self.assertEqual(touched, [], name)
        self.assertNotIn("synthetic-prod-Pw", result.output(), name)
        self.assertNotIn(tl.SYN_PW, result.output(), name)

    def assert_identity_first(self, result: Run, name: str):
        statements = result.statements()
        self.assertTrue(statements, f"{name}: no SQL ran\n{result.output()[-2000:]}")
        self.assertEqual(statements[0], runtime_db.IDENTITY_SQL, name)
        connections = {}
        for event in result.of("sql"):
            connections.setdefault(event["connection"], event["statement"])
        # Every physical connection starts with the identity query.
        self.assertEqual(set(connections.values()), {runtime_db.IDENTITY_SQL}, name)
        self.assertEqual(result.of("production_connect") + result.of("production_engine"), [], name)


class RefusalTests(EntrypointCase):
    def test_inherited_production_database_url_is_refused_before_connect(self):
        for name, command in ALL_COMMANDS.items():
            with self.subTest(name):
                result = run(command, env={"DATABASE_URL": PROD_URL})
                self.assert_refused_before_connect(result, "inherited_conflict", name)
                self.assertIn("DATABASE_URL", result.output(), name)

    def test_inherited_conflicting_pg_variable_is_refused_before_connect(self):
        for name, command in ALL_COMMANDS.items():
            with self.subTest(name):
                result = run(command, env={"PGHOST": "10.9.9.9"})
                self.assert_refused_before_connect(result, "inherited_conflict", name)

    def test_unsupported_inherited_pg_variable_is_refused(self):
        for name in ("web", "poller", "launcher"):
            with self.subTest(name):
                result = run(ALL_COMMANDS[name], env={"PGOPTIONS": "-c search_path=evil"})
                self.assert_refused_before_connect(result, "inherited_pg_key", name)

    def test_railway_context_without_production_mode_is_refused(self):
        for name, command in ALL_COMMANDS.items():
            with self.subTest(name):
                result = run(command, env={**MARKERS, "DATABASE_URL": PROD_URL}, fs={"kind": "production"})
                self.assert_refused_before_connect(result, "railway_context_without_production_mode", name)

    def test_railway_run_on_this_workstation_is_refused(self):
        for name, command in ALL_COMMANDS.items():
            with self.subTest(name):
                result = run(command, env=production_env(DATABASE_URL=PROD_URL))
                self.assert_refused_before_connect(result, "railway_context_on_workstation", name)

    def test_unattested_production_is_refused(self):
        for attestation, label in ((None, "absent"), ({**ATTESTATION, "railway_service_id": "svc-2"}, "cross-service"),
                                   ({**ATTESTATION, "build_root": "backend/transit_api"}, "wrong build root")):
            for name in ("web", "alembic", "poller"):
                with self.subTest(name=name, attestation=label):
                    result = run(ALL_COMMANDS[name], env=production_env(DATABASE_URL=PROD_URL),
                                 fs={"kind": "production", "attestation": attestation})
                    self.assert_refused_before_connect(result, "production_not_attested", name)

    def test_missing_policy_is_refused(self):
        for name in ("web", "poller", "static-script", "launcher"):
            with self.subTest(name):
                result = run(ALL_COMMANDS[name], fs={"policy_absent": True})
                self.assert_refused_before_connect(result, "policy_missing", name)

    def test_profile_with_database_url_is_refused(self):
        result = run(WEB, fs={"profile_overrides": {"DATABASE_URL": "postgresql://x"}})
        self.assert_refused_before_connect(result, "reserved_key", "web")

    def test_poller_cli_database_flag_conflict_is_refused(self):
        for flags in (["--dbname", "other_db"], ["--host", "10.9.9.9"], ["--database-url", PROD_URL],
                      ["--port", "5433"]):
            with self.subTest(flags=flags[0]):
                result = run(POLLER + flags)
                self.assert_refused_before_connect(result, "cli_conflict", "poller")
                self.assertIn(flags[0], result.output())

    def test_launcher_expected_database_mismatch_is_refused(self):
        result = run([PY, "ops/dev.py", "check", "--expected-db", "other_db"])
        self.assert_refused_before_connect(result, "Database mismatch", "launcher")


class DevelopmentTests(EntrypointCase):
    def test_identity_precedes_business_sql(self):
        cases = {
            "web": (WEB, {"stub_ui_run": True}, 0, "web"),
            # The fake driver cannot answer Alembic's INSERT ... RETURNING, so the upgrade
            # stops after its first migration's DDL; the ordering is what matters here.
            "alembic": (ALEMBIC, {}, None, "alembic"),
            "static-script": (STATIC_SCRIPT, {}, 0, "transit-bootstrap"),
            "static-module": (STATIC_MODULE, {}, 0, "transit-bootstrap"),
            "launcher": (LAUNCHER, {}, 0, "launcher"),
            # The poller reaches the network after the database gate; the isolation
            # shim blocks it, so it exits non-zero after its first SQL.
            "poller": (POLLER, {}, None, "poller"),
        }
        for name, (command, options, exit_code, purpose) in cases.items():
            with self.subTest(name):
                result = run(command, **options)
                if exit_code is not None:
                    self.assertEqual(result.code, exit_code, f"{name}\n{result.output()[-3000:]}")
                self.assertEqual([e["purpose"] for e in result.of("bootstrapped")], [purpose], name)
                self.assertEqual([e["mode"] for e in result.of("bootstrapped")], ["development"], name)
                self.assertEqual(result.of("dotenv"), [], name)
                if name == "poller":
                    # It opens its database before the network fetch fails.
                    self.assertTrue(result.of("dev_connect"), f"{name}\n{result.output()[-3000:]}")
                    self.assertNotEqual(result.code, 0)
                self.assert_identity_first(result, name)

    def test_business_statements_follow_identity(self):
        result = run(STATIC_SCRIPT)
        statements = result.statements()
        self.assertEqual(statements[:2], [runtime_db.IDENTITY_SQL, "ROLLBACK"])
        self.assertIn("CREATE SCHEMA IF NOT EXISTS transit", statements[2])  # the first migration file
        result = run(WEB, stub_ui_run=True)
        self.assertIn("select 1", result.statements())
        result = run(ALEMBIC)
        statements = result.statements()
        self.assertEqual(statements[0], runtime_db.IDENTITY_SQL)
        self.assertIn("CREATE SCHEMA IF NOT EXISTS portfolio", statements[2:])

    def test_wrong_identity_stops_before_business_sql(self):
        wrong = ("portfolio_dev", "portfolio_dev_user", "10.0.0.9", 5432)
        for name, command, options in (("static-script", STATIC_SCRIPT, {}), ("poller", POLLER, {}),
                                       ("alembic", ALEMBIC, {}), ("web", WEB, {"stub_ui_run": True}),
                                       ("launcher", LAUNCHER, {})):
            with self.subTest(name):
                result = run(command, identity=wrong, **options)
                self.assertNotEqual(result.code, 0, name)
                # The identity query, its rollback, and nothing else.
                self.assertEqual(result.statements(), [runtime_db.IDENTITY_SQL, "ROLLBACK"], name)
                self.assertIn("identity_mismatch", result.output(), name)
                self.assertNotIn(tl.SYN_PW, result.output(), name)

    def test_equal_inherited_values_and_cli_flags_are_accepted(self):
        result = run(POLLER + ["--dbname", "portfolio_dev"], env={"PGHOST": "192.168.1.50", "PGSSLMODE": "disable"})
        self.assertEqual([e["mode"] for e in result.of("bootstrapped")], ["development"])
        self.assert_identity_first(result, "poller")

    def test_launcher_child_bootstraps_again_from_inherited_equal_values(self):
        result = run([PY, "ops/dev.py", "run", "--expected-db", "portfolio_dev", "--", PY, "-m",
                      "scripts.bootstrap_transit_db"])
        self.assertEqual(result.code, 0, result.output()[-3000:])
        self.assertEqual([(e["purpose"], e["mode"]) for e in result.of("bootstrapped")],
                         [("launcher", "development"), ("transit-bootstrap", "development")])
        self.assertEqual(len(result.of("dev_connect")), 2)
        self.assert_identity_first(result, "launcher run")


class ProductionTests(EntrypointCase):
    """Attested production keeps today's connection parameters after the gate."""

    def run_production(self, command, **options):
        return run(command, env=production_env(DATABASE_URL=PROD_URL, PGHOST="db.railway.internal", PGPORT="5432",
                                               PGDATABASE="railway", PGUSER="prod_user", PGPASSWORD="synthetic-prod-Pw"),
                   fs={"kind": "production"}, **options)

    def test_raw_clients_use_todays_parameters(self):
        for name, command in (("poller", POLLER), ("static-script", STATIC_SCRIPT), ("static-module", STATIC_MODULE)):
            with self.subTest(name):
                result = self.run_production(command)
                self.assertEqual([e["mode"] for e in result.of("bootstrapped")], ["production"], name)
                # Today's precedence: DATABASE_URL wins, passed positionally to psycopg2.connect.
                self.assertEqual(result.of("production_connect"), [{"event": "production_connect", "positional": 1,
                                                                    "keys": []}], name)
                self.assertEqual(result.of("dev_connect") + result.of("sql"), [], name)
                self.assertNotIn("synthetic-prod-Pw", result.output(), name)

    def test_web_and_alembic_use_todays_engine(self):
        web = self.run_production(WEB, stub_ui_run=True)
        self.assertEqual(web.of("production_engine"),
                         [{"event": "production_engine", "url_scheme": "postgresql+psycopg2",
                           "options": ["pool_pre_ping", "pool_recycle"]}])
        self.assertEqual(len(web.of("production_connect")), 1)
        alembic = self.run_production(ALEMBIC)
        self.assertEqual([e["mode"] for e in alembic.of("bootstrapped")], ["production"])
        self.assertEqual(len(alembic.of("production_connect")), 1)
        for result in (web, alembic):
            self.assertEqual(result.of("dev_connect") + result.of("sql"), [])

    def test_launcher_refuses_production(self):
        result = self.run_production(LAUNCHER)
        self.assertEqual(result.code, 2)
        self.assertIn("refuses production mode", result.output())
        self.assertEqual([e for e in result.events if e["event"] in CONNECT_EVENTS], [])


class SourceScanTests(unittest.TestCase):
    """No alternate configuration or connection path bypasses the gate."""

    PY_SOURCES = ("app", "scripts", "poller", "migrations", "ops")

    def python_files(self):
        for root in self.PY_SOURCES:
            yield from (REPO / root).rglob("*.py")

    def test_no_dotenv_discovery_in_application_code(self):
        offenders = [str(p.relative_to(REPO)) for p in self.python_files()
                     if re.search(r"\b(load_dotenv|find_dotenv|dotenv_values)\b", p.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [])

    def test_env_template_has_the_strict_profile_shape(self):
        from app import runtime_env as rt

        profile = rt.parse_profile((REPO / ".env.example").read_bytes())
        db, nondb = rt.split_profile(profile)  # no reserved, unknown or unsupported PG keys
        self.assertEqual(sorted(db), sorted(rt.REQUIRED_DB_KEYS))
        self.assertNotIn("DATABASE_URL", profile)
        self.assertTrue(nondb)

    def test_every_database_constructor_is_gated(self):
        allowed = {
            # Development: the verified factory. Production: after the gate in the same function.
            # runtime_env.py only names psycopg2.connect in a docstring; it never connects.
            "app/runtime_env.py", "app/runtime_db.py", "app/contact/database.py", "migrations/env.py",
            "poller/poll_calgary_gtfs_rt_current.py", "scripts/bootstrap_transit_db.py",
        }
        pattern = re.compile(r"\b(psycopg2\.connect|create_engine|engine_from_config|\.connect\(\s*connection_factory)")
        found = {str(p.relative_to(REPO)) for p in self.python_files() if pattern.search(p.read_text(encoding="utf-8"))}
        self.assertEqual(found - allowed, set())
        for path in ("app/contact/database.py", "scripts/bootstrap_transit_db.py",
                     "poller/poll_calgary_gtfs_rt_current.py", "migrations/env.py"):
            text = (REPO / path).read_text(encoding="utf-8")
            self.assertRegex(text, r"runtime_state\.(assert_usable|bootstrap_runtime|bootstrap_entry_point)", path)


if __name__ == "__main__":
    unittest.main()
