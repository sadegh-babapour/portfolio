from __future__ import annotations

import logging
import time
from functools import lru_cache

from sqlalchemy import text

from app.contact.database import session_scope
from financial_research.public_views import (
    load_public_filing_directory,
    load_public_filing_profile,
    load_public_payments_comparison,
    load_public_sector_screen,
)


log = logging.getLogger(__name__)


def _set_public_read_timeout(database) -> None:
    bind = database.get_bind()
    if bind.dialect.name == "postgresql":
        database.execute(text("SET LOCAL statement_timeout = '5000ms'"))


@lru_cache(maxsize=4)
def _load_filing_directory_cached(_time_bucket: int) -> dict:
    try:
        with session_scope() as database:
            _set_public_read_timeout(database)
            return load_public_filing_directory(database)
    except Exception as exc:
        log.warning("Unable to load public SEC filing directory: %s", exc)
        return {
            "available": False,
            "version": None,
            "company_count": 0,
            "industries": [],
        }


def load_filing_directory() -> dict:
    return _load_filing_directory_cached(int(time.time() // 300))


@lru_cache(maxsize=96)
def _load_filing_profile_cached(ticker: str, _time_bucket: int) -> dict | None:
    try:
        with session_scope() as database:
            _set_public_read_timeout(database)
            return load_public_filing_profile(database, ticker)
    except Exception as exc:
        log.warning("Unable to load public SEC filing profile for %s: %s", ticker, exc)
        return None


def load_filing_profile(ticker: str) -> dict | None:
    return _load_filing_profile_cached(ticker.lower(), int(time.time() // 300))


@lru_cache(maxsize=4)
def _load_payments_comparison_cached(_time_bucket: int) -> dict:
    try:
        with session_scope() as database:
            _set_public_read_timeout(database)
            return load_public_payments_comparison(database)
    except Exception as exc:
        log.warning("Unable to load public payment comparison: %s", exc)
        return {
            "available": False,
            "version": None,
            "model_version": None,
            "period_end": None,
            "ranking_performed": False,
            "companies": [],
            "comparison_notes": [],
        }


def load_payments_comparison() -> dict:
    return _load_payments_comparison_cached(int(time.time() // 300))


@lru_cache(maxsize=24)
def _load_sector_screen_cached(industry_key: str, _time_bucket: int) -> dict | None:
    try:
        with session_scope() as database:
            _set_public_read_timeout(database)
            return load_public_sector_screen(database, industry_key)
    except Exception as exc:
        log.warning("Unable to load public sector screen for %s: %s", industry_key, exc)
        return None


def load_sector_screen(industry_key: str) -> dict | None:
    return _load_sector_screen_cached(industry_key, int(time.time() // 300))
