"""Conditional, transaction-safe synchronization of Calgary static GTFS."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

from scripts.bootstrap_transit_db import DEFAULT_GTFS_URL, load_gtfs_archive


DEFAULT_ROUTE_CATALOG = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "Calgary_Transit_Routes_20260417.csv"
)

STATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS transit.static_gtfs_import_state (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    source_url text NOT NULL,
    source_etag text,
    archive_sha256 text NOT NULL,
    checked_at timestamptz NOT NULL,
    loaded_at timestamptz NOT NULL,
    max_service_date date
)
"""


def sync_static_gtfs(
    conn,
    *,
    source_url: str | None = None,
    route_catalog: Path | None = None,
    now: datetime | None = None,
) -> str:
    """Check Calgary's archive and atomically reload it only when changed."""

    source_url = source_url or os.getenv("GTFS_STATIC_URL", DEFAULT_GTFS_URL)
    if route_catalog is None:
        configured_catalog = os.getenv("GTFS_ROUTE_CATALOG")
        route_catalog = Path(configured_catalog) if configured_catalog else DEFAULT_ROUTE_CATALOG
    checked_at = now or datetime.now(timezone.utc)

    with conn.cursor() as cur:
        cur.execute(STATE_TABLE_SQL)
        cur.execute(
            """
            SELECT source_url, source_etag, archive_sha256
            FROM transit.static_gtfs_import_state
            WHERE singleton = true
            """
        )
        row = cur.fetchone()

    previous_source_url = row[0] if row else None
    previous_etag = row[1] if row and previous_source_url == source_url else None
    previous_sha256 = row[2] if row and previous_source_url == source_url else None
    headers = {"If-None-Match": previous_etag} if previous_etag else {}
    response = requests.get(source_url, headers=headers, timeout=90)

    if response.status_code == 304 and previous_etag:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE transit.static_gtfs_import_state
                SET checked_at = %s
                WHERE singleton = true
                """,
                (checked_at,),
            )
        conn.commit()
        return "unchanged"

    response.raise_for_status()
    archive = response.content
    archive_sha256 = hashlib.sha256(archive).hexdigest()
    source_etag = response.headers.get("ETag")

    if row and archive_sha256 == previous_sha256:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE transit.static_gtfs_import_state
                SET source_url = %s, source_etag = %s, checked_at = %s
                WHERE singleton = true
                """,
                (source_url, source_etag, checked_at),
            )
        conn.commit()
        return "unchanged"

    load_gtfs_archive(conn, archive, route_catalog if route_catalog.exists() else None)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO transit.static_gtfs_import_state (
                singleton, source_url, source_etag, archive_sha256,
                checked_at, loaded_at, max_service_date
            )
            VALUES (
                true, %s, %s, %s, %s, %s,
                (SELECT max(end_date) FROM transit.calendar)
            )
            ON CONFLICT (singleton) DO UPDATE
            SET source_url = excluded.source_url,
                source_etag = excluded.source_etag,
                archive_sha256 = excluded.archive_sha256,
                checked_at = excluded.checked_at,
                loaded_at = excluded.loaded_at,
                max_service_date = excluded.max_service_date
            """,
            (source_url, source_etag, archive_sha256, checked_at, checked_at),
        )
    conn.commit()
    return "loaded"
