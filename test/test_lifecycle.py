"""Batch 2 tests: runtime state, revocation boundaries, guarded drivers, engines and Alembic.

Everything runs against a fake psycopg2-shaped driver and an injected filesystem
whose security metadata the tests mutate. The real SQLAlchemy psycopg2 dialect is
used; only its C-typed ``extras`` helpers are replaced. No database, network,
real profile or real policy is touched.
"""
from __future__ import annotations

import argparse
import io
import itertools
import json
import os
import socket
import tempfile
import traceback
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import event, text
from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2
from sqlalchemy.orm import Session

from app import runtime_db, runtime_env as rt, runtime_state
from app.runtime_state import RuntimeInputs, RuntimeRevokedError, RealMetadata
import test_runtime_env as t

REPO = Path(__file__).resolve().parents[1]
SYN_PW = "synthetic-Pw_1"
POLICY = "/Library/Application Support/Bizqlab/db-policy.json"
PROFILE = "/synthetic/repo/.env.local"
BUILD = "/synthetic/build"
IDENTITY = ("portfolio_dev", "portfolio_dev_user", "192.168.1.50", 5432)
MARKERS = {"RAILWAY_PROJECT_ID": "proj-1", "RAILWAY_ENVIRONMENT_ID": "env-1", "RAILWAY_SERVICE_ID": "svc-1"}

FAKE_EXTRAS = SimpleNamespace(
    register_uuid=lambda *a, **k: None,
    register_default_json=lambda *a, **k: None,
    register_default_jsonb=lambda *a, **k: None,
    HstoreAdapter=SimpleNamespace(get_oids=lambda conn: None),
)


# ------------------------------------------------------------- fake driver


class FakeServer:
    """Answers the fake driver and logs ``(connection_number, statement)``."""

    def __init__(self):
        self.identities: list = []
        self.identity = IDENTITY
        self.log: list[tuple[int, str]] = []
        self.connects: list[dict] = []
        self.created: list = []
        self.fail_connect = False
        self.fail_sql: str | None = None
        self.ping_fail_conn: int | None = None

    def next_identity(self):
        return self.identities.pop(0) if self.identities else self.identity

    def statements(self, number: int) -> list[str]:
        return [sql for n, sql in self.log if n == number]

    def non_rollback_since(self, index: int) -> list[str]:
        """Statements logged after ``index``, ignoring ROLLBACK (always permitted)."""
        return [sql for _n, sql in self.log[index:] if sql != "ROLLBACK"]


def make_driver(server: FakeServer):
    mod = types.ModuleType("fake_psycopg2")
    mod.paramstyle = "pyformat"
    mod.apilevel = "2.0"
    mod.threadsafety = 2
    mod.__version__ = "2.9.10 (dt dec pq3 ext lo64)"
    mod.Binary = bytes

    class Error(Exception):
        def __init__(self, message="", pgcode=None):
            super().__init__(message)
            self.pgcode = pgcode

    mod.Error = Error
    for name in ("Warning", "InterfaceError", "DatabaseError"):
        setattr(mod, name, type(name, (Error,), {}))
    for name in ("DataError", "OperationalError", "IntegrityError", "InternalError", "ProgrammingError",
                 "NotSupportedError"):
        setattr(mod, name, type(name, (mod.DatabaseError,), {}))

    class Cursor:
        def __init__(self, conn, name=None):
            self.connection = conn
            self.name = name
            self.rows: list = []
            self.description = None
            self.rowcount = -1
            self.arraysize = 1

        def execute(self, sql, params=None):
            self._run(sql)

        def _run(self, sql):
            # Unguarded internal path, so the fake never routes one cursor method through another.
            conn = self.connection
            if conn.closed:
                raise mod.InterfaceError("connection already closed")
            conn.log(sql)
            if not conn.autocommit:
                conn.in_tx = True
            norm = " ".join(str(sql).split()).lower()
            if server.fail_sql and server.fail_sql in norm:
                raise mod.OperationalError(f"failed on postgresql://u:{SYN_PW}@h/db", pgcode="57P01")
            if norm == "select 1" and server.ping_fail_conn == conn.number:
                conn.closed = 2
                raise mod.OperationalError("server closed the connection unexpectedly")
            rows = self._respond(conn, norm)
            self.rows = list(rows)
            self.rowcount = len(self.rows)
            self.description = ([(f"c{i}", None, None, None, None, None, None) for i in range(len(rows[0]))]
                                if rows else None)

        @staticmethod
        def _respond(conn, norm):
            if norm.startswith("select current_database()"):
                return [conn.identity]
            if "pg_catalog.version()" in norm:
                return [("PostgreSQL 16.4 on aarch64-apple-darwin",)]
            if norm == "select current_schema()":
                return [("public",)]
            if norm.startswith("show standard_conforming_strings"):
                return [("on",)]
            if norm.startswith("show transaction isolation level"):
                return [("read committed",)]
            if norm == "select 1":
                return [(1,)]
            if norm.startswith("select count(*)"):
                return [(0,)]
            return []

        def executemany(self, sql, seq):
            for _params in seq:
                self._run(sql)

        def callproc(self, name, params=None):
            self._run(f"CALL {name}()")

        def copy_expert(self, sql, file, size=8192):
            self._run(sql)

        def copy_from(self, file, table, *args, **kwargs):
            self._run(f"COPY {table} FROM STDIN")

        def copy_to(self, file, table, *args, **kwargs):
            self._run(f"COPY {table} TO STDOUT")

        def fetchone(self):
            return self.rows.pop(0) if self.rows else None

        def fetchall(self):
            rows, self.rows = self.rows, []
            return rows

        def fetchmany(self, size=None):
            size = size or self.arraysize
            rows, self.rows = self.rows[:size], self.rows[size:]
            return rows

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()

    class Connection:
        def __init__(self, dsn, async_=0):
            self.closed = 0
            self.autocommit = False
            self.in_tx = False
            self.cursor_factory = None
            self.readonly = None
            self.deferrable = None
            self.status = 1
            self.server_version = 160004
            self.notices = []
            self.number = 0
            self.identity = server.next_identity()
            server.created.append(self)

        def log(self, sql):
            server.log.append((self.number, str(sql)))

        def cursor(self, name=None, cursor_factory=None, withhold=False, scrollable=None):
            if self.closed:
                raise mod.InterfaceError("connection already closed")
            return (cursor_factory or Cursor)(self, name)

        def commit(self):
            self.log("COMMIT")
            self.in_tx = False

        def rollback(self):
            if self.closed:
                raise mod.InterfaceError("connection already closed")
            self.log("ROLLBACK")
            self.in_tx = False

        def close(self):
            self.closed = 1

        def set_client_encoding(self, encoding):
            self.log("SET client_encoding")

        def set_isolation_level(self, level):
            pass

        def get_transaction_status(self):
            return 2 if self.in_tx else 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            # Like psycopg2 (in C): commit or roll back without calling commit()/rollback().
            self.log("COMMIT" if exc_type is None else "ROLLBACK")
            self.in_tx = False
            return False

    mod.extensions = SimpleNamespace(connection=Connection, cursor=Cursor)

    def connect(dsn=None, connection_factory=None, cursor_factory=None, **kwargs):
        server.connects.append(dict(kwargs, connection_factory=connection_factory))
        if server.fail_connect:
            raise mod.OperationalError(f'could not connect to "postgresql://u:{SYN_PW}@h:5432/db"', pgcode="08001")
        conn = (connection_factory or Connection)("fake dsn")
        conn.number = len(server.connects)
        return conn

    mod.connect = connect
    return mod


