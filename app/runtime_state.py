"""Runtime authorization state, fingerprint and revocation (M1 design §8).

In plain words: each process (web, poller, alembic, a pipeline) calls
bootstrap_entry_point once at start. The decision from runtime_env is frozen here. On a
developer machine every database call re-checks it, and if the environment variables
changed underneath the process, the state is revoked and stays revoked.


Batch 2. ``bootstrap_runtime`` resolves the runtime with the Batch 1 resolver
(``app.runtime_env``), then commits an immutable ``RuntimeState`` under a lock.
``assert_usable`` re-checks that state at every guarded boundary in
development; any failure revokes it, and revocation is terminal. Production has
no per-statement checks (design §8.5).

Nothing here connects to a database. Process entry points call
``bootstrap_entry_point`` before any configuration-dependent import or I/O.
"""
from __future__ import annotations

import hashlib
import os
import sys
import threading
from dataclasses import dataclass, replace
from pathlib import PurePosixPath
from typing import Callable, Mapping, MutableMapping

from app import runtime_env as rt

ACTIVE = "active"
REVOKED = "revoked"

# DB settings plus the mode inputs: any change after commit revokes (design §8.1).
SNAPSHOT_KEYS = (rt.DATABASE_URL_KEY, rt.RUNTIME_KEY, *rt.MARKER_KEYS, rt.COMMIT_KEY)
SNAPSHOT_PREFIXES = ("PG",)


class RuntimeNotBootstrappedError(rt.RuntimeConfigError):
    def __init__(self):
        super().__init__("runtime_not_bootstrapped")


class RuntimeRevokedError(rt.RuntimeConfigError):
    """Raised at every boundary once the state is revoked. ``trigger`` says why; never a value."""

    def __init__(self, trigger: str, *, key: str | None = None):
        super().__init__("runtime_revoked", key=key)
        self.trigger = trigger
        message = f"runtime_revoked [trigger={trigger}]"
        if key is not None:
            message += f" [key={key}]"
        self.args = (message,)


# ----------------------------------------------------------------- inputs


class RealMetadata:
    """Security metadata of a path, without following a final symlink.

    ``stat_key`` is ``(dev, ino, mode, uid, gid, size, mtime_ns, ctime_ns)``; ``mode``
    includes the file-type bits.
    """

    def stat_key(self, path) -> tuple | None:
        try:
            st = os.lstat(path)
        except (FileNotFoundError, NotADirectoryError):
            return None
        return (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid, st.st_size,
                st.st_mtime_ns, st.st_ctime_ns)

    def access_writable(self, path) -> bool:
        return os.access(path, os.W_OK)


@dataclass(frozen=True)
class RuntimeInputs:
    """Everything bootstrap reads. ``default_inputs()`` is the real process; tests inject fakes."""

    env: MutableMapping[str, str]
    profile_path: object = rt.PROFILE_PATH
    policy_file: str | None = None  # None: the fixed path for the platform
    build_root_dir: object = rt.REPO_ROOT
    fs: object = None  # app.runtime_env provider (RealFs by default)
    meta: object = None  # metadata provider (RealMetadata by default)
    platform: str | None = None

    def provider(self):
        return rt.RealFs() if self.fs is None else self.fs

    def metadata(self):
        return RealMetadata() if self.meta is None else self.meta

    def policy_path(self) -> str | None:
        if self.policy_file is not None:
            return self.policy_file
        try:
            return rt.policy_path(self.platform)
        except rt.RuntimeConfigError:
            return None


def default_inputs() -> RuntimeInputs:
    return RuntimeInputs(env=os.environ)


# ------------------------------------------------------------ fingerprint


def _digest(value: bytes | str) -> str:
    data = value.encode("utf-8", "surrogatepass") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def env_snapshot(env: Mapping[str, str]) -> tuple:
    """Presence and (digested) value of every snapshot key, sorted."""
    return tuple(sorted(
        (key, _digest(value)) for key, value in env.items()
        if key in SNAPSHOT_KEYS or key.startswith(SNAPSHOT_PREFIXES)
    ))


def tracked_entries(inputs: RuntimeInputs) -> tuple[tuple[str, bool], ...]:
    """``(path, is_ancestor_directory)``: the profile, each policy ancestor, then the policy file."""
    entries = [(os.fspath(inputs.profile_path), False)]
    policy = inputs.policy_path()
    if policy is not None:
        pure = PurePosixPath(policy)
        entries += [(str(p), True) for p in reversed(pure.parents)] + [(policy, False)]
    return tuple(entries)


def tracked_paths(inputs: RuntimeInputs) -> tuple[str, ...]:
    return tuple(path for path, _ancestor in tracked_entries(inputs))


# Ancestor directories keep identity, type, owner, group and mode only (plus the
# access check below). Their size and times change whenever an unrelated sibling
# is created, so they are not part of the fingerprint. Files keep every field.
_ANCESTOR_FIELDS = 5  # dev, ino, mode (with type bits), uid, gid


