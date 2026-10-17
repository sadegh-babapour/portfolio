"""Batch 1 tests for app.runtime_env: pure resolution and validation.

Every check uses synthetic values, temporary files and injected filesystem
providers. Nothing here reads the real profile or policy, connects to a
database, or touches the network. The cross-language parity test runs the Node
module in a subprocess on generated inputs.
"""
from __future__ import annotations

import itertools
import json
import os
import random
import shutil
import subprocess
import tempfile
import traceback
import unittest
from pathlib import Path, PurePosixPath
from unittest.mock import patch

from app import runtime_env as rt

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "test" / "fixtures"
NODE_MODULE = REPO / "backend" / "transit_api" / "config" / "runtimeEnv.js"
SYNTHETIC_PASSWORD = "synthetic-Pw_1"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def build_bytes(segments) -> bytes:
    out = bytearray()
    for seg in segments:
        if "text" in seg:
            out += seg["text"].encode("utf-8")
        elif "hex" in seg:
            out += bytes.fromhex(seg["hex"])
        else:
            out += (seg["repeat"] * seg["count"]).encode("utf-8")
    return bytes(out)


def expand(value):
    if isinstance(value, dict) and "repeat" in value:
        return value["repeat"] * value["count"]
    return value


def outcome_of(fn):
    """Run ``fn`` and return ``("ok", value)`` or ``("error", (code, key, line))``."""
    try:
        return "ok", fn()
    except rt.RuntimeConfigError as exc:
        return "error", (exc.code, exc.key, exc.line)


def expected_error(expected):
    e = expected["error"]
    return e["code"], e.get("key"), e.get("line")


# ------------------------------------------------------------------- mode


class ModeTableTests(unittest.TestCase):
    def check_case(self, case):
        row, outcome = rt.decide_mode_row(
            case["env"], case["attestation"],
            policy_present=case["policy_present"], profile_present=case["profile_present"],
        )
        self.assertEqual((row, outcome), (case["row"], case["outcome"]), case["name"])

    def test_fixture_rows(self):
        fixture = load_fixture("runtime_mode_cases.json")
        self.assertEqual({c["row"] for c in fixture["cases"]}, set(range(1, 8)))
        for case in fixture["cases"]:
            with self.subTest(case["name"]):
                self.check_case(case)

    def test_named_contexts(self):
        for case in load_fixture("runtime_mode_cases.json")["named_contexts"]:
            with self.subTest(case["name"]):
                self.check_case(case)

    def test_exhaustive_matrix_matches_v4_wording(self):
        for env, attestation, policy, profile, expected in mode_matrix():
            with self.subTest(env=env, attestation=attestation, policy=policy, profile=profile):
                _row, outcome = rt.decide_mode_row(env, attestation, policy_present=policy,
                                                   profile_present=profile)
                got = outcome if outcome in ("production", "development") else "error"
                self.assertEqual(got, expected)

    def test_decide_mode_raises_with_code_only(self):
        with self.assertRaises(rt.RuntimeConfigError) as ctx:
            rt.decide_mode({"BIZQLAB_RUNTIME": "Production"}, "valid", policy_present=False,
                           profile_present=False)
        self.assertEqual(str(ctx.exception), "invalid_mode")

    def test_attestation_is_evaluated_only_for_row_four(self):
        calls = []

        def attestation():
            calls.append(1)
            return "valid"

        markers = {k: "x" for k in rt.MARKER_KEYS}
        rt.decide_mode_row({}, attestation, policy_present=False, profile_present=False)
        rt.decide_mode_row(markers, attestation, policy_present=True, profile_present=False)
        rt.decide_mode_row({"BIZQLAB_RUNTIME": "production"}, attestation, policy_present=False,
                           profile_present=False)
        self.assertEqual(calls, [])
        rt.decide_mode_row({"BIZQLAB_RUNTIME": "production", **markers}, attestation,
                           policy_present=False, profile_present=False)
        self.assertEqual(calls, [1])

    def test_workstation_indicators_use_lstat(self):
        with tempfile.TemporaryDirectory() as tmp:
            dangling = os.path.join(tmp, "dangling")
            os.symlink(os.path.join(tmp, "nowhere"), dangling)
            self.assertEqual(rt.workstation_indicators(dangling, os.path.join(tmp, "absent")),
                             (True, False))


MODE_VALUES = [None, "production", "development", "Production", " production", "", "staging"]
MARKER_VARIANTS = [
    ("absent", {}),
    ("partial-one", {"RAILWAY_SERVICE_ID": "svc"}),
    ("partial-two", {"RAILWAY_PROJECT_ID": "p", "RAILWAY_ENVIRONMENT_ID": "e"}),
    ("complete", {"RAILWAY_PROJECT_ID": "p", "RAILWAY_ENVIRONMENT_ID": "e", "RAILWAY_SERVICE_ID": "s"}),
    ("one-empty", {"RAILWAY_PROJECT_ID": "p", "RAILWAY_ENVIRONMENT_ID": "", "RAILWAY_SERVICE_ID": "s"}),
    ("all-empty", {"RAILWAY_PROJECT_ID": "", "RAILWAY_ENVIRONMENT_ID": "", "RAILWAY_SERVICE_ID": ""}),
]
ATTESTATIONS = ["valid", "absent", "invalid:service_mismatch"]