# --------------------------------------------------------------- fake fs


def profile_bytes(**overrides) -> bytes:
    values = dict(t.load_fixture("validation_cases.json")["base_profile"])
    values.update(overrides)
    return "".join(f"{k}={v}\n" for k, v in values.items() if v is not None).encode()


class LifecycleFs(t.FakeFs):
    """Resolver provider plus metadata provider over one mutable in-memory tree."""

    KIND_BITS = {"file": 0o100000, "dir": 0o040000, "symlink": 0o120000, "other": 0o010000}

    def __init__(self, *, policy_doc=None, profile: bytes | None = None, production: bool = False):
        fixture = t.load_fixture("policy_cases.json")
        super().__init__({} if policy_doc is None else {"doc": policy_doc}, POLICY, fixture["base_policy"])
        self._ino = itertools.count(100)
        user_dir = {"kind": "dir", "uid": 501, "mode": 0o755, "writable": True}
        for path in ("/synthetic", "/synthetic/repo", BUILD):
            self.entries[path] = dict(user_dir)
        if production:
            del self.entries[POLICY]
            attestation = f"{BUILD}/{rt.ATTESTATION_FILENAME}"
            self.entries[attestation] = {"kind": "file", "uid": 501, "mode": 0o444, "writable": False}
            self.files[attestation] = json.dumps(t.load_fixture("attestation_cases.json")["base_doc"]).encode()
        else:
            self.entries[PROFILE] = {"kind": "file", "uid": 501, "mode": 0o600, "writable": True}
            self.files[PROFILE] = profile_bytes() if profile is None else profile
        for entry in self.entries.values():
            entry.update(ino=next(self._ino), gid=0, mtime=0, ctime=0)
        self.stat_calls = 0

    # metadata provider
    def stat_key(self, path):
        self.stat_calls += 1
        e = self.entries.get(path)
        if e is None:
            return None
        return (1, e["ino"], self.KIND_BITS[e["kind"]] | e["mode"], e["uid"], e["gid"],
                len(self.files.get(path, b"")), e["mtime"], e["ctime"])

    def access_writable(self, path):
        e = self.entries.get(path)
        return bool(e and e["writable"])

    # metadata-only mutations (content unchanged)
    def chmod(self, path, mode):
        self.entries[path].update(mode=mode, ctime=self.entries[path]["ctime"] + 1)

    def chown(self, path, *, uid=None, gid=None):
        e = self.entries[path]
        e.update(uid=e["uid"] if uid is None else uid, gid=e["gid"] if gid is None else gid, ctime=e["ctime"] + 1)

    def grant_acl(self, path):
        self.entries[path].update(writable=True, ctime=self.entries[path]["ctime"] + 1)

    def access_only_change(self, path):
        self.entries[path]["writable"] = True

    def swap_to_symlink(self, path):
        self.entries[path].update(kind="symlink", ino=next(self._ino))

    def replace_identical(self, path):
        self.entries[path]["ino"] = next(self._ino)

    def delete(self, path):
        del self.entries[path]

    def add_sibling(self, directory):
        """An unrelated entry appears in ``directory``: its size and times change, nothing else."""
        sibling = f"{directory}/unrelated-app"
        self.entries[sibling] = {"kind": "dir", "uid": 501, "mode": 0o755, "writable": True,
                                 "ino": next(self._ino), "gid": 20, "mtime": 0, "ctime": 0}
        self.files[directory] = self.files.get(directory, b"") + b"x" * 64  # directory size grows
        e = self.entries[directory]
        e.update(mtime=e["mtime"] + 1, ctime=e["ctime"] + 1)

    def rewrite(self, path, data: bytes):
        self.files[path] = data
        e = self.entries[path]
        e.update(mtime=e["mtime"] + 1, ctime=e["ctime"] + 1)


class RealProfileFs(LifecycleFs):
    """The profile is a real temporary file; everything else stays injected."""

    def __init__(self, real_profile: str):
        super().__init__()
        self.real = real_profile
        self.real_fs = rt.RealFs()
        self.real_meta = RealMetadata()

    def lstat(self, path):
        return self.real_fs.lstat(path) if path == self.real else super().lstat(path)

    def read_nofollow(self, path, max_bytes):
        return self.real_fs.read_nofollow(path, max_bytes) if path == self.real else super().read_nofollow(path, max_bytes)

    def stat_key(self, path):
        return self.real_meta.stat_key(path) if path == self.real else super().stat_key(path)

    def access_writable(self, path):
        return self.real_meta.access_writable(path) if path == self.real else super().access_writable(path)


def assert_sanitized(case: unittest.TestCase, exc: BaseException) -> None:
    case.assertIsNone(exc.__cause__)
    case.assertIsNone(exc.__context__)
    rendered = "".join(traceback.format_exception(exc)) + repr(exc) + str(exc)
    case.assertNotIn(SYN_PW, rendered)
    case.assertNotIn("postgresql://", rendered)


