"""Load Bank of Canada rates and USD/CAD into the reporting `raw` schema.

Source: the Bank of Canada Valet API (free, no key; reuse allowed with attribution,
https://www.bankofcanada.ca/terms/). One request fetches every configured series.

The load is idempotent: one row per (series, date), upserted, so a re-run changes
nothing. Each run re-reads the last LOOKBACK_DAYS so values the Bank revises are
picked up; `--since` backfills further. Every run leaves one row in raw.load_runs,
and a failed run commits none of its observations.

Usage (development, through the approved database only):
  .venv/bin/python -m pipelines.bank_of_canada [--since 2015-01-01]
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests

SOURCE = "bank_of_canada"
VALET_URL = "https://www.bankofcanada.ca/valet/observations/{series}/json"
DEFAULT_START = date(2015, 1, 1)
LOOKBACK_DAYS = 30
SCHEMA_SQL = Path(__file__).with_name("sql") / "raw_bank_of_canada.sql"

# Series IDs as the Valet API names them (checked against the API on 2026-10-21).
SERIES = (
    "V39079",              # target for the overnight rate (policy rate)
    "AVG.INTWO",           # CORRA, the overnight repo rate average
    "BD.CDN.2YR.DQ.YLD",   # 2-year Government of Canada benchmark bond yield
    "BD.CDN.5YR.DQ.YLD",   # 5-year
    "BD.CDN.10YR.DQ.YLD",  # 10-year
    "FXUSDCAD",            # USD/CAD daily average exchange rate
)


class SourceError(Exception):
    """The API could not be read, or its answer is not what this loader expects."""


@dataclass(frozen=True)
class Series:
    series_id: str
    label: str
    description: str
    unit: str | None
    frequency: str | None


@dataclass(frozen=True)
class Observation:
    series_id: str
    obs_date: date
    value: Decimal


def fetch(series: tuple[str, ...], start: date, session=requests) -> dict:
    """The Valet JSON for `series` from `start` onwards."""
    url = VALET_URL.format(series=",".join(series))
    try:
        response = session.get(url, params={"start_date": start.isoformat()}, timeout=30)
    except requests.RequestException as exc:
        raise SourceError(f"request failed: {type(exc).__name__}") from exc
    if response.status_code != 200:
        # Valet explains errors in JSON, e.g. {"message": "Series NOPE not found."}.
        try:
            message = response.json().get("message")
        except ValueError:
            message = None
        raise SourceError(f"HTTP {response.status_code}: {message or 'no message'}")
    try:
        return response.json()
    except ValueError as exc:
        raise SourceError("response is not JSON") from exc


def parse(payload: dict, series: tuple[str, ...]) -> tuple[list[Series], list[Observation]]:
    """Series metadata and observations. Days with no value for a series are skipped."""
    details = payload.get("seriesDetail")
    rows = payload.get("observations")
    if not isinstance(details, dict) or not isinstance(rows, list):
        raise SourceError("response has no seriesDetail/observations")
    missing = [s for s in series if s not in details]
    if missing:
        raise SourceError(f"series missing from response: {', '.join(missing)}")

    metadata = [
        Series(s, details[s].get("label") or s, details[s].get("description") or "",
               (details[s].get("metadata") or {}).get("unit"),
               (details[s].get("metadata") or {}).get("frequency"))
        for s in series
    ]
    observations = []
    for row in rows:
        try:
            obs_date = date.fromisoformat(row["d"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SourceError(f"observation without a valid date: {row!r:.80}") from exc
        for s in series:
            # Holidays: a series is absent from the row, or present with an empty value.
            text = (row.get(s) or {}).get("v")
            if text in (None, ""):
                continue
            try:
                value = Decimal(text)
            except InvalidOperation:
                value = None
            if value is None or not value.is_finite():  # Postgres numeric would accept 'NaN'
                raise SourceError(f"{s} on {obs_date}: value {text!r} is not a number")
            observations.append(Observation(s, obs_date, value))
    return metadata, observations


def ensure_schema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
    conn.commit()


def start_date(conn, series: tuple[str, ...], since: date | None) -> date:
    """`since` if given; otherwise LOOKBACK_DAYS before the oldest 'latest date' among the series."""
    if since is not None:
        return since
    with conn.cursor() as cur:
        cur.execute(
            """
            select count(distinct series_id), min(latest)
            from (select series_id, max(obs_date) as latest
                  from raw.boc_observations where series_id = any(%s) group by series_id) per_series
            """,
            (list(series),),
        )
        loaded, oldest_latest = cur.fetchone()
    if loaded < len(series):
        return DEFAULT_START  # a series has never been loaded: full history
    return oldest_latest - timedelta(days=LOOKBACK_DAYS)


def upsert(conn, metadata: list[Series], observations: list[Observation]) -> tuple[int, int]:
    """Write series and observations in the caller's transaction. Returns (inserted, updated)."""
    with conn.cursor() as cur:
        for s in metadata:
            cur.execute(
                """
                insert into raw.boc_series (series_id, label, description, unit, frequency)
                values (%s, %s, %s, %s, %s)
                on conflict (series_id) do update
                set label = excluded.label, description = excluded.description,
                    unit = excluded.unit, frequency = excluded.frequency, last_seen_at = now()
                """,
                (s.series_id, s.label, s.description, s.unit, s.frequency),
            )
        inserted = updated = 0
        for o in observations:
            # An unchanged value matches the WHERE clause on neither branch, so nothing is
            # written and nothing is returned. xmax = 0 marks a freshly inserted row.
            cur.execute(
                """
                insert into raw.boc_observations (series_id, obs_date, value)
                values (%s, %s, %s)
                on conflict (series_id, obs_date) do update
                set value = excluded.value, last_changed_at = now()
                where raw.boc_observations.value is distinct from excluded.value
                returning (xmax = 0)
                """,
                (o.series_id, o.obs_date, o.value),
            )
            row = cur.fetchone()
            if row is not None:
                if row[0]:
                    inserted += 1
                else:
                    updated += 1
    return inserted, updated