def file_metadata(inputs: RuntimeInputs) -> tuple:
    meta = inputs.metadata()
    out = []
    for path, ancestor in tracked_entries(inputs):
        key = meta.stat_key(path)
        if key is not None and ancestor:
            key = key[:_ANCESTOR_FIELDS]
        out.append((path, key, key is not None and meta.access_writable(path)))
    return tuple(out)


@dataclass(frozen=True, repr=False)
class Fingerprint:
    mode: str
    purpose: str
    target: tuple | None
    env: tuple
    files: tuple
    digests: tuple

    def __repr__(self) -> str:
        return f"Fingerprint(mode={self.mode!r}, purpose={self.purpose!r}, files={len(self.files)})"


def _target_key(resolution: rt.RuntimeResolution) -> tuple | None:
    dev = resolution.development
    if dev is None:
        return None
    t, p = dev.target, dev.policy
    return (t.host, t.port, t.database, t.user, _digest(t.password), t.sslmode, t.connect_timeout,
            t.application_name, t.explicit_options,
            None if p is None else (p.server_addresses, p.server_port), tuple(sorted(dev.nondb)))


@dataclass(frozen=True, repr=False)
class RuntimeState:
    mode: str
    status: str
    resolution: rt.RuntimeResolution
    fingerprint: Fingerprint
    inputs: RuntimeInputs
    trigger: str | None = None

    @property
    def development(self) -> rt.DevelopmentResolution | None:
        return self.resolution.development

    def __repr__(self) -> str:
        return (f"RuntimeState(mode={self.mode!r}, status={self.status!r}, trigger={self.trigger!r}, "
                f"resolution={self.resolution!r})")

    __str__ = __repr__


# ---------------------------------------------------------- module state

_LOCK = threading.RLock()
_STATE: RuntimeState | None = None
_ENV_BEFORE: tuple[MutableMapping[str, str], dict] | None = None
_REVOKE_HOOKS: list[Callable[[], None]] = []
_RESET_HOOKS: list[Callable[[], None]] = []


def register_hooks(*, on_revoke: Callable[[], None], on_reset: Callable[[], None]) -> None:
    """Used by ``app.runtime_db`` to dispose engines on revocation and test reset."""
    with _LOCK:
        _REVOKE_HOOKS.append(on_revoke)
        _RESET_HOOKS.append(on_reset)


def current_state() -> RuntimeState | None:
    return _STATE


class _CapturingFs:
    """Wraps the resolver provider and keeps the bytes it read, for content digests."""

    def __init__(self, inner):
        self._inner = inner
        self.read: dict[str, bytes] = {}

    def lstat(self, path):
        return self._inner.lstat(path)

    def access_writable(self, path):
        return self._inner.access_writable(path)

    def realpath(self, path):
        return self._inner.realpath(path)

    def read_nofollow(self, path, max_bytes):
        data, info = self._inner.read_nofollow(path, max_bytes)
        self.read[os.fspath(path)] = data
        return data, info

    def read_in_root(self, root, name, max_bytes):
        return self._inner.read_in_root(root, name, max_bytes)


def development_exports(resolution: rt.RuntimeResolution, env: Mapping[str, str]) -> dict[str, str]:
    """What a committed development bootstrap writes into the environment.

    The canonical ``DATABASE_URL`` and the profile's DB keys (children accept them
    because they are equal), plus allowlisted non-DB keys only where unset.
    """
    dev = resolution.development
    if dev is None:
        return {}
    exports = {rt.DATABASE_URL_KEY: dev.database_url}
    for key in rt.REQUIRED_DB_KEYS + tuple(k for k in rt.OPTIONAL_DB_KEYS if k in dev.target.explicit_options):
        exports[key] = rt._effective_option_text(dev.target, key)
    for key, value in dev.nondb.items():
        if key not in env:
            exports[key] = value
    return exports


@dataclass(frozen=True)
class _Candidate:
    resolution: rt.RuntimeResolution
    fingerprint: Fingerprint
    exports: dict


def _evaluate(purpose: str, cli, inputs: RuntimeInputs) -> _Candidate:
    """Phase 1: pure validation. Reads files; never mutates the environment."""
    env_view = dict(inputs.env)
    before = file_metadata(inputs)
    capture = _CapturingFs(inputs.provider())
    resolution = rt.resolve_runtime(
        env_view, purpose=purpose, cli=cli, profile_path=inputs.profile_path,
        policy_file=inputs.policy_path(), build_root_dir=inputs.build_root_dir, fs=capture,
        platform=inputs.platform,
    )
    after = file_metadata(inputs)
    if before != after:
        raise rt.RuntimeConfigError("configuration_changed_during_bootstrap")
    exports = development_exports(resolution, env_view)
    development = resolution.mode == "development"
    digests = ()
    if development:
        digests = tuple(sorted((path, _digest(data)) for path, data in capture.read.items()))
    fingerprint = Fingerprint(
        mode=resolution.mode, purpose=purpose, target=_target_key(resolution),
        env=env_snapshot({**env_view, **exports}), files=after if development else (), digests=digests,
    )
    return _Candidate(resolution=resolution, fingerprint=fingerprint, exports=exports)