def mode_matrix():
    """Yield every combination with the outcome stated by verification.md V4 (written independently)."""
    for mode, (marker_name, markers), attestation, policy, profile in itertools.product(
        MODE_VALUES, MARKER_VARIANTS, ATTESTATIONS, (False, True), (False, True)
    ):
        env = dict(markers)
        if mode is not None:
            env["BIZQLAB_RUNTIME"] = mode
        if marker_name == "absent" and mode in (None, "development"):
            expected = "development"
        elif (mode == "production" and marker_name == "complete" and attestation == "valid"
              and not policy and not profile):
            expected = "production"
        else:
            expected = "error"
        yield env, attestation, policy, profile, expected


# ------------------------------------------------------------ attestation


def attestation_content(case, base_doc) -> bytes:
    if "content" in case:
        return build_bytes(case["content"])
    doc = dict(base_doc)
    doc.update(case["doc"]["set"])
    for key in case["doc"]["delete"]:
        doc.pop(key)
    return json.dumps(doc, separators=(",", ":")).encode("utf-8")


def materialize_attestation(tmp: str, case, base_doc) -> str:
    """Lay out the case under ``<tmp>/build`` (the build root); return the root."""
    root = os.path.join(tmp, "build")
    target = os.path.join(root, rt.ATTESTATION_FILENAME)
    content = attestation_content(case, base_doc)
    kind = case["file"]
    if kind == "root_absent":
        return root
    if kind == "root_file":
        Path(root).write_bytes(content)
        return root
    os.mkdir(root)
    if kind == "absent":
        return root
    if kind == "legacy_regular":
        os.mkdir(os.path.join(root, ".bizqlab"))
        Path(root, ".bizqlab", "build-attestation.json").write_bytes(content)
    elif kind == "legacy_parent_symlink_outside":
        outside = os.path.join(tmp, "outside")
        os.mkdir(outside)
        Path(outside, "build-attestation.json").write_bytes(content)
        os.symlink(outside, os.path.join(root, ".bizqlab"))
    elif kind == "regular":
        Path(target).write_bytes(content)
    elif kind == "symlink":
        real = os.path.join(root, "real.json")
        Path(real).write_bytes(content)
        os.symlink(real, target)
    elif kind == "symlink_outside":
        outside = os.path.join(tmp, "outside.json")
        Path(outside).write_bytes(content)
        os.symlink(outside, target)
    elif kind == "dangling_symlink":
        os.symlink(os.path.join(tmp, "nowhere.json"), target)
    elif kind == "directory":
        os.mkdir(target)
    elif kind == "fifo":
        os.mkfifo(target)
    else:
        raise AssertionError(kind)
    return root