# ------------------------------------------------------------- base class


class RuntimeCase(unittest.TestCase):
    """Fresh runtime state, fake driver and injected inputs; always reset via addCleanup."""

    def setUp(self):
        runtime_state._reset_for_tests()
        self.addCleanup(runtime_state._reset_for_tests)
        self.server = FakeServer()
        self.driver = make_driver(self.server)
        for patcher in (patch.object(runtime_db, "_dbapi", lambda: self.driver),
                        patch.object(PGDialect_psycopg2, "_psycopg2_extras", FAKE_EXTRAS)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.use_fs(LifecycleFs())

    def use_fs(self, fs, env=None):
        self.fs = fs
        self.env = {} if env is None else env
        self.inputs = RuntimeInputs(env=self.env, profile_path=getattr(fs, "real", PROFILE), policy_file=POLICY,
                                    build_root_dir=BUILD, fs=fs, meta=fs, platform="darwin")

    def bootstrap(self, purpose="web"):
        return runtime_state.bootstrap_runtime(purpose, inputs=self.inputs)

    def assert_revoked(self, fn, trigger=None):
        with self.assertRaises(RuntimeRevokedError) as ctx:
            fn()
        if trigger is not None:
            self.assertEqual(ctx.exception.trigger, trigger)
        return ctx.exception

    def revoke_now(self, trigger="test"):
        with self.assertRaises(RuntimeRevokedError):
            runtime_state.revoke(trigger)


# ------------------------------------------------------------------ state


class StateTests(RuntimeCase):
    def test_bootstrap_commits_exports_and_applies_non_db_keys_only_where_unset(self):
        self.use_fs(LifecycleFs(profile=profile_bytes(APP_ENV="development", TRANSIT_API_PORT="4000")),
                    env={"APP_ENV": "preset"})
        state = self.bootstrap()
        self.assertEqual((state.mode, state.status), ("development", runtime_state.ACTIVE))
        dev = state.development
        self.assertEqual(self.env["DATABASE_URL"], dev.database_url)
        self.assertEqual((self.env["PGHOST"], self.env["PGSSLMODE"]), ("192.168.1.50", "disable"))
        self.assertEqual((self.env["APP_ENV"], self.env["TRANSIT_API_PORT"]), ("preset", "4000"))
        self.assertIs(runtime_state.assert_usable(), state)
        self.assertNotIn(SYN_PW, repr(state))

    def test_identical_rebootstrap_is_a_no_op(self):
        state = self.bootstrap()
        env_after = dict(self.env)
        self.assertIs(self.bootstrap(), state)
        self.assertEqual(self.env, env_after)

    def test_different_rebootstrap_revokes(self):
        for change in ("profile", "purpose", "policy"):
            with self.subTest(change):
                runtime_state._reset_for_tests()
                self.use_fs(LifecycleFs())
                self.bootstrap()
                if change == "profile":
                    # The committed env now holds the exported URL, so the changed profile
                    # surfaces as an inherited conflict: an invalid re-bootstrap, which revokes too.
                    self.fs.rewrite(PROFILE, profile_bytes(PGCONNECT_TIMEOUT="20"))
                    with self.assertRaises(rt.RuntimeConfigError) as ctx:
                        self.bootstrap()
                    self.assertEqual((ctx.exception.code, ctx.exception.key), ("inherited_conflict", "DATABASE_URL"))
                    self.assert_revoked(runtime_state.assert_usable, "rebootstrap_invalid")
                    continue
                elif change == "purpose":
                    self.assert_revoked(lambda: self.bootstrap("poller"), "rebootstrap_conflict")
                else:
                    doc = t.load_fixture("policy_cases.json")["base_policy"]
                    doc = {**doc, "development_target": {**doc["development_target"], "server_port": 5433}}
                    self.fs.rewrite(POLICY, json.dumps(doc).encode())
                    self.assert_revoked(self.bootstrap, "rebootstrap_conflict")
                self.assert_revoked(runtime_state.assert_usable, "rebootstrap_conflict")

    def test_invalid_rebootstrap_revokes_and_raises_the_validation_error(self):
        self.bootstrap()
        self.fs.rewrite(PROFILE, b"PGHOST = broken\n")
        with self.assertRaises(rt.RuntimeConfigError) as ctx:
            self.bootstrap()
        self.assertEqual(ctx.exception.code, "profile_space_around_equals")
        self.assert_revoked(runtime_state.assert_usable, "rebootstrap_invalid")

    def test_failed_initial_bootstrap_leaves_environment_byte_identical(self):
        env = {"Z_FIRST": "1", "A_SECOND": "2", "PGHOST": "192.168.1.50"}
        fs = LifecycleFs()
        fs.delete(POLICY)
        self.use_fs(fs, env=env)
        before = list(env.items())
        with self.assertRaises(rt.RuntimeConfigError) as ctx:
            self.bootstrap()
        self.assertEqual(ctx.exception.code, "policy_missing")
        self.assertEqual(list(env.items()), before)
        self.assertIsNone(runtime_state.current_state())
        # Nothing was cached: once the policy exists, the next call resolves from scratch.
        self.use_fs(LifecycleFs(), env=env)
        self.assertEqual(self.bootstrap().mode, "development")

    def test_change_during_bootstrap_is_refused(self):
        fs = LifecycleFs()
        rounds = len(runtime_state.tracked_paths(RuntimeInputs(env={}, profile_path=PROFILE, policy_file=POLICY)))
        original = fs.stat_key

        def changing(path):
            if fs.stat_calls == rounds:  # after the first full traversal
                fs.chmod(PROFILE, 0o640)
            return original(path)

        fs.stat_key = changing
        self.use_fs(fs, env={"KEEP": "1"})
        with self.assertRaises(rt.RuntimeConfigError) as ctx:
            self.bootstrap()
        self.assertEqual(ctx.exception.code, "configuration_changed_during_bootstrap")
        self.assertEqual(self.env, {"KEEP": "1"})
        self.assertIsNone(runtime_state.current_state())

    def test_revocation_is_terminal(self):
        self.bootstrap()
        self.revoke_now("manual")
        self.assert_revoked(self.bootstrap, "manual")
        self.assert_revoked(runtime_state.assert_usable, "manual")
        self.assert_revoked(runtime_db.connect_verified, "manual")

    def test_not_bootstrapped(self):
        for fn in (runtime_state.assert_usable, runtime_db.connect_verified, runtime_db.create_development_engine,
                   runtime_db.get_development_engine):
            with self.assertRaises(runtime_state.RuntimeNotBootstrappedError) as ctx:
                fn()
            self.assertEqual(str(ctx.exception), "runtime_not_bootstrapped")

    def test_environment_drift_revokes(self):
        mutations = [
            ("PGOPTIONS", lambda env: env.__setitem__("PGOPTIONS", "-c search_path=evil")),
            ("DATABASE_URL", lambda env: env.__setitem__("DATABASE_URL", "postgresql://x@db.railway.internal/railway")),
            ("PGHOST", lambda env: env.pop("PGHOST")),
            ("PGPASSWORD", lambda env: env.__setitem__("PGPASSWORD", "other")),
            ("BIZQLAB_RUNTIME", lambda env: env.__setitem__("BIZQLAB_RUNTIME", "production")),
            ("RAILWAY_SERVICE_ID", lambda env: env.__setitem__("RAILWAY_SERVICE_ID", "svc-1")),
        ]
        for key, mutate in mutations:
            with self.subTest(key):
                runtime_state._reset_for_tests()
                self.use_fs(LifecycleFs())
                self.bootstrap()
                mutate(self.env)
                exc = self.assert_revoked(runtime_state.assert_usable, "env_drift")
                self.assertEqual(exc.key, key)
                self.assertNotIn(SYN_PW, str(exc))

    def test_unrelated_environment_change_does_not_revoke(self):
        state = self.bootstrap()
        self.env["HOME"] = "/tmp/elsewhere"
        self.env["pghost"] = "8.8.8.8"
        self.assertIs(runtime_state.assert_usable(), state)

    def test_metadata_only_changes_revoke_with_content_unchanged(self):
        ancestor = "/Library/Application Support/Bizqlab"
        mutations = [
            ("chmod profile", lambda fs: fs.chmod(PROFILE, 0o640)),
            ("chown profile", lambda fs: fs.chown(PROFILE, gid=20)),
            ("chmod policy", lambda fs: fs.chmod(POLICY, 0o444)),
            ("chown policy", lambda fs: fs.chown(POLICY, uid=501)),
            ("chmod ancestor", lambda fs: fs.chmod(ancestor, 0o750)),
            ("chown ancestor", lambda fs: fs.chown("/Library", gid=80)),
            ("ACL on ancestor", lambda fs: fs.grant_acl(ancestor)),
            ("access-only ACL on policy", lambda fs: fs.access_only_change(POLICY)),
            ("symlink swap of profile", lambda fs: fs.swap_to_symlink(PROFILE)),
            ("symlink swap of ancestor", lambda fs: fs.swap_to_symlink(ancestor)),
            ("replacement of ancestor directory", lambda fs: fs.replace_identical(ancestor)),
            ("replacement of root directory", lambda fs: fs.replace_identical("/")),
            ("identical replacement of policy", lambda fs: fs.replace_identical(POLICY)),
            ("deletion of policy", lambda fs: fs.delete(POLICY)),
            ("deletion of profile", lambda fs: fs.delete(PROFILE)),
        ]
        for name, mutate in mutations:
            with self.subTest(name):
                runtime_state._reset_for_tests()
                self.use_fs(LifecycleFs())
                self.bootstrap()
                content = dict(self.fs.files)
                mutate(self.fs)
                self.assertEqual(self.fs.files, content)
                self.assert_revoked(runtime_state.assert_usable, "metadata_changed")

    def test_unrelated_sibling_creation_in_policy_ancestors_does_not_revoke(self):
        state = self.bootstrap()
        for directory in ("/", "/Library", "/Library/Application Support", "/Library/Application Support/Bizqlab"):
            with self.subTest(directory):
                self.fs.add_sibling(directory)
                self.assertIs(runtime_state.assert_usable(), state)
        # The profile and policy themselves still revoke on any change.
        self.fs.rewrite(POLICY, self.fs.files[POLICY])
        self.assert_revoked(runtime_state.assert_usable, "metadata_changed")

    def test_real_ancestor_directory_activity_does_not_revoke(self):
        """Real temporary directories stand in for the policy ancestors."""
        with tempfile.TemporaryDirectory() as tmp:
            meta = RealMetadata()
            ancestor = os.path.join(tmp, "Bizqlab")
            os.mkdir(ancestor)
            inputs = RuntimeInputs(env={}, profile_path=os.path.join(tmp, "profile"),
                                   policy_file=os.path.join(ancestor, "db-policy.json"), meta=meta)
            Path(inputs.profile_path).write_text("x")
            Path(inputs.policy_file).write_text("{}")
            before = runtime_state.file_metadata(inputs)
            os.mkdir(os.path.join(tmp, "unrelated-sibling"))
            Path(ancestor, "unrelated.txt").write_text("y")
            self.assertEqual(runtime_state.file_metadata(inputs), before)
            os.chmod(ancestor, 0o700)
            self.assertNotEqual(runtime_state.file_metadata(inputs), before)

    def test_real_profile_metadata_changes_revoke(self):
        def touch(p):
            st = os.stat(p)
            os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))

        def symlink_swap(p):
            copy = p + ".copy"
            Path(copy).write_bytes(Path(p).read_bytes())
            os.remove(p)
            os.symlink(copy, p)

        for name, mutate in [("chmod", lambda p: os.chmod(p, 0o640)), ("touch", touch),
                             ("symlink swap", symlink_swap), ("delete", os.remove)]:
            with self.subTest(name), tempfile.TemporaryDirectory() as tmp:
                runtime_state._reset_for_tests()
                path = os.path.join(tmp, ".env.local")
                Path(path).write_bytes(profile_bytes())
                os.chmod(path, 0o600)
                self.use_fs(RealProfileFs(path))
                self.bootstrap()
                mutate(path)
                self.assert_revoked(runtime_state.assert_usable, "metadata_changed")

    def test_production_has_no_per_statement_checks_and_no_dev_connections(self):
        self.use_fs(LifecycleFs(production=True), env={"BIZQLAB_RUNTIME": "production", **MARKERS})
        state = self.bootstrap()
        self.assertEqual((state.mode, state.development), ("production", None))
        self.fs.stat_calls = 0
        self.env["PGHOST"] = "10.9.9.9"
        self.assertIs(runtime_state.assert_usable(), state)
        self.assertEqual(self.fs.stat_calls, 0)
        for fn in (runtime_db.connect_verified, runtime_db.create_development_engine):
            with self.assertRaises(rt.RuntimeConfigError) as ctx:
                fn()
            self.assertEqual(ctx.exception.code, "development_only")
        self.assertEqual(self.server.connects, [])

    def test_reset_restores_environment_and_disposes_engines(self):
        original = {"KEEP": "1"}
        self.use_fs(LifecycleFs(), env=dict(original))
        self.bootstrap()
        engine = runtime_db.create_development_engine()
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        pooled = self.server.created[0]
        self.assertEqual(pooled.closed, 0)
        runtime_state._reset_for_tests()
        self.assertEqual(self.env, original)
        self.assertIsNone(runtime_state.current_state())
        self.assertEqual(pooled.closed, 1)


