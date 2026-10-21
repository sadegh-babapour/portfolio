"""Guarded development connections and engines (M1 design §5, §6, §8.3).

Batch 2. Every development connection is created by ``connect_verified()``:
psycopg2 keyword arguments from the resolved target, a guarded
``connection_factory``, and the identity query as the first statement. Guards
call ``runtime_state.assert_usable()`` before every statement and commit, on raw
psycopg2 handles and on SQLAlchemy engines (checkout, statement, commit), so a
revoked state stops retained, pooled and long-lived handles. Rollback and close
are always allowed.

Same-process code that deliberately constructs an unguarded cursor (for example
``psycopg2.extensions.cursor(conn)``) is outside the accidental-mistargeting
threat model.
"""
from __future__ import annotations

import re
import weakref

from sqlalchemy import create_engine, event

from app import runtime_env as rt
from app import runtime_state

IDENTITY_SQL = "SELECT current_database(), current_user, host(inet_server_addr()), inet_server_port()"
_SQLSTATE_RE = re.compile(r"[0-9A-Z]{5}")
_FORBIDDEN_ENGINE_KWARGS = ("creator", "module", "connect_args", "url")


class RuntimeConnectError(rt.RuntimeConfigError):
    """A sanitized connect or identity failure: code and SQLSTATE only.

    ``redacted_target`` names user, host, port and database (no password) for
    diagnostics; it is not part of the message.
    """

    def __init__(self, code: str, *, sqlstate: str | None = None, redacted_target: str | None = None):
        super().__init__(code)
        self.sqlstate = sqlstate
        self.redacted_target = redacted_target
        if sqlstate is not None:
            self.args = (f"{code} [sqlstate={sqlstate}]",)


def _dbapi():
    """The DB-API module. Tests replace this function with a fake driver."""
    import psycopg2

    return psycopg2


def _sqlstate(exc: BaseException) -> str | None:
    code = getattr(exc, "pgcode", None)
    return code if isinstance(code, str) and _SQLSTATE_RE.fullmatch(code) else None


def _redacted(target: rt.DevelopmentTarget) -> str:
    return f"{target.user}@{target.host}:{target.port}/{target.database}"


def _require_development(state: runtime_state.RuntimeState) -> rt.DevelopmentResolution:
    if state.mode != "development" or state.development is None:
        raise rt.RuntimeConfigError("development_only")
    return state.development


# ------------------------------------------------------- guarded psycopg2


class _CursorGuard:
    """Checks the runtime state before every statement-issuing cursor call."""

    def execute(self, *args, **kwargs):
        runtime_state.assert_usable()
        return super().execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        runtime_state.assert_usable()
        return super().executemany(*args, **kwargs)

    def callproc(self, *args, **kwargs):
        runtime_state.assert_usable()
        return super().callproc(*args, **kwargs)

    def copy_expert(self, *args, **kwargs):
        runtime_state.assert_usable()
        return super().copy_expert(*args, **kwargs)

    def copy_from(self, *args, **kwargs):
        runtime_state.assert_usable()
        return super().copy_from(*args, **kwargs)

    def copy_to(self, *args, **kwargs):
        runtime_state.assert_usable()
        return super().copy_to(*args, **kwargs)