class AttestationTests(unittest.TestCase):
    def test_fixture_cases_through_real_files(self):
        fixture = load_fixture("attestation_cases.json")
        for case in fixture["cases"]:
            with self.subTest(case["name"]), tempfile.TemporaryDirectory() as tmp:
                root = materialize_attestation(tmp, case, fixture["base_doc"])
                status = rt.read_attestation(root, build_root=case["build_root"], env=case["env"])
                self.assertEqual(status, case["expected"])

    def test_b1_intermediate_path_swaps_cannot_supply_the_marker(self):
        """B1 regression: swapping the retired ``.bizqlab`` directory around every open has no effect.

        The reader opens only the build root and one file directly inside it, so a valid
        document outside the root, reachable only through ``.bizqlab``, is never accepted.
        """
        base = load_fixture("attestation_cases.json")["base_doc"]
        env = {"RAILWAY_PROJECT_ID": "proj-1", "RAILWAY_ENVIRONMENT_ID": "env-1", "RAILWAY_SERVICE_ID": "svc-1"}
        for marker in (None, {**base, "railway_service_id": "svc-2"}):
            with self.subTest(marker=marker is not None), tempfile.TemporaryDirectory() as tmp:
                root, outside = os.path.join(tmp, "build"), os.path.join(tmp, "outside")
                legacy = os.path.join(root, ".bizqlab")
                os.makedirs(legacy)
                os.mkdir(outside)
                Path(outside, "build-attestation.json").write_text(json.dumps(base))
                if marker is not None:
                    Path(root, rt.ATTESTATION_FILENAME).write_text(json.dumps(marker))
                real_open = os.open

                def swapping_open(path, flags, mode=0o777, *, dir_fd=None):
                    # Alternate .bizqlab between the real directory and an outside symlink.
                    if os.path.islink(legacy):
                        os.unlink(legacy)
                        os.rename(legacy + ".moved", legacy)
                    else:
                        os.rename(legacy, legacy + ".moved")
                        os.symlink(outside, legacy)
                    return real_open(path, flags, mode, dir_fd=dir_fd)

                with patch("os.open", swapping_open):
                    status = rt.read_attestation(root, build_root=".", env=env)
                self.assertEqual(status, "absent" if marker is None else "invalid:service_mismatch")

    def test_marker_replaced_by_symlink_before_open_is_refused(self):
        base = load_fixture("attestation_cases.json")["base_doc"]
        env = {"RAILWAY_PROJECT_ID": "proj-1", "RAILWAY_ENVIRONMENT_ID": "env-1", "RAILWAY_SERVICE_ID": "svc-1"}
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "build")
            os.mkdir(root)
            target = os.path.join(root, rt.ATTESTATION_FILENAME)
            Path(target).write_text(json.dumps({**base, "railway_service_id": "svc-2"}))
            Path(tmp, "outside.json").write_text(json.dumps(base))
            real_open = os.open

            def swapping_open(path, flags, mode=0o777, *, dir_fd=None):
                if path == rt.ATTESTATION_FILENAME:
                    os.remove(target)
                    os.symlink(os.path.join(tmp, "outside.json"), target)
                return real_open(path, flags, mode, dir_fd=dir_fd)

            with patch("os.open", swapping_open):
                self.assertEqual(rt.read_attestation(root, build_root=".", env=env), "invalid:symlink")

    def test_marker_replaced_after_open_reads_the_opened_file(self):
        base = load_fixture("attestation_cases.json")["base_doc"]
        env = {"RAILWAY_PROJECT_ID": "proj-1", "RAILWAY_ENVIRONMENT_ID": "env-1", "RAILWAY_SERVICE_ID": "svc-1"}
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "build")
            os.mkdir(root)
            target = os.path.join(root, rt.ATTESTATION_FILENAME)
            Path(target).write_text(json.dumps({**base, "railway_service_id": "svc-2"}))
            Path(tmp, "outside.json").write_text(json.dumps(base))
            real_open = os.open

            def swapping_open(path, flags, mode=0o777, *, dir_fd=None):
                fd = real_open(path, flags, mode, dir_fd=dir_fd)
                if path == rt.ATTESTATION_FILENAME:
                    os.remove(target)
                    os.symlink(os.path.join(tmp, "outside.json"), target)
                return fd

            with patch("os.open", swapping_open):
                self.assertEqual(rt.read_attestation(root, build_root=".", env=env), "invalid:service_mismatch")

    def test_reader_takes_a_single_component(self):
        for name in ("", ".", "..", ".bizqlab/build-attestation.json"):
            with self.subTest(name), self.assertRaises(ValueError):
                rt.read_in_root("/", name, 1024)

    def test_python_consumer_constant(self):
        self.assertEqual(rt.BUILD_ROOT, ".")


# ---------------------------------------------------------------- grammar


class GrammarTests(unittest.TestCase):
    def test_fixture_cases(self):
        for case in load_fixture("profile_grammar_cases.json")["cases"]:
            with self.subTest(case["name"]):
                kind, value = outcome_of(lambda: rt.parse_profile(build_bytes(case["bytes"])))
                if "ok" in case["expected"]:
                    self.assertEqual((kind, value), ("ok", case["expected"]["ok"]))
                else:
                    self.assertEqual((kind, value), ("error", expected_error(case["expected"])))

    def test_file_cases(self):
        for case in load_fixture("profile_grammar_cases.json")["file_cases"]:
            if case["setup"] == "unreadable" and os.geteuid() == 0:
                continue
            with self.subTest(case["name"]), tempfile.TemporaryDirectory() as tmp:
                path = materialize_profile(tmp, case["setup"])
                kind, value = outcome_of(lambda: rt.read_profile(path))
                if case["expected"] == "ok":
                    self.assertEqual(kind, "ok")
                else:
                    self.assertEqual((kind, value), ("error", (case["expected"], None, None)))


def exact_size_profile(size: int) -> bytes:
    body = bytearray(b"A=1\n")
    while len(body) < size:
        remaining = size - len(body)
        line_len = min(remaining, 2000)
        body += b"#" + b"c" * (line_len - 2) + b"\n" if line_len >= 2 else b"\n"
    return bytes(body)


def materialize_profile(tmp: str, setup: str) -> str:
    path = os.path.join(tmp, ".env.local")
    if setup == "missing":
        return path
    if setup == "symlink":
        real = os.path.join(tmp, "real.env")
        Path(real).write_bytes(b"A=1\n")
        os.symlink(real, path)
    elif setup == "directory":
        os.mkdir(path)
    elif setup == "fifo":
        os.mkfifo(path)
    elif setup == "empty":
        Path(path).write_bytes(b"")
    elif setup == "oversized":
        Path(path).write_bytes(exact_size_profile(rt.PROFILE_MAX_BYTES + 1))
    elif setup == "exact_limit":
        Path(path).write_bytes(exact_size_profile(rt.PROFILE_MAX_BYTES))
        assert os.path.getsize(path) == rt.PROFILE_MAX_BYTES
    elif setup == "unreadable":
        Path(path).write_bytes(b"A=1\n")
        os.chmod(path, 0)
    else:
        raise AssertionError(setup)
    return path


# ------------------------------------------------------------- validation


