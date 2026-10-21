from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import runtime_db, runtime_state
from app.contact.config import ContactSettings


def get_engine() -> Engine:
    """The shared engine. The runtime gate is checked on every call, outside any cache.

    Development uses the verified engine (identity before any SQL, revocation guards).
    Attested production keeps today's parameters. Without a bootstrapped entry point
    this raises ``runtime_not_bootstrapped`` before any connection exists.
    """
    state = runtime_state.assert_usable()
    if state.mode == "development":
        return runtime_db.get_development_engine()
    return _production_engine()


@lru_cache(maxsize=1)
def _production_engine() -> Engine:
    settings = ContactSettings.from_env()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for the contact workflow")
    return create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=300)


def session_scope() -> Session:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)()


def _dispose_production_engine() -> None:
    if _production_engine.cache_info().currsize:
        _production_engine().dispose()


def _reset_production_engine() -> None:
    _dispose_production_engine()
    _production_engine.cache_clear()


runtime_state.register_hooks(on_revoke=_dispose_production_engine, on_reset=_reset_production_engine)