# ------------------------------------------------------------- raw driver


class RawDriverTests(RuntimeCase):
    def test_identity_is_first_and_leaves_no_open_transaction(self):
        state = self.bootstrap()
        conn = runtime_db.connect_verified()
        connection_class, _cursor_class = runtime_db.guarded_classes(self.driver)
        kwargs = dict(self.server.connects[0])
        self.assertIs(kwargs.pop("connection_factory"), connection_class)
        self.assertTrue(issubclass(connection_class, self.driver.extensions.connection))
        self.assertEqual(kwargs, state.development.target.psycopg2_kwargs())
        self.assertIsInstance(conn, connection_class)
        self.assertEqual(self.server.statements(1), [runtime_db.IDENTITY_SQL, "ROLLBACK"])
        self.assertEqual(conn.get_transaction_status(), 0)

    def test_identity_mismatch_closes_revokes_and_sanitizes(self):
        cases = {
            "database": ("other_db", "portfolio_dev_user", "192.168.1.50", 5432),
            "role": ("portfolio_dev", "postgres", "192.168.1.50", 5432),
            "address outside policy": ("portfolio_dev", "portfolio_dev_user", "192.168.1.99", 5432),
            "NULL address": ("portfolio_dev", "portfolio_dev_user", None, 5432),
            "port": ("portfolio_dev", "portfolio_dev_user", "192.168.1.50", 6543),
            "port as text": ("portfolio_dev", "portfolio_dev_user", "192.168.1.50", "5432"),
            "short row": ("portfolio_dev", "portfolio_dev_user"),
        }
        for name, row in cases.items():
            with self.subTest(name):
                runtime_state._reset_for_tests()
                self.server.identity = row
                self.server.created.clear()
                self.bootstrap()
                with self.assertRaises(runtime_db.RuntimeConnectError) as ctx:
                    runtime_db.connect_verified()
                self.assertEqual(ctx.exception.code, "identity_mismatch")
                assert_sanitized(self, ctx.exception)
                self.assertEqual(self.server.created[-1].closed, 1)
                self.assert_revoked(runtime_state.assert_usable, "identity_mismatch")

    def test_equivalent_ipv6_server_address_matches(self):
        doc = t.load_fixture("policy_cases.json")["base_policy"]
        doc = {**doc, "development_target": {**doc["development_target"], "server_addresses": ["fd7a:115c:a1e0::1"]}}
        self.use_fs(LifecycleFs(policy_doc=doc))
        self.server.identity = ("portfolio_dev", "portfolio_dev_user", "fd7a:115c:a1e0:0:0:0:0:1", 5432)
        self.bootstrap()
        self.assertEqual(runtime_db.connect_verified().closed, 0)

    def test_connect_failure_is_sanitized_and_does_not_revoke(self):
        self.bootstrap()
        self.server.fail_connect = True
        with self.assertRaises(runtime_db.RuntimeConnectError) as ctx:
            runtime_db.connect_verified()
        self.assertEqual((ctx.exception.code, ctx.exception.sqlstate), ("connect_failed", "08001"))
        self.assertEqual(ctx.exception.redacted_target, "portfolio_dev_user@192.168.1.50:5432/portfolio_dev")
        assert_sanitized(self, ctx.exception)
        self.assertEqual(runtime_state.current_state().status, runtime_state.ACTIVE)

    def test_identity_query_failure_closes_revokes_and_sanitizes(self):
        self.bootstrap()
        self.server.fail_sql = "current_database()"
        with self.assertRaises(runtime_db.RuntimeConnectError) as ctx:
            runtime_db.connect_verified()
        self.assertEqual((ctx.exception.code, ctx.exception.sqlstate), ("identity_query_failed", "57P01"))
        assert_sanitized(self, ctx.exception)
        self.assertEqual(self.server.created[-1].closed, 1)
        self.assert_revoked(runtime_state.assert_usable, "identity_query_failed")

    def test_context_manager_exit_cannot_commit_after_revocation(self):
        """psycopg2 commits in C on a clean ``with conn:`` exit; the guarded exit checks first."""
        self.bootstrap()
        conn = runtime_db.connect_verified()
        with conn:
            conn.cursor().execute("UPDATE t SET x = 1")
        self.assertEqual(self.server.statements(1)[-1], "COMMIT")
        logged = len(self.server.log)
        with self.assertRaises(RuntimeRevokedError) as ctx:
            with conn:
                conn.cursor().execute("UPDATE t SET x = 2")
                self.env["PGHOST"] = "10.9.9.9"  # drift; nothing raises until the block exits cleanly
        self.assertEqual(ctx.exception.trigger, "env_drift")
        self.assertEqual(self.server.non_rollback_since(logged), ["UPDATE t SET x = 2"])
        self.assertEqual(self.server.statements(1)[-1], "ROLLBACK")
        # An exception inside the block still rolls back as before.
        with self.assertRaises(ZeroDivisionError):
            with conn:
                1 / 0
        self.assertEqual(self.server.statements(1)[-1], "ROLLBACK")

    def test_long_lived_connection_after_revocation(self):
        self.bootstrap()
        conn = runtime_db.connect_verified()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        self.env["PGHOST"] = "10.9.9.9"  # drift, detected at the next boundary without a new connection
        calls = {
            "execute": lambda: cur.execute("UPDATE t SET x = 1"),
            "executemany": lambda: cur.executemany("INSERT INTO t VALUES (%s)", [(1,), (2,)]),
            "callproc": lambda: cur.callproc("p"),
            "copy_expert": lambda: cur.copy_expert("COPY t FROM STDIN", io.StringIO("1\n")),
            "copy_from": lambda: cur.copy_from(io.StringIO("1\n"), "t"),
            "copy_to": lambda: cur.copy_to(io.StringIO(), "t"),
            "new cursor execute": lambda: conn.cursor().execute("SELECT 2"),
            "commit": conn.commit,
        }
        logged = len(self.server.log)
        first = True
        for name, call in calls.items():
            with self.subTest(name):
                exc = self.assert_revoked(call)
                if first:
                    self.assertEqual((exc.trigger, exc.key), ("env_drift", "PGHOST"))
                    first = False
        self.assertEqual(len(self.server.log), logged)
        self.assertEqual(len(self.server.connects), 1)
        conn.rollback()
        self.assertEqual(self.server.log[-1], (1, "ROLLBACK"))
        conn.close()
        self.assertEqual(conn.closed, 1)

    def test_in_flight_commit_refused_rollback_allowed(self):
        self.bootstrap()
        conn = runtime_db.connect_verified()
        conn.cursor().execute("UPDATE t SET x = 1")
        self.assertEqual(conn.get_transaction_status(), 2)
        self.fs.chmod(PROFILE, 0o640)
        self.assert_revoked(conn.commit, "metadata_changed")
        self.assertNotIn((1, "COMMIT"), self.server.log)
        conn.rollback()
        self.assertEqual(conn.get_transaction_status(), 0)

    def test_cursor_factory_rules(self):
        self.bootstrap()
        conn = runtime_db.connect_verified()
        plain = self.driver.extensions.cursor
        with self.assertRaises(rt.RuntimeConfigError) as ctx:
            conn.cursor(cursor_factory=plain)
        self.assertEqual(ctx.exception.code, "unguarded_cursor_factory")
        conn.cursor_factory = plain
        with self.assertRaises(rt.RuntimeConfigError):
            conn.cursor()
        conn.cursor_factory = None
        guarded = runtime_db.guarded_cursor_factory(plain)
        cur = conn.cursor(cursor_factory=guarded)
        cur.execute("SELECT 1")
        for call, code in ((lambda: conn.cursor("named"), "named_cursor_unsupported"),
                           (lambda: conn.cursor(name="named"), "named_cursor_unsupported"),
                           (conn.lobject, "large_objects_unsupported")):
            with self.assertRaises(rt.RuntimeConfigError) as ctx:
                call()
            self.assertEqual(ctx.exception.code, code)
        self.revoke_now()
        self.assert_revoked(lambda: cur.execute("SELECT 1"))