def validation_inputs(fixture, case):
    profile = dict(fixture["base_profile"])
    for key, value in case["profile"].items():
        if value is None:
            profile.pop(key, None)
        else:
            profile[key] = expand(value)
    target = dict(fixture["base_target"])
    target.update(case["policy"])
    policy = rt.PolicyTarget(
        host=target["host"], port=target["port"], database=target["database"], role=target["role"],
        server_addresses=tuple(target["server_addresses"]), server_port=target["server_port"],
    )
    return profile, policy


def resolution_view(res: rt.DevelopmentResolution) -> dict:
    t = res.target
    return {
        "params": {"host": t.host, "port": t.port, "database": t.database, "user": t.user,
                   "sslmode": t.sslmode, "connect_timeout": t.connect_timeout,
                   "application_name": t.application_name},
        "python_kwargs": t.psycopg2_kwargs(),
        "database_url": res.database_url,
        "nondb_keys": sorted(res.nondb),
    }


class ValidationTests(unittest.TestCase):
    def test_fixture_cases(self):
        fixture = load_fixture("validation_cases.json")
        for case in fixture["cases"]:
            with self.subTest(case["name"]):
                profile, policy = validation_inputs(fixture, case)
                kind, value = outcome_of(lambda: rt.resolve_development_target(
                    profile, policy, inherited_env=case["inherited_env"], purpose=case["purpose"],
                    cli=case["cli"],
                ))
                if "ok" in case["expected"]:
                    self.assertEqual(kind, "ok", value)
                    expected = dict(case["expected"]["ok"])
                    expected.pop("node_config")
                    self.assertEqual(resolution_view(value), expected)
                else:
                    self.assertEqual((kind, value), ("error", expected_error(case["expected"])))

    def test_sqlalchemy_url_object_matches_components(self):
        fixture = load_fixture("validation_cases.json")
        profile, policy = validation_inputs(fixture, {"profile": {"PGPASSWORD": "p@ss:/%#?"}, "policy": {}})
        res = rt.resolve_development_target(profile, policy, inherited_env={}, purpose="web")
        url = res.target.sqlalchemy_url()
        self.assertEqual((url.username, url.password, url.host, url.port, url.database),
                         ("portfolio_dev_user", "p@ss:/%#?", "192.168.1.50", 5432, "portfolio_dev"))
        self.assertEqual(dict(url.query), {"sslmode": "disable", "connect_timeout": "10"})
        self.assertNotIn("p@ss", repr(url))

    def test_round_trip_failure_is_sanitized(self):
        fixture = load_fixture("validation_cases.json")
        profile, policy = validation_inputs(fixture, {"profile": {}, "policy": {}})
        leak = f"postgresql://u:{SYNTHETIC_PASSWORD}@h/db"
        with patch("psycopg2.extensions.parse_dsn", side_effect=ValueError(leak)):
            with self.assertRaises(rt.RuntimeConfigError) as ctx:
                rt.resolve_development_target(profile, policy, inherited_env={}, purpose="web")
        assert_sanitized(self, ctx.exception, "url_round_trip_failed")

    def test_round_trip_mismatch_is_rejected(self):
        fixture = load_fixture("validation_cases.json")
        profile, policy = validation_inputs(fixture, {"profile": {}, "policy": {}})
        with patch("psycopg2.extensions.parse_dsn", return_value={"host": "evil.example"}):
            with self.assertRaises(rt.RuntimeConfigError) as ctx:
                rt.resolve_development_target(profile, policy, inherited_env={}, purpose="web")
        self.assertEqual(ctx.exception.code, "url_round_trip_failed")

    def test_resolution_does_not_mutate_inputs_or_environ(self):
        fixture = load_fixture("validation_cases.json")
        profile, policy = validation_inputs(fixture, {"profile": {}, "policy": {}})
        env = {"PGHOST": "192.168.1.50"}
        before_environ = dict(os.environ)
        before = (dict(profile), dict(env))
        rt.resolve_development_target(profile, policy, inherited_env=env, purpose="web")
        self.assertEqual((profile, env), before)
        self.assertEqual(dict(os.environ), before_environ)


# ----------------------------------------------------------------- policy


class FakeFs:
    """Injected provider built from a policy fixture case (mirrored in the Node tests)."""

    def __init__(self, case, policy_path: str, base_policy):
        chain = [str(p) for p in reversed(PurePosixPath(policy_path).parents)]
        self.entries = {d: {"kind": "dir", "uid": 0, "mode": 0o755, "writable": False} for d in chain}
        self.entries[policy_path] = {"kind": "file", "uid": 0, "mode": 0o644, "writable": False}
        for path, override in case.get("entries", {}).items():
            if override is None:
                self.entries.pop(path, None)
            else:
                merged = dict(self.entries.get(path, {"kind": "dir", "uid": 0, "mode": 0o755, "writable": False}))
                merged.update({k: int(v, 8) if k == "mode" else v for k, v in override.items()})
                self.entries[path] = merged
        if "content" in case:
            self.data = build_bytes(case["content"])
        else:
            self.data = json.dumps(case.get("doc", base_policy), separators=(",", ":")).encode("utf-8")
        self.realpaths = case.get("realpath", {})
        self.read = {k: int(v, 8) if k == "mode" else v for k, v in case.get("read", {}).items()}
        self.files = {policy_path: self.data}

    def _info(self, entry, path):
        return rt.StatInfo(entry["kind"], entry["uid"], entry["mode"], len(self.files.get(path, b"")))

    def lstat(self, path):
        entry = self.entries.get(path)
        return None if entry is None else self._info(entry, path)

    def access_writable(self, path):
        return self.entries[path]["writable"]

    def realpath(self, path):
        return self.realpaths.get(path, path)

    def read_in_root(self, root, name, max_bytes):
        if self.lstat(root) is None:
            raise rt.FileReadError("missing")
        return self.read_nofollow(f"{root}/{name}", max_bytes)

    def read_nofollow(self, path, max_bytes):
        if "error" in self.read:
            raise rt.FileReadError(self.read["error"])
        entry = self.entries.get(path)
        if entry is None:
            raise rt.FileReadError("missing")
        if entry["kind"] == "symlink":
            raise rt.FileReadError("symlink")
        merged = {**entry, **{k: v for k, v in self.read.items() if k != "error"}}
        info = self._info(merged, path)
        if info.kind != "file":
            raise rt.FileReadError("not_regular")
        if info.size > max_bytes:
            raise rt.FileReadError("too_large")
        return self.files[path], info