class _ConnectionGuard:
    """Guarded cursors only; commit and other server-side calls check the state first."""

    _bizqlab_cursor_class: type
    _bizqlab_base_cursor: type

    def cursor(self, name=None, cursor_factory=None, withhold=False, scrollable=None):
        if name is not None:
            raise rt.RuntimeConfigError("named_cursor_unsupported")
        factory = cursor_factory if cursor_factory is not None else getattr(self, "cursor_factory", None)
        # The driver's exact base cursor (which psycopg2.extras helpers such as
        # HstoreAdapter.get_oids request explicitly, called by SQLAlchemy's dialect on
        # connect) becomes the guarded cursor. Its unguarded subclasses stay refused.
        if factory is None or factory is self._bizqlab_base_cursor:
            factory = self._bizqlab_cursor_class
        elif not (isinstance(factory, type) and issubclass(factory, _CursorGuard)):
            raise rt.RuntimeConfigError("unguarded_cursor_factory")
        return super().cursor(cursor_factory=factory, withhold=withhold, scrollable=scrollable)

    def commit(self):
        runtime_state.assert_usable()
        return super().commit()

    def __exit__(self, exc_type, exc_value, traceback):
        # psycopg2's own __exit__ commits in C without calling commit() above, so check
        # first; a refused exit rolls back instead and re-raises.
        if exc_type is None:
            try:
                runtime_state.assert_usable()
            except rt.RuntimeConfigError:
                self.rollback()
                raise
        return super().__exit__(exc_type, exc_value, traceback)

    def set_client_encoding(self, *args, **kwargs):
        runtime_state.assert_usable()
        return super().set_client_encoding(*args, **kwargs)

    def tpc_begin(self, *args, **kwargs):
        runtime_state.assert_usable()
        return super().tpc_begin(*args, **kwargs)

    def tpc_prepare(self, *args, **kwargs):
        runtime_state.assert_usable()
        return super().tpc_prepare(*args, **kwargs)

    def tpc_commit(self, *args, **kwargs):
        runtime_state.assert_usable()
        return super().tpc_commit(*args, **kwargs)

    def lobject(self, *args, **kwargs):
        raise rt.RuntimeConfigError("large_objects_unsupported")


_GUARDED_CLASSES: dict[int, tuple[type, type]] = {}


def guarded_classes(driver=None) -> tuple[type, type]:
    """``(GuardedConnection, GuardedCursor)`` built on the driver's own connection and cursor types."""
    driver = _dbapi() if driver is None else driver
    key = id(driver)
    if key not in _GUARDED_CLASSES:
        cursor_class = type("GuardedCursor", (_CursorGuard, driver.extensions.cursor), {})
        connection_class = type("GuardedConnection", (_ConnectionGuard, driver.extensions.connection),
                                {"_bizqlab_cursor_class": cursor_class,
                                 "_bizqlab_base_cursor": driver.extensions.cursor})
        _GUARDED_CLASSES[key] = (connection_class, cursor_class)
    return _GUARDED_CLASSES[key]


def guarded_cursor_factory(base: type) -> type:
    """A guarded variant of a cursor factory (for example a dict cursor), accepted by guarded connections."""
    return type(f"Guarded{base.__name__}", (_CursorGuard, base), {})


# ------------------------------------------------------------ identity


def normalize_address(text) -> str | None:
    if not isinstance(text, str):
        return None
    if ":" in text:
        hextets = rt.parse_ipv6(text.lower())
        return None if hextets is None else rt.format_ipv6(hextets)
    octets = rt.parse_ipv4(text)
    return None if octets is None else ".".join(str(o) for o in octets)


def identity_matches(row, policy: rt.PolicyTarget) -> bool:
    if not isinstance(row, (tuple, list)) or len(row) != 4:
        return False
    database, role, address, port = row
    return (
        database == policy.database
        and role == policy.role
        and normalize_address(address) in policy.server_addresses
        and type(port) is int and port == policy.server_port
    )


def _close_quietly(conn) -> None:
    try:
        conn.close()
    except Exception:  # noqa: BLE001 - closing is best effort; the error is already decided
        pass


