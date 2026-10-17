#!/usr/bin/env python3
"""Create the transit schema and optionally load current static GTFS data."""

from __future__ import annotations

import argparse
import io
import os
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZipFile

import psycopg2
import requests


DEFAULT_GTFS_URL = (
    "https://data.calgary.ca/download/npk7-z3bj/application%2Fzip"
)
MIGRATIONS = (
    "001_create_transit_schema.sql",
    "002_create_transit_tables.sql",
    "003_create_transit_views.sql",
    "004_indexes.sql",
    "005_static_gtfs_import_state.sql",
)
REQUIRED_GTFS_FILES = (
    "routes.txt",
    "trips.txt",
    "calendar.txt",
    "calendar_dates.txt",
    "stops.txt",
    "shapes.txt",
    "stop_times.txt",
)


def connect():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
    )


def apply_migrations(conn) -> None:
    migration_dir = Path(__file__).resolve().parent / "db"
    with conn.cursor() as cur:
        for name in MIGRATIONS:
            path = migration_dir / name
            cur.execute(path.read_text(encoding="utf-8"))
            print(f"applied {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}")
    conn.commit()


def read_source(source: str) -> bytes:
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        response = requests.get(source, timeout=90)
        response.raise_for_status()
        return response.content
    return Path(source).read_bytes()


@contextmanager
def zip_text(zf: ZipFile, member: str):
    with zf.open(member) as raw:
        with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
            yield text


def copy_member(cur, zf: ZipFile, member: str, table: str, columns: str) -> None:
    with zip_text(zf, member) as source:
        cur.copy_expert(
            f"COPY {table} ({columns}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)",
            source,
        )
    print(f"loaded {member} -> {table}")


def load_gtfs_archive(conn, archive: bytes, route_catalog: Path | None) -> None:
    with ZipFile(io.BytesIO(archive)) as zf:
        missing = sorted(set(REQUIRED_GTFS_FILES) - set(zf.namelist()))
        if missing:
            raise RuntimeError(f"GTFS archive is missing: {', '.join(missing)}")

        with conn.cursor() as cur:
            cur.execute(
                """
                TRUNCATE TABLE
                    transit.calendar_dates,
                    transit.calendar,
                    transit.stop_times,
                    transit.shapes,
                    transit.stops,
                    transit.trips,
                    transit.routes,
                    transit.route_catalog_raw
                """
            )

            copy_member(
                cur,
                zf,
                "routes.txt",
                "transit.routes",
                "route_id, route_short_name, route_long_name, route_desc, "
                "route_type, route_url, route_color, route_text_color",
            )
            copy_member(
                cur,
                zf,
                "trips.txt",
                "transit.trips",
                "route_id, service_id, trip_id, trip_headsign, direction_id, "
                "block_id, shape_id",
            )
            copy_member(
                cur,
                zf,
                "stops.txt",
                "transit.stops",
                "stop_id, stop_code, stop_name, stop_desc, stop_lat, stop_lon, "
                "zone_id, stop_url, location_type",
            )
            copy_member(
                cur,
                zf,
                "shapes.txt",
                "transit.shapes",
                "shape_id, shape_pt_lat, shape_pt_lon, shape_pt_sequence, "
                "shape_dist_traveled",
            )
            copy_member(
                cur,
                zf,
                "stop_times.txt",
                "transit.stop_times",
                "trip_id, arrival_time, departure_time, stop_id, stop_sequence, "
                "pickup_type, drop_off_type, shape_dist_traveled, timepoint",
            )

            cur.execute(
                """
                CREATE TEMP TABLE calendar_stage (
                    service_id text,
                    monday integer,
                    tuesday integer,
                    wednesday integer,
                    thursday integer,
                    friday integer,
                    saturday integer,
                    sunday integer,
                    start_date text,
                    end_date text
                ) ON COMMIT DROP
                """
            )
            copy_member(
                cur,
                zf,
                "calendar.txt",
                "calendar_stage",
                "service_id, monday, tuesday, wednesday, thursday, friday, "
                "saturday, sunday, start_date, end_date",
            )
            cur.execute(
                """
                INSERT INTO transit.calendar
                SELECT service_id, monday, tuesday, wednesday, thursday, friday,
                       saturday, sunday, to_date(start_date, 'YYYYMMDD'),
                       to_date(end_date, 'YYYYMMDD')
                FROM calendar_stage
                """
            )

            cur.execute(
                """
                CREATE TEMP TABLE calendar_dates_stage (
                    service_id text,
                    date text,
                    exception_type integer
                ) ON COMMIT DROP
                """
            )
            copy_member(
                cur,
                zf,
                "calendar_dates.txt",
                "calendar_dates_stage",
                "service_id, date, exception_type",
            )
            cur.execute(
                """
                INSERT INTO transit.calendar_dates
                SELECT service_id, to_date(date, 'YYYYMMDD'), exception_type
                FROM calendar_dates_stage
                """
            )

            if route_catalog:
                with route_catalog.open(encoding="utf-8-sig", newline="") as catalog:
                    cur.copy_expert(
                        """
                        COPY transit.route_catalog_raw (
                            route_category, route_short_name, route_long_name,
                            create_dt_utc, mod_dt_utc, globalid, multilinestring
                        ) FROM STDIN WITH (FORMAT CSV, HEADER TRUE)
                        """,
                        catalog,
                    )
                print(f"loaded {route_catalog} -> transit.route_catalog_raw")

        # The caller owns the transaction so an automated refresh can record
        # its import state atomically with the static table replacement.


def load_gtfs(conn, source: str, route_catalog: Path | None) -> None:
    load_gtfs_archive(conn, read_source(source), route_catalog)
    conn.commit()


def print_counts(conn) -> None:
    tables = (
        "routes",
        "trips",
        "calendar",
        "calendar_dates",
        "stops",
        "shapes",
        "stop_times",
        "route_catalog_raw",
    )
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(f"SELECT count(*) FROM transit.{table}")
            print(f"transit.{table}: {cur.fetchone()[0]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--load-static",
        action="store_true",
        help="replace static GTFS tables after applying migrations",
    )
    parser.add_argument("--gtfs-source", default=DEFAULT_GTFS_URL)
    parser.add_argument("--route-catalog", type=Path)
    args = parser.parse_args()

    with connect() as conn:
        apply_migrations(conn)
        if args.load_static:
            load_gtfs(conn, args.gtfs_source, args.route_catalog)
        print_counts(conn)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
