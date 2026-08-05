from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.contact.config import ContactSettings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = ContactSettings.from_env()
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required for the contact workflow")
    return create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=300)


def session_scope() -> Session:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)()