# ------------------------------------------------------------- SQLAlchemy


class EngineTests(RuntimeCase):
    def setUp(self):
        super().setUp()
        self.bootstrap()
        self.engine = runtime_db.create_development_engine()

    def test_identity_precedes_dialect_initialization(self):
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text("select 1")).scalar(), 1)
        statements = self.server.statements(1)
        self.assertEqual(statements[:2], [runtime_db.IDENTITY_SQL, "ROLLBACK"])
        self.assertIn("select pg_catalog.version()", statements[2:])
        self.assertEqual(sum(1 for s in statements if s == runtime_db.IDENTITY_SQL), 1)

    def test_failing_creator_leaves_nothing_checked_out(self):
        self.server.identity = ("other_db", "portfolio_dev_user", "192.168.1.50", 5432)
        with self.assertRaises(runtime_db.RuntimeConnectError) as ctx:
            self.engine.connect()
        assert_sanitized(self, ctx.exception)
        self.assertEqual(self.engine.pool.checkedout(), 0)
        self.assertEqual(self.server.statements(1), [runtime_db.IDENTITY_SQL, "ROLLBACK"])
        self.assert_revoked(runtime_state.assert_usable, "identity_mismatch")

    def test_idle_pooled_checkout_after_file_change(self):
        with self.engine.connect() as conn:
            conn.execute(text("select 1"))
        pooled = self.server.created[0]
        self.fs.chmod(PROFILE, 0o640)
        logged = len(self.server.log)
        self.assert_revoked(self.engine.connect, "metadata_changed")
        self.assertEqual(len(self.server.connects), 1)  # no new physical connection
        self.assertEqual(self.engine.pool.checkedout(), 0)
        self.assertEqual(pooled.closed, 1)
        self.assertEqual(self.server.non_rollback_since(logged), [])

    def test_idle_checkout_is_guarded_without_pre_ping(self):
        # Without pre-ping no statement runs at checkout, so only the checkout listener can refuse.
        engine = runtime_db.create_development_engine(pool_pre_ping=False)
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        self.env["PGOPTIONS"] = "-c search_path=evil"
        logged = len(self.server.log)
        self.assert_revoked(engine.connect, "env_drift")
        self.assertEqual(self.server.non_rollback_since(logged), [])
        self.assertEqual(engine.pool.checkedout(), 0)
        self.assertEqual(self.server.created[-1].closed, 1)

    def test_retained_connection_rejects_statements_after_revocation(self):
        conn = self.engine.connect()
        conn.execute(text("select 1"))
        raw = self.server.created[0]
        self.revoke_now()
        logged = len(self.server.log)
        exc = self.assert_revoked(lambda: conn.execute(text("select 1")))
        self.assertIs(type(exc), RuntimeRevokedError)  # not wrapped by SQLAlchemy
        self.assertEqual(self.server.non_rollback_since(logged), [])
        conn.rollback()
        conn.close()
        self.assertEqual(raw.closed, 1)  # checkin invalidated the retained connection

    def test_statement_listener_guards_engine_paths_on_its_own(self):
        # Defense in depth: with the DBAPI cursor guard disabled, the engine-level
        # before_cursor_execute listener still refuses the statement.
        conn = self.engine.connect()
        conn.execute(text("select 1"))
        self.revoke_now()
        logged = len(self.server.log)
        with patch.object(runtime_db._CursorGuard, "execute",
                          lambda cur, *a, **k: super(runtime_db._CursorGuard, cur).execute(*a, **k)):
            self.assert_revoked(lambda: conn.execute(text("select 1")))
        self.assertEqual(self.server.non_rollback_since(logged), [])
        conn.close()

    def test_raw_statement_guards_each_method_on_its_own(self):
        # Revoke first, so each call below is refused by its own guard alone.
        conn = runtime_db.connect_verified()
        cur = conn.cursor()
        self.revoke_now()
        logged = len(self.server.log)
        for name, call in {
            "execute": lambda: cur.execute("SELECT 1"),
            "executemany": lambda: cur.executemany("INSERT INTO t VALUES (%s)", [(1,)]),
            "callproc": lambda: cur.callproc("p"),
            "copy_expert": lambda: cur.copy_expert("COPY t FROM STDIN", io.StringIO("1\n")),
            "copy_from": lambda: cur.copy_from(io.StringIO("1\n"), "t"),
            "copy_to": lambda: cur.copy_to(io.StringIO(), "t"),
        }.items():
            with self.subTest(name):
                self.assert_revoked(call)
        self.assertEqual(self.server.non_rollback_since(logged), [])

    def test_retained_session_rejects_statements_after_revocation(self):
        session = Session(self.engine)
        self.assertEqual(session.execute(text("select 1")).scalar(), 1)
        self.fs.delete(POLICY)
        self.assert_revoked(lambda: session.execute(text("select 1")), "metadata_changed")
        session.rollback()
        session.close()
        self.assertEqual(self.server.created[0].closed, 1)

    def test_commit_refused_after_revocation_and_rollback_allowed(self):
        conn = self.engine.connect()
        conn.execute(text("UPDATE t SET x = 1"))
        with patch.object(self.engine.dialect, "do_commit", wraps=self.engine.dialect.do_commit) as do_commit:
            self.env["PGSSLMODE"] = "require"
            self.assert_revoked(conn.commit, "env_drift")
            do_commit.assert_not_called()
        self.assertNotIn("COMMIT", self.server.statements(1))
        conn.rollback()
        conn.close()
        self.assertEqual(self.server.created[0].closed, 1)

    def test_commit_guard_runs_before_do_commit(self):
        order = []
        event.listen(self.engine, "commit", lambda conn: order.append("commit event"))
        original = self.engine.dialect.do_commit

        def recording(dbapi_connection):
            order.append("do_commit")
            return original(dbapi_connection)

        with patch.object(self.engine.dialect, "do_commit", side_effect=recording):
            with self.engine.connect() as conn:
                conn.execute(text("UPDATE t SET x = 1"))
                with patch.object(runtime_state, "assert_usable", wraps=runtime_state.assert_usable) as guard:
                    guard.side_effect = lambda: order.append("guard") or runtime_state.current_state()
                    conn.commit()
        self.assertEqual(order[:3], ["guard", "commit event", "do_commit"])
        self.assertIn("COMMIT", self.server.statements(1))

    def test_revocation_disposes_checked_in_connections(self):
        with self.engine.connect() as conn:
            conn.execute(text("select 1"))
        idle = self.server.created[0]
        self.revoke_now()
        self.assertEqual(idle.closed, 1)

    def test_pre_ping_reconnect_is_reverified(self):
        with self.engine.connect() as conn:
            conn.execute(text("select 1"))
        self.server.ping_fail_conn = 1
        with self.engine.connect() as conn:
            conn.execute(text("select 1"))
        self.assertEqual(len(self.server.connects), 2)
        self.assertEqual(self.server.statements(2)[0], runtime_db.IDENTITY_SQL)

    def test_pre_ping_replacement_with_wrong_identity_is_refused(self):
        with self.engine.connect() as conn:
            conn.execute(text("select 1"))
        self.server.ping_fail_conn = 1
        self.server.identity = ("portfolio_dev", "portfolio_dev_user", "192.168.1.99", 5432)
        with self.assertRaises(runtime_db.RuntimeConnectError):
            self.engine.connect()
        self.assertEqual(self.server.statements(2), [runtime_db.IDENTITY_SQL, "ROLLBACK"])
        self.assert_revoked(runtime_state.assert_usable, "identity_mismatch")

    def test_invalidated_connection_is_replaced_and_reverified(self):
        conn = self.engine.connect()
        conn.execute(text("select 1"))
        conn.invalidate()
        conn.rollback()  # SQLAlchemy requires this before reconnecting
        conn.execute(text("select 1"))
        self.assertEqual(self.server.statements(2)[0], runtime_db.IDENTITY_SQL)
        conn.close()

    def test_engine_option_bypass_refused(self):
        for key in ("creator", "module", "connect_args", "url"):
            with self.subTest(key), self.assertRaises(rt.RuntimeConfigError) as ctx:
                runtime_db.create_development_engine(**{key: object()})
            self.assertEqual((ctx.exception.code, ctx.exception.key), ("engine_option_refused", key))

    def test_cached_engine_checks_state_on_every_call(self):
        engine = runtime_db.get_development_engine()
        self.assertIs(runtime_db.get_development_engine(), engine)
        self.env["PGOPTIONS"] = "x"
        self.assert_revoked(runtime_db.get_development_engine, "env_drift")

    def test_engine_url_repr_masks_password(self):
        self.assertNotIn(SYN_PW, repr(self.engine))
        self.assertNotIn(SYN_PW, repr(self.engine.url))


