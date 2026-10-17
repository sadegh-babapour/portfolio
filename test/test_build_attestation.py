"""Build attestation generators and checkers (design §3.4), for both service build roots.

Generators run against temporary build roots with synthetic Railway identifiers;
the workstation indicators are injected. Each generated marker must be accepted
by the runtime reader of its own build root only, and stale, cross-service,
cross-environment and cross-root markers must be refused. No real marker is
generated in the repository, and nothing connects anywhere.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app import runtime_env as rt
import run_isolated
from ops import check_build_attestation as checker
from ops import write_build_attestation as gen

REPO = Path(__file__).resolve().parents[1]
NODE_GENERATOR = REPO / "backend" / "transit_api" / "scripts" / "writeBuildAttestation.js"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
ENV = {"RAILWAY_PROJECT_ID": "proj-1", "RAILWAY_ENVIRONMENT_ID": "env-1", "RAILWAY_SERVICE_ID": "svc-1"}
NOW = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)
NO_WORKSTATION = lambda: (False, False)  # noqa: E731


def node_write(root: str, env: dict) -> subprocess.CompletedProcess:
    script = ("const g=require(process.argv[1]);"
              "try{console.log(g.writeAttestation(process.argv[2],JSON.parse(process.argv[3]),"
              "{isWorkstation:()=>[false,false]}))}catch(e){console.log('refused:'+e.code);}")
    return subprocess.run(["node", "-e", script, str(NODE_GENERATOR), root, json.dumps(env)],
                          capture_output=True, text=True, timeout=60, check=False)


class GeneratorTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.marker = os.path.join(self.root, rt.ATTESTATION_FILENAME)

    def write(self, env=None, **kwargs):
        return gen.write_attestation(self.root, ENV if env is None else env, now=NOW,
                                     workstation=kwargs.pop("workstation", NO_WORKSTATION), **kwargs)

    def test_written_marker_is_valid_for_this_build_only(self):
        self.assertEqual(self.write({**ENV, rt.COMMIT_KEY: COMMIT}), "written")
        self.assertEqual(os.stat(self.marker).st_mode & 0o777, 0o444)
        doc = json.loads(Path(self.marker).read_text())
        self.assertEqual(doc, {"schema": 1, "kind": "bizqlab-railway-build", "build_root": ".",
                               "railway_service_id": "svc-1", "railway_environment_id": "env-1",
                               "git_commit": COMMIT, "generated_at": "2026-10-16T12:00:00Z"})
        runtime = {**ENV, rt.COMMIT_KEY: COMMIT}
        self.assertEqual(rt.read_attestation(self.root, env=runtime), "valid")
        for env, expected in (
            ({**runtime, "RAILWAY_SERVICE_ID": "svc-2"}, "invalid:service_mismatch"),
            ({**runtime, "RAILWAY_ENVIRONMENT_ID": "env-2"}, "invalid:environment_mismatch"),
            ({**runtime, rt.COMMIT_KEY: "f" * 40}, "invalid:commit_mismatch"),
            (ENV, "invalid:commit_missing"),
        ):
            with self.subTest(expected):
                self.assertEqual(rt.read_attestation(self.root, env=env), expected)
        # The transit-api consumer refuses the Python services' marker.
        self.assertEqual(rt.read_attestation(self.root, build_root="backend/transit_api", env=runtime),
                         "invalid:build_root")

    def test_commit_is_null_without_a_build_commit(self):
        self.write()
        self.assertIsNone(json.loads(Path(self.marker).read_text())["git_commit"])
        self.assertEqual(rt.read_attestation(self.root, env={**ENV, rt.COMMIT_KEY: COMMIT}), "valid")

    def test_missing_or_malformed_identifiers_fail_and_write_nothing(self):
        cases = [
            ({"RAILWAY_ENVIRONMENT_ID": "env-1"}, ("missing_build_identifier", "RAILWAY_SERVICE_ID")),
            ({"RAILWAY_SERVICE_ID": "svc-1"}, ("missing_build_identifier", "RAILWAY_ENVIRONMENT_ID")),
            ({**ENV, "RAILWAY_SERVICE_ID": ""}, ("missing_build_identifier", "RAILWAY_SERVICE_ID")),
            ({**ENV, "RAILWAY_SERVICE_ID": "svc 1"}, ("invalid_build_identifier", "RAILWAY_SERVICE_ID")),
            ({**ENV, "RAILWAY_ENVIRONMENT_ID": "e" * 65}, ("invalid_build_identifier", "RAILWAY_ENVIRONMENT_ID")),
            ({**ENV, rt.COMMIT_KEY: "ABC"}, ("invalid_build_identifier", rt.COMMIT_KEY)),
        ]
        for env, (code, key) in cases:
            with self.subTest(code=code, key=key), self.assertRaises(gen.AttestationRefused) as ctx:
                self.write(env)
            self.assertEqual((ctx.exception.code, ctx.exception.key), (code, key))
            self.assertFalse(os.path.lexists(self.marker))

    def test_workstation_is_refused(self):
        for indicators in ((True, False), (False, True)):
            with self.subTest(indicators), self.assertRaises(gen.AttestationRefused) as ctx:
                self.write(workstation=lambda indicators=indicators: indicators)
            self.assertEqual(ctx.exception.code, "workstation_build_refused")
            self.assertFalse(os.path.lexists(self.marker))

    def test_rebuild_keeps_an_identical_marker_and_refuses_any_other(self):
        self.write()
        before = Path(self.marker).read_bytes()
        later = datetime(2026, 10, 17, 9, 30, 0, tzinfo=timezone.utc)
        self.assertEqual(gen.write_attestation(self.root, ENV, now=later, workstation=NO_WORKSTATION), "unchanged")
        self.assertEqual(Path(self.marker).read_bytes(), before)
        for env in ({**ENV, "RAILWAY_SERVICE_ID": "svc-2"}, {**ENV, "RAILWAY_ENVIRONMENT_ID": "env-2"},
                    {**ENV, rt.COMMIT_KEY: COMMIT}):
            with self.subTest(env), self.assertRaises(gen.AttestationRefused) as ctx:
                self.write(env)
            self.assertEqual(ctx.exception.code, "existing_marker_mismatch")
            self.assertEqual(Path(self.marker).read_bytes(), before)

    def test_unsafe_existing_marker_is_refused(self):
        outside = os.path.join(self.root, "..", os.path.basename(self.root) + "-outside.json")
        cases = {
            "malformed": lambda: Path(self.marker).write_text("{"),
            "other build root": lambda: Path(self.marker).write_text(json.dumps(
                json.loads(gen.render(gen.attestation_document(ENV, NOW, "backend/transit_api"))))),
            "symlink": lambda: (Path(outside).write_bytes(gen.render(gen.attestation_document(ENV, NOW))),
                                os.symlink(outside, self.marker)),
            "directory": lambda: os.mkdir(self.marker),
        }
        expected = {"malformed": "existing_marker_mismatch", "other build root": "existing_marker_mismatch",
                    "symlink": "existing_marker_symlink", "directory": "existing_marker_not_regular"}
        for name, make in cases.items():
            with self.subTest(name):
                if os.path.isdir(self.marker) and not os.path.islink(self.marker):
                    os.rmdir(self.marker)
                elif os.path.lexists(self.marker):
                    os.remove(self.marker)
                make()
                with self.assertRaises(gen.AttestationRefused) as ctx:
                    self.write()
                self.assertEqual(ctx.exception.code, expected[name])
        if os.path.exists(outside):
            os.remove(outside)

    def test_node_generator_marker_is_refused_by_python_and_vice_versa(self):
        node_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, node_root, True)
        result = node_write(node_root, ENV)
        self.assertEqual(result.stdout.strip(), "written", result.stderr)
        self.assertEqual(json.loads(Path(node_root, rt.ATTESTATION_FILENAME).read_text())["build_root"],
                         "backend/transit_api")
        self.assertEqual(rt.read_attestation(node_root, env=ENV), "invalid:build_root")
        self.assertEqual(rt.read_attestation(node_root, build_root="backend/transit_api", env=ENV), "valid")
        self.write()
        self.assertEqual(node_write(self.root, ENV).stdout.strip(), "refused:existing_marker_mismatch")


class CommandTests(unittest.TestCase):
    def run_cli(self, script, env):
        child = run_isolated.isolated_env()
        child.update(env)
        return subprocess.run([sys.executable, script], cwd=REPO, env=child, capture_output=True, text=True,
                              timeout=60, check=False)

    def test_generator_command_without_railway_identifiers_refuses_and_writes_nothing(self):
        marker = REPO / rt.ATTESTATION_FILENAME
        self.assertFalse(marker.exists())
        result = self.run_cli("ops/write_build_attestation.py", {})
        self.assertEqual(result.returncode, 2)
        self.assertIn("missing_build_identifier [key=RAILWAY_SERVICE_ID]", result.stderr)
        self.assertFalse(marker.exists())

    def test_checker_command_reports_absent_without_values(self):
        result = self.run_cli("ops/check_build_attestation.py", {**ENV, "BIZQLAB_RUNTIME": "production"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("attestation: absent", result.stdout)
        self.assertIn("RAILWAY_SERVICE_ID=set", result.stdout)
        self.assertNotIn("svc-1", result.stdout)

    def test_checker_classifies_a_generated_marker(self):
        with tempfile.TemporaryDirectory() as root:
            gen.write_attestation(root, ENV, now=NOW, workstation=NO_WORKSTATION)
            self.assertEqual(checker.main(env=ENV, root=root), 0)
            self.assertEqual(checker.main(env={**ENV, "RAILWAY_SERVICE_ID": "svc-2"}, root=root), 1)

    def test_generated_markers_are_ignored_by_git(self):
        for path in (rt.ATTESTATION_FILENAME, f"backend/transit_api/{rt.ATTESTATION_FILENAME}"):
            result = subprocess.run(["git", "check-ignore", "--no-index", "-q", path], cwd=REPO, check=False)
            self.assertEqual(result.returncode, 0, path)


if __name__ == "__main__":
    unittest.main()