def verify_identity(conn, dev: rt.DevelopmentResolution) -> None:
    """Run the identity query as the first statement; leave no open transaction (design §6).

    On any failure the connection is closed, the state is revoked and a
    sanitized error is raised outside the handler.
    """
    code = sqlstate = None
    refusal = None
    row = None
    try:
        cur = conn.cursor()
        try:
            cur.execute(IDENTITY_SQL)
            row = cur.fetchone()
        finally:
            cur.close()
        conn.rollback()
    except rt.RuntimeConfigError as exc:
        refusal = exc
    except Exception as exc:  # noqa: BLE001 - driver messages may contain connection details
        code, sqlstate = "identity_query_failed", _sqlstate(exc)
    if refusal is None and code is None and not identity_matches(row, dev.policy):
        code = "identity_mismatch"
    if refusal is None and code is None:
        return
    _close_quietly(conn)
    if refusal is not None:
        raise refusal
    try:
        runtime_state.revoke(code)
    except runtime_state.RuntimeRevokedError:
        pass
    raise RuntimeConnectError(code, sqlstate=sqlstate, redacted_target=_redacted(dev.target))


def connect_verified():
    """Open a development psycopg2 connection and verify its identity before returning it.

    Takes no arguments, so it can be used directly as a SQLAlchemy ``creator``.
    """
    state = runtime_state.assert_usable()
    dev = _require_development(state)
    driver = _dbapi()
    connection_class, _cursor_class = guarded_classes(driver)
    code = sqlstate = None
    conn = None
    try:
        conn = driver.connect(connection_factory=connection_class, **dev.target.psycopg2_kwargs())
    except Exception as exc:  # noqa: BLE001 - driver messages may contain connection details
        code, sqlstate = "connect_failed", _sqlstate(exc)
    if code is not None:
        raise RuntimeConnectError(code, sqlstate=sqlstate, redacted_target=_redacted(dev.target))
    verify_identity(conn, dev)
    return conn


# ------------------------------------------------------------- SQLAlchemy

_ENGINES: "weakref.WeakSet" = weakref.WeakSet()
_ENGINE_CACHE: dict = {}


def _on_checkout(dbapi_connection, connection_record, connection_proxy):
    runtime_state.assert_usable()


def _on_checkin(dbapi_connection, connection_record):
    state = runtime_state.current_state()
    if dbapi_connection is not None and (state is None or state.status != runtime_state.ACTIVE):
        connection_record.invalidate()


def _on_before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    runtime_state.assert_usable()


def _on_commit(conn):
    runtime_state.assert_usable()


def install_guards(engine) -> None:
    event.listen(engine, "checkout", _on_checkout)
    event.listen(engine, "checkin", _on_checkin)
    event.listen(engine, "before_cursor_execute", _on_before_cursor_execute)
    event.listen(engine, "commit", _on_commit)


def create_development_engine(**kwargs):
    """A SQLAlchemy engine whose every physical connection comes from ``connect_verified``.

    Identity verification therefore precedes the dialect's own first-connect SQL
    and runs again on recycle and pre-ping reconnects (design L1).
    """
    for key in _FORBIDDEN_ENGINE_KWARGS:
        if key in kwargs:
            raise rt.RuntimeConfigError("engine_option_refused", key=key)
    state = runtime_state.assert_usable()
    dev = _require_development(state)
    options = {"pool_pre_ping": True, "pool_recycle": 300, **kwargs}
    engine = create_engine(dev.target.sqlalchemy_url(), creator=connect_verified, module=_dbapi(), **options)
    install_guards(engine)
    _ENGINES.add(engine)
    return engine


def get_development_engine():
    """The cached engine for the current state. The state is checked on every call, outside the cache."""
    state = runtime_state.assert_usable()
    engine = _ENGINE_CACHE.get(id(state))
    if engine is None:
        _ENGINE_CACHE.clear()
        engine = create_development_engine()
        _ENGINE_CACHE[id(state)] = engine
    return engine


def _dispose_all() -> None:
    for engine in list(_ENGINES):
        try:
            engine.dispose()
        except Exception:  # noqa: BLE001
            pass


def _reset() -> None:
    _dispose_all()
    _ENGINES.clear()
    _ENGINE_CACHE.clear()
    _GUARDED_CLASSES.clear()


runtime_state.register_hooks(on_revoke=_dispose_all, on_reset=_reset)