# ----------------------------------------------------------------- Alembic


class AlembicTests(RuntimeCase):
    def setUp(self):
        super().setUp()
        patcher = patch.object(runtime_state, "default_inputs", lambda: self.inputs)
        patcher.start()
        self.addCleanup(patcher.stop)

    def config(self, *, x=None, output=None):
        from alembic.config import Config

        cfg = Config(output_buffer=output, cmd_opts=argparse.Namespace(x=x or []))
        cfg.set_main_option("script_location", str(REPO / "migrations"))
        cfg.set_main_option("prepend_sys_path", str(REPO))
        cfg.set_main_option("path_separator", "os")
        return cfg

    def upgrade(self, cfg, **kwargs):
        from alembic import command

        command.upgrade(cfg, "head", **kwargs)

    def test_identity_failure_runs_nothing_before_create_schema(self):
        self.server.identity = ("portfolio_dev", "postgres", "192.168.1.50", 5432)
        with self.assertRaises(runtime_db.RuntimeConnectError) as ctx:
            self.upgrade(self.config())
        assert_sanitized(self, ctx.exception)
        self.assertEqual([s for _n, s in self.server.log], [runtime_db.IDENTITY_SQL, "ROLLBACK"])

    def test_identity_precedes_create_schema(self):
        self.server.fail_sql = "create schema"  # stop the run at the first DDL
        with self.assertRaises(Exception):
            self.upgrade(self.config())
        statements = self.server.statements(1)
        self.assertEqual(statements[0], runtime_db.IDENTITY_SQL)
        create = [i for i, sql in enumerate(statements) if sql.startswith("CREATE SCHEMA IF NOT EXISTS portfolio")]
        self.assertEqual(len(create), 1)
        self.assertEqual(statements.count(runtime_db.IDENTITY_SQL), 1)
        self.assertEqual(runtime_state.current_state().fingerprint.purpose, "alembic")

    def test_railway_context_without_mode_refused_before_connect(self):
        self.use_fs(LifecycleFs(production=True), env=dict(MARKERS))
        with patch("sqlalchemy.engine_from_config") as engine_from_config:
            with self.assertRaises(rt.RuntimeConfigError) as ctx:
                self.upgrade(self.config())
        self.assertEqual(ctx.exception.code, "railway_context_without_production_mode")
        engine_from_config.assert_not_called()
        self.assertEqual(self.server.connects, [])

    def test_unattested_production_refused_before_connect(self):
        fs = LifecycleFs(production=True)
        fs.delete(f"{BUILD}/{rt.ATTESTATION_FILENAME}")
        self.use_fs(fs, env={"BIZQLAB_RUNTIME": "production", **MARKERS})
        with patch("sqlalchemy.engine_from_config") as engine_from_config:
            with self.assertRaises(rt.RuntimeConfigError) as ctx:
                self.upgrade(self.config())
        self.assertEqual(ctx.exception.code, "production_not_attested")
        engine_from_config.assert_not_called()

    def test_attested_production_uses_todays_parameters_after_the_gate(self):
        url = "postgresql://prod_user:synthetic-prod@prod.example:5432/railway"
        self.use_fs(LifecycleFs(production=True), env={"BIZQLAB_RUNTIME": "production", "DATABASE_URL": url, **MARKERS})
        seen = {}

        class Stop(Exception):
            pass

        def spy(options, prefix, poolclass):
            seen.update(state=runtime_state.current_state(), url=options.get("sqlalchemy.url"), poolclass=poolclass)
            raise Stop()

        with patch.dict(os.environ, {"DATABASE_URL": url}), patch("sqlalchemy.engine_from_config", side_effect=spy):
            with self.assertRaises(Stop):
                self.upgrade(self.config())
        from sqlalchemy.pool import NullPool
        from app.contact.config import normalize_database_url

        self.assertEqual(seen["state"].mode, "production")
        # Exactly today's parameters: ContactSettings' normalized DATABASE_URL and NullPool.
        self.assertEqual((seen["url"], seen["poolclass"]), (normalize_database_url(url), NullPool))
        self.assertEqual(self.server.connects, [])

    def test_x_argument_and_configured_url_refused(self):
        for name, build in (("-x", lambda: self.config(x=["dbname=postgresql://evil"])),
                            ("sqlalchemy.url", lambda: self._with_url())):
            with self.subTest(name), self.assertRaises(rt.RuntimeConfigError) as ctx:
                self.upgrade(build())
            self.assertEqual((ctx.exception.code, ctx.exception.key), ("alembic_override_refused", name))
            self.assertIsNone(runtime_state.current_state())
        self.assertEqual(self.server.connects, [])

    def _with_url(self):
        cfg = self.config()
        cfg.set_main_option("sqlalchemy.url", "postgresql://u:p@db.railway.internal:5432/railway")
        return cfg

    def test_offline_mode_never_bootstraps_or_connects(self):
        output = io.StringIO()
        self.upgrade(self.config(output=output), sql=True)
        self.assertIn("CREATE SCHEMA IF NOT EXISTS portfolio", output.getvalue())
        self.assertIsNone(runtime_state.current_state())
        self.assertEqual(self.server.connects, [])


