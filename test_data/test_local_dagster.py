"""orchestration/local.py: Dagster in the local stack. No database, no Dagster processes."""
import os
import tempfile
import unittest
from pathlib import Path

from orchestration import local, production


class LocalDagsterTests(unittest.TestCase):
    def test_it_refuses_production(self):
        self.assertEqual(local.refusal("production", lambda: None), "not_development")

    def test_a_failed_identity_check_is_reported_as_its_code(self):
        from app import runtime_env

        def refuse():
            raise runtime_env.RuntimeConfigError("server_identity_mismatch")

        self.assertEqual(local.refusal("development", refuse), "server_identity_mismatch")

        def broken():
            raise OSError("connection to host=10.0.0.2 password=x failed")

        self.assertEqual(local.refusal("development", broken), "OSError")  # no message: it can name hosts

    def test_a_verified_development_database_may_start(self):
        self.assertIsNone(local.refusal("development", lambda: None))

    def test_the_ui_binds_to_loopback_and_reads_the_one_code_server(self):
        command = local.webserver_command()
        self.assertEqual(command[command.index("-h") + 1], "127.0.0.1")
        self.assertEqual(command[command.index("-w") + 1], str(production.WORKSPACE))
        self.assertEqual(command[command.index("-p") + 1], "3000")

    def test_history_stays_on_this_machine(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = local.prepare_home({"DAGSTER_HOME": os.path.join(tmp, "home")})
            config = (home / "dagster.yaml").read_text()
        self.assertEqual(config, local.INSTANCE_CONFIG.read_text())
        self.assertNotIn("postgres", config)  # SQLite under DAGSTER_HOME, never the shared dev DB

    def test_dagster_home_is_required(self):
        with self.assertRaises(RuntimeError):
            local.prepare_home({})


if __name__ == "__main__":
    unittest.main()