def run(conn, *, series: tuple[str, ...] = SERIES, since: date | None = None, session=requests) -> dict:
    """One load. The run row is committed on its own so a failure is still recorded."""
    ensure_schema(conn)
    with conn.cursor() as cur:
        cur.execute("insert into raw.load_runs (source) values (%s) returning run_id", (SOURCE,))
        run_id = cur.fetchone()[0]
    conn.commit()

    try:
        start = start_date(conn, series, since)
        metadata, observations = parse(fetch(series, start, session), series)
        inserted, updated = upsert(conn, metadata, observations)
        with conn.cursor() as cur:
            cur.execute(
                """
                update raw.load_runs
                set finished_at = now(), status = 'succeeded', start_date = %s,
                    rows_read = %s, rows_inserted = %s, rows_updated = %s
                where run_id = %s
                """,
                (start, len(observations), inserted, updated, run_id),
            )
        conn.commit()  # the observations and the run's success, together
    except Exception as exc:
        conn.rollback()  # none of this run's observations
        with conn.cursor() as cur:
            cur.execute(
                "update raw.load_runs set finished_at = now(), status = 'failed', error = %s where run_id = %s",
                (f"{type(exc).__name__}: {exc}"[:500], run_id),
            )
        conn.commit()
        raise
    return {"run_id": run_id, "start_date": start, "rows_read": len(observations),
            "inserted": inserted, "updated": updated}


def main(argv: list[str] | None = None) -> int:
    from app import runtime_db, runtime_state

    # The gate runs before anything else. Stage 1 loads the approved development
    # database only; the production reporting database arrives with stage 2.
    state = runtime_state.bootstrap_entry_point("bank-of-canada")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", type=date.fromisoformat, help="backfill from this date (YYYY-MM-DD)")
    args = parser.parse_args(argv)
    if state.mode != "development":
        print("bank_of_canada: production has no reporting database yet (stage 2); refusing", file=sys.stderr)
        return 2

    conn = runtime_db.connect_verified()
    try:
        result = run(conn, since=args.since)
    except Exception as exc:  # noqa: BLE001 - recorded in raw.load_runs; the exit code reports it
        print(f"bank_of_canada: load failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    print(f"bank_of_canada: run {result['run_id']} from {result['start_date']}: "
          f"{result['rows_read']} read, {result['inserted']} inserted, {result['updated']} updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