def bootstrap_runtime(purpose: str, *, cli=None, inputs: RuntimeInputs | None = None) -> RuntimeState:
    """Resolve and commit the runtime state (design §8.1, §8.4).

    - First call: validate, then commit. A failure commits nothing and leaves the
      environment byte-identical.
    - Later call with fingerprint-identical inputs: no-op, returns the same state.
    - Later call with different or invalid inputs: revokes, then raises.
    - After revocation: always raises ``RuntimeRevokedError``.
    """
    global _STATE, _ENV_BEFORE
    inputs = default_inputs() if inputs is None else inputs
    with _LOCK:
        current = _STATE
        if current is not None and current.status == REVOKED:
            raise RuntimeRevokedError(current.trigger or "revoked")
        failure = None
        try:
            candidate = _evaluate(purpose, cli, inputs)
        except rt.RuntimeConfigError as exc:
            failure = exc
        if failure is not None:
            if current is not None:
                _revoke_locked("rebootstrap_invalid")
            raise failure
        if current is not None:
            if candidate.fingerprint == current.fingerprint and inputs.env is current.inputs.env:
                return current
            _revoke_locked("rebootstrap_conflict")
            raise RuntimeRevokedError("rebootstrap_conflict")

        # Phase 2: commit.
        env = inputs.env
        saved = dict(env)
        committed = False
        try:
            env.update(candidate.exports)
            _STATE = RuntimeState(mode=candidate.resolution.mode, status=ACTIVE,
                                  resolution=candidate.resolution, fingerprint=candidate.fingerprint,
                                  inputs=inputs)
            _ENV_BEFORE = (env, saved)
            committed = True
        finally:
            if not committed:
                env.clear()
                env.update(saved)
                _STATE = None
        return _STATE


def bootstrap_entry_point(purpose: str, *, cli=None) -> RuntimeState:
    """``bootstrap_runtime`` for a process entry point: a refusal prints its code and exits 2.

    The message carries only the sanitized code (and key or line); the process exits
    before any connection is attempted.
    """
    failure = None
    try:
        return bootstrap_runtime(purpose, cli=cli)
    except rt.RuntimeConfigError as exc:
        failure = str(exc)
    print(f"BIZQLAB RUNTIME REFUSED ({purpose}): {failure}", file=sys.stderr, flush=True)
    raise SystemExit(2)


def assert_usable() -> RuntimeState:
    """Check the committed state at a boundary (design §8.2). Revokes on any failure."""
    state = _STATE
    if state is None:
        raise RuntimeNotBootstrappedError()
    if state.status != ACTIVE:
        raise RuntimeRevokedError(state.trigger or "revoked")
    if state.mode == "production":
        return state
    current_env = env_snapshot(state.inputs.env)
    if current_env != state.fingerprint.env:
        key = _first_difference(current_env, state.fingerprint.env)
        revoke("env_drift", key=key)
    files = None
    try:
        files = file_metadata(state.inputs)
    except OSError:
        files = None
    if files != state.fingerprint.files:
        revoke("metadata_changed")
    return state


def _first_difference(a: tuple, b: tuple) -> str | None:
    da, db = dict(a), dict(b)
    for key in sorted(set(da) | set(db)):
        if da.get(key) != db.get(key):
            return key
    return None


def revoke(trigger: str, *, key: str | None = None):
    """Revoke the active state (terminal) and raise ``RuntimeRevokedError``."""
    with _LOCK:
        _revoke_locked(trigger)
    raise RuntimeRevokedError(trigger, key=key)


def _revoke_locked(trigger: str) -> None:
    global _STATE
    state = _STATE
    if state is None or state.status == REVOKED:
        return
    _STATE = replace(state, status=REVOKED, trigger=trigger)
    for hook in list(_REVOKE_HOOKS):
        try:
            hook()
        except Exception:  # noqa: BLE001 - revocation must never be blocked by cleanup
            pass


def _reset_for_tests() -> None:
    """Dispose engines, clear state and caches, and restore the pre-commit environment."""
    global _STATE, _ENV_BEFORE
    with _LOCK:
        for hook in list(_RESET_HOOKS):
            try:
                hook()
            except Exception:  # noqa: BLE001
                pass
        if _ENV_BEFORE is not None:
            env, saved = _ENV_BEFORE
            env.clear()
            env.update(saved)
        _STATE = None
        _ENV_BEFORE = None
