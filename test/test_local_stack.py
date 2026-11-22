"""The local stack's driver (ops/local_stack.py) and compose.local.yaml, without Docker.

What must hold: environment files never reach a build context, the policy check refuses a
file the gate would refuse, every port is published on loopback only, Railpack-image
commands are one string (their ENTRYPOINT is bash -c), and the poller is opt-in.
"""
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "ops"))

import local_stack  # noqa: E402

COMPOSE = (REPO / "compose.local.yaml").read_text()


def fake_stat(mode: int, uid: int) -> os.stat_result:
    return os.stat_result((mode, 0, 0, 1, uid, 0, 10, 0, 0, 0))


class ExportTests(unittest.TestCase):
    def test_env_files_are_never_exported(self):
        for path in (".env", ".env.local", "frontend/.env.development.local", "x/.env.production"):
            self.assertTrue(local_stack.is_secret_path(path), path)
        for path in (".env.example", "environment.py", "docs.env.md", "app/envelope.py"):
            self.assertFalse(local_stack.is_secret_path(path), path)

    def test_export_is_tracked_plus_new_unignored_files_from_the_working_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
            subprocess.run(git + ["init", "-q"], cwd=root, check=True)
            (root / ".gitignore").write_text("ignored.txt\n.env.local\n")
            (root / "tracked.txt").write_text("v1")
            (root / "deleted.txt").write_text("x")
            (root / ".env.example").write_text("PGHOST=")
            subprocess.run(git + ["add", "."], cwd=root, check=True)
            subprocess.run(git + ["commit", "-qm", "init"], cwd=root, check=True)
            (root / "tracked.txt").write_text("v2 (uncommitted)")
            (root / "deleted.txt").unlink()
            (root / "new.txt").write_text("new")
            (root / "ignored.txt").write_text("no")
            (root / ".env.local").write_text("PGPASSWORD=secret")
            (root / ".env").write_text("forced")
            subprocess.run(git + ["add", "-f", ".env"], cwd=root, check=True)  # even if someone tracks it

            dest = root / "out"
            count = local_stack.export_source(root, dest)

            exported = sorted(str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file())
            self.assertEqual(exported, [".env.example", ".gitignore", "new.txt", "tracked.txt"])
            self.assertEqual(count, 4)
            self.assertEqual((dest / "tracked.txt").read_text(), "v2 (uncommitted)")


class PolicyTests(unittest.TestCase):
    def test_policy_must_be_a_root_owned_file_nobody_else_can_write(self):
        regular = stat.S_IFREG
        self.assertIsNone(local_stack.policy_problem(fake_stat(regular | 0o644, 0)))
        self.assertEqual(local_stack.policy_problem(fake_stat(regular | 0o644, 501)), "not owned by root")
        self.assertEqual(local_stack.policy_problem(fake_stat(regular | 0o664, 0)), "writable by group or others")
        self.assertEqual(local_stack.policy_problem(fake_stat(regular | 0o646, 0)), "writable by group or others")
        self.assertEqual(local_stack.policy_problem(fake_stat(stat.S_IFLNK | 0o777, 0)), "not a regular file")


class BuildCommandTests(unittest.TestCase):
    def test_plan_secrets_are_read_from_the_railpack_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan.json"
            plan.write_text(json.dumps({"steps": [], "secrets": ["RAILPACK_NODE_VERSION"]}))
            self.assertEqual(local_stack.plan_secrets(plan), ["RAILPACK_NODE_VERSION"])
            plan.write_text(json.dumps({"steps": []}))
            self.assertEqual(local_stack.plan_secrets(plan), [])

    def test_compose_command_names_the_project_files_and_profiles(self):
        command = local_stack.compose(["ops/local-stack/compose.ci.yaml"], "up", "-d", profiles=["poller"])
        self.assertEqual(command[:4], ["docker", "compose", "-p", "bizqlab-local"])
        self.assertIn(str(REPO / "compose.local.yaml"), command)
        self.assertIn(str(REPO / "ops/local-stack/compose.ci.yaml"), command)
        self.assertEqual(command[-4:], ["--profile", "poller", "up", "-d"])

    def test_the_railpack_frontend_matches_the_cli_version(self):
        self.assertTrue(local_stack.RAILPACK_FRONTEND.endswith(f":v{local_stack.RAILPACK_VERSION}"))

    def test_the_poller_is_opt_in(self):
        args = type("Args", (), {"poller": False})()
        self.assertNotIn("poller", local_stack.services_for(args)[0])
        args.poller = True
        self.assertEqual(local_stack.services_for(args), (local_stack.DEFAULT_SERVICES + ["poller"], ["poller"]))


class StartedTests(unittest.TestCase):
    def test_transit_api_counts_as_started_once_it_reaches_its_tables(self):
        self.assertTrue(local_stack.started("transit-api", 503, b'{"ok": false, "status": "degraded"}'))
        self.assertTrue(local_stack.started("transit-api", 200, b'{"ok": true, "status": "healthy"}'))
        self.assertFalse(local_stack.started("transit-api", 503, b'{"ok": false, "status": "unavailable"}'))
        self.assertFalse(local_stack.started("transit-api", 502, b"<html>bad gateway</html>"))

    def test_other_services_need_a_200(self):
        self.assertTrue(local_stack.started("web", 200, b""))
        self.assertFalse(local_stack.started("web", 500, b""))
        self.assertFalse(local_stack.started("dagster", 404, b""))


class ComposeFileTests(unittest.TestCase):
    def test_every_port_is_published_on_loopback_only(self):
        ports = re.findall(r'ports:\s*\[([^\]]*)\]', COMPOSE)
        self.assertEqual(len(ports), 4)
        for entry in ports:
            for mapping in re.findall(r'"([^"]+)"', entry):
                self.assertTrue(mapping.startswith("127.0.0.1:"), mapping)

    def test_railpack_image_commands_are_one_string(self):
        for service in ("bizqlab-dev-start python -m app.main", "bizqlab-dev-start npm run start",
                        "bizqlab-dev-start python -m poller.poll_calgary_gtfs_rt_current"):
            self.assertIn(f'command: ["{service}"]', COMPOSE)

    def test_the_poller_has_a_profile_and_env_local_is_mounted_read_only(self):
        poller = COMPOSE.split("\n  poller:\n", 1)[1].split("\n\n", 1)[0]
        self.assertIn("profiles: [poller]", poller)
        self.assertIn("target: /run/bizqlab/env.local\n  read_only: true", COMPOSE)

    def test_dev_layers_never_copy_the_profile_into_an_image(self):
        for name in ("python.Dockerfile", "node.Dockerfile", "dagster.Dockerfile"):
            text = (REPO / "ops" / "local-stack" / name).read_text()
            copies = [line for line in text.splitlines() if line.startswith("COPY")]
            self.assertFalse([line for line in copies if "env" in line.lower()], name)
            self.assertIn("USER ", text.splitlines()[-1], name)
            self.assertNotIn("USER root", text.splitlines()[-1], name)


if __name__ == "__main__":
    unittest.main()