# --------------------------------------------------------------- isolation


class IsolationGuardTests(unittest.TestCase):
    """Active only under test/run_isolated.py, which loads test/shims/sitecustomize.py first."""

    def setUp(self):
        if os.environ.get("BQ_TEST_ISOLATION") != "1":
            self.skipTest("not running under test/run_isolated.py")
        import sitecustomize

        self.violation = sitecustomize.IsolationViolation

    def test_guards_are_installed(self):
        import dotenv
        import psycopg2

        with self.assertRaises(self.violation):
            psycopg2.connect(host="192.0.2.1", dbname="x")
        with self.assertRaises(self.violation):
            socket.create_connection(("192.0.2.1", 5432))
        with socket.socket() as sock, self.assertRaises(self.violation):
            sock.connect(("192.0.2.1", 5432))
        self.assertIs(dotenv.load_dotenv(), False)
        for path in (REPO / ".env.local", REPO / ".env", POLICY):
            with self.assertRaises(self.violation):
                open(path)
            with self.assertRaises(self.violation):
                os.open(path, os.O_RDONLY)
        for key in os.environ:
            self.assertFalse(key == "DATABASE_URL" or key.startswith(("PG", "RAILWAY_", "BIZQLAB_")), key)


if __name__ == "__main__":
    unittest.main()