def policy_view(target: rt.PolicyTarget) -> dict:
    return {"host": target.host, "port": target.port, "database": target.database, "role": target.role,
            "server_addresses": list(target.server_addresses), "server_port": target.server_port}


class PolicyTests(unittest.TestCase):
    def test_fixture_cases(self):
        fixture = load_fixture("policy_cases.json")
        for case in fixture["cases"]:
            with self.subTest(case["name"]):
                fs = FakeFs(case, fixture["policy_path"], fixture["base_policy"])
                kind, value = outcome_of(lambda: rt.load_policy(None, fs, platform=case["platform"]))
                if "ok" in case["expected"]:
                    self.assertEqual(kind, "ok", value)
                    self.assertEqual(policy_view(value), case["expected"]["ok"])
                else:
                    self.assertEqual((kind, value), ("error", expected_error(case["expected"])))

    def test_fixed_paths_ignore_home(self):
        with patch.dict(os.environ, {"HOME": "/tmp/redirected-home"}):
            self.assertEqual(rt.policy_path("darwin"), "/Library/Application Support/Bizqlab/db-policy.json")
            self.assertEqual(rt.policy_path("linux"), "/etc/bizqlab/db-policy.json")
        with self.assertRaises(rt.RuntimeConfigError):
            rt.policy_path("win32")

    def test_real_provider_rejects_user_owned_temp_policy(self):
        if os.geteuid() == 0:
            self.skipTest("running as root")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.realpath(os.path.join(tmp, "db-policy.json"))
            Path(path).write_text(json.dumps(load_fixture("policy_cases.json")["base_policy"]))
            os.chmod(path, 0o444)
            with self.assertRaises(rt.RuntimeConfigError) as ctx:
                rt.load_policy(path)
            self.assertEqual(ctx.exception.code, "policy_not_root_owned")

    def test_real_provider_rejects_symlinked_component(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = os.path.realpath(tmp)
            Path(real, "p.json").write_text("{}")
            os.symlink(real, os.path.join(real, "link"))
            with self.assertRaises(rt.RuntimeConfigError) as ctx:
                rt.load_policy(os.path.join(real, "link", "p.json"))
            # The walk fails at the first non-root-owned or symlinked component.
            self.assertIn(ctx.exception.code, {"policy_not_root_owned", "policy_symlink"})

    def test_relative_or_dotdot_path_rejected(self):
        fs = FakeFs({}, "/Library/Application Support/Bizqlab/db-policy.json", {})
        for path in ("relative/db-policy.json", "/Library/../Library/Application Support/Bizqlab/db-policy.json"):
            with self.assertRaises(rt.RuntimeConfigError) as ctx:
                rt.load_policy(path, fs)
            self.assertEqual(ctx.exception.code, "policy_symlink")


# ------------------------------------------------------------ combined


class ResolveRuntimeTests(unittest.TestCase):
    """resolve_runtime with every file behind an injected provider."""

    POLICY = "/Library/Application Support/Bizqlab/db-policy.json"
    PROFILE = "/synthetic/repo/.env.local"

    def provider(self, profile_bytes: bytes | None, policy_case=None):
        fixture = load_fixture("policy_cases.json")
        fs = FakeFs(policy_case or {}, self.POLICY, fixture["base_policy"])
        if profile_bytes is not None:
            fs.entries["/synthetic"] = {"kind": "dir", "uid": 501, "mode": 0o755, "writable": True}
            fs.entries[self.PROFILE] = {"kind": "file", "uid": 501, "mode": 0o600, "writable": True}
            fs.files[self.PROFILE] = profile_bytes
        return fs

    def profile_bytes(self, **overrides) -> bytes:
        values = dict(load_fixture("validation_cases.json")["base_profile"])
        values.update(overrides)
        return "".join(f"{k}={v}\n" for k, v in values.items()).encode()

    def resolve(self, env, fs, build_root_dir="/synthetic/build"):
        return rt.resolve_runtime(env, purpose="web", profile_path=self.PROFILE, policy_file=self.POLICY,
                                  build_root_dir=build_root_dir, fs=fs)

    def test_development_end_to_end(self):
        result = self.resolve({}, self.provider(self.profile_bytes()))
        self.assertEqual(result.mode, "development")
        self.assertEqual(result.development.target.database, "portfolio_dev")
        self.assertNotIn(SYNTHETIC_PASSWORD, repr(result))

    def test_development_requires_policy(self):
        fs = self.provider(self.profile_bytes(), {"entries": {self.POLICY: None}})
        with self.assertRaises(rt.RuntimeConfigError) as ctx:
            self.resolve({}, fs)
        self.assertEqual(ctx.exception.code, "policy_missing")

    def test_development_requires_profile(self):
        with self.assertRaises(rt.RuntimeConfigError) as ctx:
            self.resolve({}, self.provider(None))
        self.assertEqual(ctx.exception.code, "profile_missing")

    def test_railway_run_on_this_workstation_refused_even_with_forged_attestation(self):
        env = {"BIZQLAB_RUNTIME": "production", **{k: "x" for k in rt.MARKER_KEYS}}
        with self.assertRaises(rt.RuntimeConfigError) as ctx:
            self.resolve(env, self.provider(self.profile_bytes()))
        self.assertEqual(ctx.exception.code, "railway_context_on_workstation")

    def test_attested_production_returns_no_development_target(self):
        base = load_fixture("attestation_cases.json")["base_doc"]
        env = {"BIZQLAB_RUNTIME": "production", "RAILWAY_PROJECT_ID": "proj-1",
               "RAILWAY_ENVIRONMENT_ID": "env-1", "RAILWAY_SERVICE_ID": "svc-1"}
        fs = self.provider(None, {"entries": {self.POLICY: None}})
        for directory in ("/synthetic", "/synthetic/build"):
            fs.entries[directory] = {"kind": "dir", "uid": 501, "mode": 0o755, "writable": True}
        attestation = "/synthetic/build/" + rt.ATTESTATION_FILENAME
        fs.entries[attestation] = {"kind": "file", "uid": 501, "mode": 0o444, "writable": False}
        fs.files[attestation] = json.dumps(base).encode()
        result = self.resolve(env, fs)
        self.assertEqual((result.mode, result.development), ("production", None))
        fs.files[attestation] = json.dumps({**base, "railway_service_id": "svc-2"}).encode()
        with self.assertRaises(rt.RuntimeConfigError) as ctx:
            self.resolve(env, fs)
        self.assertEqual(ctx.exception.code, "production_not_attested")

    def test_environ_untouched(self):
        before = dict(os.environ)
        self.resolve({}, self.provider(self.profile_bytes()))
        self.assertEqual(dict(os.environ), before)


# ----------------------------------------------------------- sanitization


def assert_sanitized(case: unittest.TestCase, exc: BaseException, code: str) -> None:
    case.assertEqual(exc.code, code)
    case.assertIsNone(exc.__cause__)
    case.assertIsNone(exc.__context__)
    rendered = "".join(traceback.format_exception(exc)) + repr(exc) + str(exc)
    case.assertNotIn(SYNTHETIC_PASSWORD, rendered)
    case.assertNotIn("postgresql://", rendered)


class SanitizationTests(unittest.TestCase):
    def test_every_validation_error_omits_the_password(self):
        fixture = load_fixture("validation_cases.json")
        for case in fixture["cases"]:
            if "error" not in case["expected"]:
                continue
            profile, policy = validation_inputs(fixture, case)
            try:
                rt.resolve_development_target(profile, policy, inherited_env=case["inherited_env"],
                                              purpose=case["purpose"], cli=case["cli"])
            except rt.RuntimeConfigError as exc:
                rendered = "".join(traceback.format_exception(exc))
                self.assertNotIn(SYNTHETIC_PASSWORD, rendered, case["name"])
                self.assertNotIn("p@ss", rendered, case["name"])

    def test_grammar_errors_have_no_context_and_no_value(self):
        data = b"PGPASSWORD=" + SYNTHETIC_PASSWORD.encode() + b" #trailing\n"
        with self.assertRaises(rt.RuntimeConfigError) as ctx:
            rt.parse_profile(data)
        assert_sanitized(self, ctx.exception, "profile_unquoted_hash")
        with self.assertRaises(rt.RuntimeConfigError) as ctx:
            rt.parse_profile(b"PGPASSWORD=" + SYNTHETIC_PASSWORD.encode() + b"\xff\n")
        assert_sanitized(self, ctx.exception, "profile_invalid_utf8")

    def test_file_read_errors_have_no_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(rt.RuntimeConfigError) as ctx:
                rt.read_profile(os.path.join(tmp, "missing"))
            assert_sanitized(self, ctx.exception, "profile_missing")
            real = os.path.join(tmp, "r")
            Path(real).write_text("A=1\n")
            os.symlink(real, os.path.join(tmp, "l"))
            with self.assertRaises(rt.RuntimeConfigError) as ctx:
                rt.read_profile(os.path.join(tmp, "l"))
            assert_sanitized(self, ctx.exception, "profile_symlink")

    def test_policy_parse_error_has_no_context(self):
        fixture = load_fixture("policy_cases.json")
        fs = FakeFs({"content": [{"text": '{"password": "' + SYNTHETIC_PASSWORD + '"'}]},
                    fixture["policy_path"], fixture["base_policy"])
        with self.assertRaises(rt.RuntimeConfigError) as ctx:
            rt.load_policy(None, fs, platform="darwin")
        assert_sanitized(self, ctx.exception, "policy_malformed")

    def test_representations_mask_password(self):
        fixture = load_fixture("validation_cases.json")
        profile, policy = validation_inputs(fixture, {"profile": {}, "policy": {}})
        res = rt.resolve_development_target(profile, policy, inherited_env={}, purpose="web")
        for text in (repr(res), str(res), repr(res.target), str(res.target)):
            self.assertNotIn(SYNTHETIC_PASSWORD, text)
            self.assertIn("***", text)


# --------------------------------------------------- Python / Node parity

NODE_HARNESS = r"""
const r = require(process.argv[1]);
const chunks = [];
process.stdin.on("data", (c) => chunks.push(c)).on("end", () => {
  const job = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  const run = (fn) => {
    try { return { ok: fn() }; } catch (e) {
      if (e instanceof r.RuntimeConfigError) return { error: [e.code, e.key, e.line] };
      return { thrown: e.constructor.name };
    }
  };
  const norm = (v) => {
    if (v instanceof r.JsonFloat) return { $float: v.text };
    if (Array.isArray(v)) return v.map(norm);
    if (v !== null && typeof v === "object") {
      const out = {};
      for (const k of Object.keys(v)) out[k] = norm(v[k]);
      return { $object: Object.keys(v).sort().map((k) => [k, out[k]]) };
    }
    return v;
  };
  const out = {
    mode: job.mode.map(([env, att, pol, prof]) => r.decideModeRow(env, att, { policyPresent: pol, profilePresent: prof })),
    profiles: job.profiles.map((hex) => run(() => r.parseProfile(Buffer.from(hex, "hex")))),
    json: job.json.map((hex) => {
      try { return { ok: norm(r.parseStrictJson(Buffer.from(hex, "hex"))) }; } catch { return { error: true }; }
    }),
    hosts: job.hosts.map((h) => run(() => r.validateHost(h))),
    urls: job.urls.map(([profile, policy, url]) => run(() => r.resolveDevelopmentTarget(profile, policy, {
      inheritedEnv: { DATABASE_URL: url }, purpose: "web",
    }).target.host)),
    ports: job.ports.map((p) => run(() => r.validatePortText(p))),
  };
  process.stdout.write(JSON.stringify(out));
});
"""


def _norm_json(value):
    if isinstance(value, rt.JsonFloat):
        return {"$float": value.text}
    if isinstance(value, list):
        return [_norm_json(v) for v in value]
    if isinstance(value, dict):
        return {"$object": [[k, _norm_json(value[k])] for k in sorted(value)]}
    return value


def _fuzz(rng: random.Random, fragments, count: int, max_len: int) -> list:
    return ["".join(rng.choice(fragments) for _ in range(rng.randint(0, max_len))) for _ in range(count)]


class ParityTests(unittest.TestCase):
    """Differential check: Python and Node must agree on generated inputs, not only fixtures."""

    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")

    def setUp(self):
        if not self.node:
            self.skipTest("node not on PATH")

    def test_python_and_node_agree_on_generated_inputs(self):
        rng = random.Random(20261016)
        profile_fragments = ["A", "PG", "B_1", "=", '"', "'", " ", "\t", "#", "$", "{", "${", "\r", "\n", "\r\n",
                             "é", "😀", "\x00", "\x01", "\x7f", "\u0085", " ", "﻿", "export ", "x", "a"]
        profiles = [s.encode("utf-8") for s in _fuzz(rng, profile_fragments, 3000, 30)]
        # Well-formed KEY=VALUE lines with fuzzed values, so value-level rules are reached.
        value_fragments = ["x", "é", " ", "\t", "#", " #", "\t#", '"', "'", "$", "${", "=", "\x7f", "a b"]
        profiles += [
            "".join(
                rng.choice(["A", "PG_1", "B"]) + "=" + "".join(_fuzz(rng, value_fragments, 1, 6)) + rng.choice(["\n", "\r\n"])
                for _ in range(rng.randint(1, 3))
            ).encode("utf-8")
            for _ in range(3000)
        ]
        profiles += [bytes(rng.choice([0x41, 0x3D, 0x0A, 0x0D, 0x80, 0xC3, 0xA9, 0xED, 0xA0, 0xFF, 0xF4, 0x90, 0x20])
                           for _ in range(rng.randint(1, 12))) for _ in range(1000)]
        json_fragments = ["{", "}", "[", "]", '"a"', '"b"', '"1"', ":", ",", "1", "-", "0", "01", ".5", "e3", "E-2",
                          "true", "null", "fals", " ", "\n", '"\\u00e9"', '"\\ud83d\\ude00"', '"\\ud800"', '"\\x"',
                          '"é"', "\\", '"', "\x01", "NaN", "Infinity", "12345678901234567"]
        json_inputs = [s.encode("utf-8") for s in _fuzz(rng, json_fragments, 3000, 12)]
        host_fragments = ["1", "0", "9", "25", "255", "256", "10", "192", "168", ".", ":", "::", "a", "f", "ffff",
                          "fd", "fe80", "x", "-", "%", "[", "]", "railway", "rlwy.net", "é", "A", "0x", "lan"]
        hosts = _fuzz(rng, host_fragments, 3000, 9)
        ports = _fuzz(rng, ["0", "1", "5", "9", "6", "+", "-", " ", "٣", "５", "\n"], 1000, 6)
        modes = [list(m[:4]) for m in mode_matrix()]
        validation = load_fixture("validation_cases.json")
        url_cases = []
        password_choices = ["synthetic-Pw_1", "p@ss:/%#?&=+ w\"'\\é😀", "a+b", "~._-"]
        url_fragments = ["postgresql+psycopg2://", "postgresql://", "postgres://", "portfolio_dev_user", "%70",
                         "%5f", "%5F", ":", "@", "192.168.1.50", "[fd7a:115c:a1e0::1]", "5432", "05432", "/",
                         "portfolio_dev", "?", "&", "sslmode=disable", "sslmode=require", "connect_timeout=10",
                         "connect_timeout=010", "application_name=bizqlab-dev-web", "host=evil", "=", "#", "+",
                         "%2B", "%2b", "%40", "%ff", "%G", " ", "é", ",", "synthetic-Pw_1", "%73ynthetic-Pw_1"]
        for i in range(3000):
            password = rng.choice(password_choices)
            target = rt.DevelopmentTarget(
                host="192.168.1.50", port=5432, database="portfolio_dev", user="portfolio_dev_user",
                password=password, sslmode="disable", connect_timeout=10,
                application_name="bizqlab-dev-web", explicit_options=())
            if i % 3 == 0:  # structurally plausible: mutate a canonical URL
                url = rt.compose_database_url(target)
                for _ in range(rng.randint(0, 3)):
                    pos = rng.randint(0, len(url))
                    url = url[:pos] + rng.choice(url_fragments) + url[pos + rng.randint(0, 3):]
            elif i % 3 == 1:  # reordered or re-encoded but equal
                head, query = rt.compose_database_url(target).split("?")
                items = query.split("&") + (["application_name=bizqlab-dev-web"] if rng.random() < 0.5 else [])
                rng.shuffle(items)
                url = head + "?" + "&".join(items)
                if rng.random() < 0.5:
                    url = url.replace("postgresql+psycopg2://", "postgresql://")
            else:
                url = "".join(_fuzz(rng, url_fragments, 1, 14))
            profile = {**validation["base_profile"], "PGPASSWORD": password}
            url_cases.append((profile, validation["base_target"], url))

        job = {"mode": modes, "profiles": [p.hex() for p in profiles], "json": [j.hex() for j in json_inputs],
               "hosts": hosts, "ports": ports,
               "urls": [[p, {"host": t["host"], "port": t["port"], "database": t["database"], "role": t["role"]}, u]
                        for p, t, u in url_cases]}
        proc = subprocess.run([self.node, "-e", NODE_HARNESS, str(NODE_MODULE)], input=json.dumps(job),
                              capture_output=True, text=True, timeout=120, check=False,
                              env={"PATH": os.environ.get("PATH", "")})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        node = json.loads(proc.stdout)

        def run(fn):
            kind, value = outcome_of(fn)
            return {"ok": value} if kind == "ok" else {"error": list(value)}

        def run_json(data):
            try:
                return {"ok": _norm_json(rt.parse_strict_json(data))}
            except Exception:  # noqa: BLE001 - any refusal counts as an error for parity
                return {"error": True}

        py = {
            "mode": [list(rt.decide_mode_row(e, a, policy_present=p, profile_present=q)) for e, a, p, q in modes],
            "profiles": [run(lambda d=d: rt.parse_profile(d)) for d in profiles],
            "json": [run_json(d) for d in json_inputs],
            "hosts": [run(lambda h=h: rt.validate_host(h)) for h in hosts],
            "urls": [run(lambda p=p, t=t, u=u: rt.resolve_development_target(
                p, rt.PolicyTarget(t["host"], t["port"], t["database"], t["role"],
                                   tuple(t["server_addresses"]), t["server_port"]),
                inherited_env={"DATABASE_URL": u}, purpose="web").target.host) for p, t, u in url_cases],
            "ports": [run(lambda p=p: rt.validate_port_text(p)) for p in ports],
        }
        for section in py:
            mismatches = [(i, py[section][i], node[section][i])
                          for i in range(len(py[section])) if py[section][i] != node[section][i]]
            self.assertEqual(mismatches[:5], [], section)
            self.assertEqual(len(py[section]), len(node[section]))
        # The generated inputs must exercise both outcomes, or the comparison proves little.
        for section in ("profiles", "json", "hosts", "ports", "urls"):
            kinds = {next(iter(item)) for item in py[section]}
            self.assertEqual(kinds, {"ok", "error"}, section)


if __name__ == "__main__":
    unittest.main()
