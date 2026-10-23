"""Canada rates page data: reads the Bank of Canada dbt mart, never writes.

The mart (warehouse/models/marts/mart_canada_rates_daily.sql) exists only where the
pipeline has run. Production has no reporting database until stage 2, so there the
page gets `available: False` and says so.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date
from typing import Any

from sqlalchemy import text

from app.contact.database import session_scope


log = logging.getLogger(__name__)
CACHE_SECONDS = 600
MEASURES = ("policy_rate", "corra", "gov_2y", "gov_5y", "gov_10y", "usd_cad", "spread_10y_2y_bps")
# Overnight is the policy rate; the rest are Government of Canada benchmark yields.
TENORS = (("Overnight", "policy_rate", 0), ("2-year", "gov_2y", 2), ("5-year", "gov_5y", 5),
          ("10-year", "gov_10y", 10))

MART_SQL = text(
    """
    select obs_date, policy_rate, corra, gov_2y, gov_5y, gov_10y, usd_cad, spread_10y_2y_bps
    from marts.mart_canada_rates_daily
    order by obs_date
    """
)
LAST_LOAD_SQL = text(
    """
    select finished_at, status, rows_inserted, rows_updated
    from raw.load_runs
    where source = 'bank_of_canada'
    order by run_id desc
    limit 1
    """
)

_LOCK = threading.Lock()
_CACHE: dict[str, Any] | None = None
_EXPIRES_AT = 0.0


def load_rates() -> dict[str, Any]:
    """The page's data, cached for ten minutes: the mart changes once a day at most."""
    global _CACHE, _EXPIRES_AT

    now = time.monotonic()
    with _LOCK:
        if _CACHE is not None and now < _EXPIRES_AT:
            return _CACHE
        _CACHE = _query()
        _EXPIRES_AT = now + (CACHE_SECONDS if _CACHE["available"] else 60)
        return _CACHE


def _query() -> dict[str, Any]:
    try:
        with session_scope() as database:
            database.execute(text("set transaction read only"))
            database.execute(text("set local statement_timeout = '3000ms'"))
            rows = [dict(row) for row in database.execute(MART_SQL).mappings()]
            last_load = database.execute(LAST_LOAD_SQL).mappings().first()
            database.rollback()
    except Exception as exc:  # noqa: BLE001 - the page shows "not available" for any failure
        log.warning("Canada rates mart unavailable: %s", type(exc).__name__)
        return {"available": False}
    return summarize(rows, dict(last_load) if last_load else None)


def _num(value) -> float | None:
    return None if value is None else float(value)


def _year_before(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # 29 February
        return day.replace(year=day.year - 1, day=28)


def _change(measure: str, latest: float, prior: float) -> float:
    """Change in the unit people quote: bps for rates, percent for the exchange rate."""
    if measure == "usd_cad":
        return round((latest / prior - 1) * 100, 1)
    if measure == "spread_10y_2y_bps":
        return round(latest - prior)
    return round((latest - prior) * 100)


def summarize(rows: list[dict], last_load: dict | None = None) -> dict[str, Any]:
    """Shape mart rows for the page. Pure: no database, so it is tested directly."""
    series = [
        {"date": row["obs_date"], **{m: _num(row.get(m)) for m in MEASURES}}
        for row in rows
    ]
    if not series:
        return {"available": False}

    latest = {}
    for measure in MEASURES:
        points = [(r["date"], r[measure]) for r in series if r[measure] is not None]
        if not points:
            continue
        day, value = points[-1]
        cut = _year_before(day)
        prior = next((v for d, v in reversed(points) if d <= cut), None)
        latest[measure] = {
            "date": day,
            "value": value,
            "change_1y": None if prior is None else _change(measure, value, prior),
            "spark": [[d.isoformat(), v] for d, v in points if d > cut],
        }

    # Policy decisions: every day the policy rate differs from the day before.
    decisions = []
    previous = None
    for row in series:
        rate = row["policy_rate"]
        if rate is None:
            continue
        if previous is not None and rate != previous:
            decisions.append({"date": row["date"], "rate": rate, "change_bps": round((rate - previous) * 100)})
        previous = rate

    full = [r for r in series if all(r[key] is not None for _, key, _ in TENORS)]
    curve = []
    if full:
        now_row = full[-1]
        cut = _year_before(now_row["date"])
        then_row = next((r for r in reversed(full) if r["date"] <= cut), full[0])
        curve = [
            {"tenor": tenor, "years": years, "now": now_row[key], "year_ago": then_row[key]}
            for tenor, key, years in TENORS
        ]
        curve_dates = {"now": now_row["date"], "year_ago": then_row["date"]}
    else:
        curve_dates = {}

    spread = latest.get("spread_10y_2y_bps", {}).get("value")
    return {
        "available": True,
        "rows": series,
        "first_date": series[0]["date"],
        "last_date": series[-1]["date"],
        "latest": latest,
        "decisions": decisions,
        "curve": curve,
        "curve_dates": curve_dates,
        "curve_shape": None if spread is None else "upward" if spread > 0 else "inverted" if spread < 0 else "flat",
        "last_load": last_load,
    }
