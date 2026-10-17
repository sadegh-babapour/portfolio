"""Test-only harness for exact entry-command subprocess tests (test/test_entrypoints.py).

Loaded by sitecustomize.py when BQ_ENTRYPOINT_SCENARIO names a scenario JSON file.
Production code contains none of this. Patches are applied by a post-import hook
the moment the entry point itself imports app.runtime_state / app.runtime_db, so
nothing here puts the repository root on sys.path or imports the application early.

- app.runtime_state.default_inputs -> synthetic profile/policy/attestation provider
  (test_lifecycle.LifecycleFs), with the real process environment.
- app.runtime_db._dbapi -> the fake psycopg2 driver (test_lifecycle.make_driver).
- psycopg2.connect (production paths) -> recorded, then refused.
- dotenv discovery -> recorded (it must never be called).
- nicegui ui.run (web only, when requested) -> one statement through session_scope, then exit 0.
Every event is appended to the scenario's JSON-lines log as it happens.
"""
from __future__ import annotations

import importlib.abc
import importlib.machinery
import json
import os
import sys

_SCENARIO: dict = {}
_TARGETS = {"app.runtime_state", "app.runtime_db", "app.contact.database", "psycopg2", "nicegui"}


def record(event: str, **fields) -> None:
    with open(_SCENARIO["log"], "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": event, **fields}) + "\n")


class _Loader(importlib.abc.Loader):
    def __init__(self, inner, fullname):
        self.inner, self.fullname = inner, fullname

    def create_module(self, spec):
        return self.inner.create_module(spec)

    def exec_module(self, module):
        self.inner.exec_module(module)
        _patch(self.fullname, module)


class _Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname not in _TARGETS:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is not None and spec.loader is not None:
            spec.loader = _Loader(spec.loader, fullname)
        return spec


_SERVER = None


def _server():
    global _SERVER
    if _SERVER is None:
        import test_lifecycle as tl

        class LoggingServer(tl.FakeServer):
            def __init__(self):
                super().__init__()
                self.log = _LoggedList()

        _SERVER = LoggingServer()
        identity = _SCENARIO.get("identity")
        if identity is not None:
            _SERVER.identity = tuple(identity)
    return _SERVER


class _LoggedList(list):
    def append(self, item):
        super().append(item)
        record("sql", connection=item[0], statement=" ".join(str(item[1]).split()))


def _inputs(module):
    """Synthetic resolver inputs over the real process environment (built on first use)."""
    import test_lifecycle as tl
    from app import runtime_env as rt

    fs_spec = _SCENARIO.get("fs", {})
    production = fs_spec.get("kind") == "production"
    profile = None if production else tl.profile_bytes(**fs_spec.get("profile_overrides", {}))
    fs = tl.LifecycleFs(profile=profile, production=production)
    if fs_spec.get("policy_absent"):
        fs.delete(tl.POLICY)
    if production and "attestation" in fs_spec:
        path = f"{tl.BUILD}/{rt.ATTESTATION_FILENAME}"
        if fs_spec["attestation"] is None:
            fs.delete(path)
        else:
            fs.files[path] = json.dumps(fs_spec["attestation"]).encode()
    return module.RuntimeInputs(env=os.environ, profile_path=tl.PROFILE, policy_file=tl.POLICY,
                                build_root_dir=tl.BUILD, fs=fs, meta=fs, platform="darwin")


_DRIVER = None


def _driver():
    global _DRIVER
    if _DRIVER is None:
        import test_lifecycle as tl
        from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2

        driver = tl.make_driver(_server())
        real_connect = driver.connect

        def connect(*args, **kwargs):
            record("dev_connect", keys=sorted(k for k in kwargs if k != "password"))
            return real_connect(*args, **kwargs)

        driver.connect = connect
        PGDialect_psycopg2._psycopg2_extras = tl.FAKE_EXTRAS
        _DRIVER = driver
    return _DRIVER


def _patch(name: str, module) -> None:
    if name == "app.runtime_state":
        cache = []

        def default_inputs():
            if not cache:
                cache.append(_inputs(module))
            return cache[0]

        module.default_inputs = default_inputs
        real_bootstrap = module.bootstrap_runtime

        def bootstrap_runtime(purpose, *, cli=None, inputs=None):
            record("bootstrap", purpose=purpose, cli={k: v is not None for k, v in (cli or {}).items()})
            state = real_bootstrap(purpose, cli=cli, inputs=inputs)
            record("bootstrapped", purpose=purpose, mode=state.mode)
            return state

        module.bootstrap_runtime = bootstrap_runtime
    elif name == "app.runtime_db":
        module._dbapi = _driver
    elif name == "app.contact.database":
        real = module.create_engine

        def create_engine(url, *args, **kwargs):
            record("production_engine", url_scheme=str(url).split("://", 1)[0], options=sorted(kwargs))
            return real(url, *args, **kwargs)

        module.create_engine = create_engine
    elif name == "psycopg2":
        def refused(*args, **kwargs):
            record("production_connect", positional=len(args), keys=sorted(k for k in kwargs if k != "password"))
            raise RuntimeError("blocked by test isolation")

        module.connect = refused
    elif name == "nicegui" and _SCENARIO.get("stub_ui_run"):
        def run(**kwargs):
            record("ui_run", port=kwargs.get("port"))
            from sqlalchemy import text
            from app.contact.database import session_scope

            with session_scope() as session:
                session.execute(text("select 1"))
            raise SystemExit(0)

        module.ui.run = run


def _guard_dotenv() -> None:
    try:
        import dotenv
    except ImportError:
        return
    for attr in ("load_dotenv", "find_dotenv", "dotenv_values"):
        def called(*_a, _attr=attr, **_k):
            record("dotenv", function=_attr)
            return {} if _attr == "dotenv_values" else ("" if _attr == "find_dotenv" else False)

        setattr(dotenv, attr, called)


def install(path: str) -> None:
    with open(path, encoding="utf-8") as fh:
        _SCENARIO.update(json.load(fh))
    # psycopg2 and dotenv may already be imported by sitecustomize; patch them in place.
    if "psycopg2" in sys.modules:
        _patch("psycopg2", sys.modules["psycopg2"])
    _guard_dotenv()
    sys.meta_path.insert(0, _Finder())
