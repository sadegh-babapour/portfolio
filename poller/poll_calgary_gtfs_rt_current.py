"""The transit-poller service: Calgary's realtime feeds → Postgres, every 30 seconds.

One loop (main), forever:
  fetch each feed (GTFS-Realtime, a protobuf binary) → parse → write → commit.
- "current" tables hold one row per vehicle, trip or alert: an upsert replaces the old row.
- vehicle_positions_raw keeps the last few minutes of points so the map can replay them
  (docs/lessons/09); older rows are deleted on every pass (RAW_RETENTION_MINUTES).
- Each feed is its own transaction: a broken alerts feed doesn't lose the bus positions.
- Polling runs only during service hours, and POLL_ENABLED / ADMIN_KILL_SWITCH stop it
  without a deploy. The static schedule (routes, stops, shapes) re-syncs every 6 hours.
- Rows go to Postgres in batches (execute_values), not one statement per row: trip updates
  carry ~40k stop times, and one-by-one writes stretched each pass from 30 s to ~100 s.
- Each pass records per-feed counts and timings in transit.poller_feed_status, which the
  health checks read to tell "Calgary's data" apart from "our pipeline".
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import psycopg2
import requests
from google.transit import gtfs_realtime_pb2
from psycopg2.extras import execute_values

from app import runtime_db, runtime_state
from app.runtime_env import CLI_DB_FLAGS
from poller.static_gtfs_sync import sync_static_gtfs
from scripts.bootstrap_transit_db import apply_migrations

VEHICLE_POSITIONS_URL = "https://data.calgary.ca/download/am7c-qe3u/application%2Foctet-stream"
TRIP_UPDATES_URL = "https://data.calgary.ca/download/gs4m-mdc2/application%2Foctet-stream"
ALERTS_URL = "https://data.calgary.ca/download/jhgn-ynqj/application%2Foctet-stream"

# Rows per INSERT statement in a batch.
BATCH_PAGE_SIZE = 1000
# Calgary sends most buses (about 265 of 360 in November 2026) with an impossible vehicle
# timestamp: one shared value per feed, months or decades old (1988 on Nov 9, 2020 on
# Nov 13), changing every feed. Those buses are live and moving, so their report time
# falls back to the feed's own timestamp. Real reports trail the header by seconds to
# about 10 minutes and are kept as they are (an old one is genuinely stale); only times a
# day behind the feed, or more than 10 minutes ahead of it, are treated as missing.
MAX_REPORT_BEHIND_FEED_SECONDS = 24 * 60 * 60
MAX_REPORT_AHEAD_OF_FEED_SECONDS = 600


def ts_to_dt(ts: int | None):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def report_time(vehicle_ts: datetime | None, header_ts: datetime | None) -> tuple[datetime | None, bool]:
    """The time a vehicle report describes, and whether it came from the feed header."""
    if header_ts is None:
        return vehicle_ts, False
    if vehicle_ts is None:
        return header_ts, True
    ahead_seconds = (vehicle_ts - header_ts).total_seconds()
    if ahead_seconds > MAX_REPORT_AHEAD_OF_FEED_SECONDS or -ahead_seconds > MAX_REPORT_BEHIND_FEED_SECONDS:
        return header_ts, True
    return vehicle_ts, False


def record_feed_status(
    cur,
    feed_name: str,
    started: float,
    header_ts: datetime | None,
    entities: int,
    written: int,
    timestamps_from_header: int = 0,
) -> float:
    """Store this pass's counts and timing for the health checks; returns the duration."""
    duration = time.monotonic() - started
    cur.execute(
        """
        insert into transit.poller_feed_status (
            feed_name, finished_at, seconds_since_previous, duration_seconds,
            feed_header_timestamp, entities_in_feed, rows_written, timestamps_from_header
        )
        values (%s, now(), null, %s, %s, %s, %s, %s)
        on conflict (feed_name) do update
        set seconds_since_previous =
                extract(epoch from (now() - transit.poller_feed_status.finished_at)),
            finished_at = now(),
            duration_seconds = excluded.duration_seconds,
            feed_header_timestamp = excluded.feed_header_timestamp,
            entities_in_feed = excluded.entities_in_feed,
            rows_written = excluded.rows_written,
            timestamps_from_header = excluded.timestamps_from_header
        """,
        (feed_name, duration, header_ts, entities, written, timestamps_from_header),
    )
    return duration


def fetch_feed(url: str) -> tuple[bytes, gtfs_realtime_pb2.FeedMessage]:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    raw = resp.content
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(raw)
    return raw, feed


def first_translation_text(translated_string):
    if not translated_string or not hasattr(translated_string, "translation"):
        return None
    for t in translated_string.translation:
        if getattr(t, "text", None):
            return t.text
    return None


def within_hours(start_hour: int, end_hour: int, tz_name: str) -> bool:
    now_local = datetime.now(ZoneInfo(tz_name))
    return start_hour <= now_local.hour < end_hour

def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

def upsert_vehicle_positions(conn) -> None:
    started = time.monotonic()
    raw, feed = fetch_feed(VEHICLE_POSITIONS_URL)
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    header_ts = ts_to_dt(getattr(feed.header, "timestamp", None))

    current_sql = """
        insert into transit.vehicle_positions_current (
            vehicle_id,
            trip_id,
            feed_entity_id,
            vehicle_timestamp,
            feed_header_timestamp,
            lat,
            lon,
            raw_sha256,
            updated_at
        )
        values %s
        -- One row per bus: a newer report overwrites the last one.
        on conflict (vehicle_id) do update
        set trip_id = excluded.trip_id,
            feed_entity_id = excluded.feed_entity_id,
            vehicle_timestamp = excluded.vehicle_timestamp,
            feed_header_timestamp = excluded.feed_header_timestamp,
            lat = excluded.lat,
            lon = excluded.lon,
            raw_sha256 = excluded.raw_sha256,
            updated_at = now()
    """

    raw_sql = """
        insert into transit.vehicle_positions_raw (
            downloaded_at,
            feed_header_timestamp,
            feed_entity_id,
            trip_id,
            vehicle_id,
            vehicle_timestamp,
            lat,
            lon,
            raw_sha256
        )
        values %s
        -- The feed repeats a bus's last report until it sends a new one; keep each report once.
        on conflict (trip_id, vehicle_id, vehicle_timestamp) do nothing
    """

    # Keyed by vehicle: one statement cannot upsert the same row twice.
    current_rows: dict[str, tuple] = {}
    raw_rows: list[tuple] = []
    entities = 0
    from_header = 0
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        entities += 1

        vp = entity.vehicle
        trip_id = vp.trip.trip_id if vp.HasField("trip") and vp.trip.trip_id else None
        vehicle_id = vp.vehicle.id if vp.HasField("vehicle") and vp.vehicle.id else None
        lat = vp.position.latitude if vp.HasField("position") else None
        lon = vp.position.longitude if vp.HasField("position") else None
        vehicle_ts, substituted = report_time(ts_to_dt(getattr(vp, "timestamp", None)), header_ts)

        if not trip_id or not vehicle_id or lat is None or lon is None or vehicle_ts is None:
            continue

        from_header += substituted
        current_rows[vehicle_id] = (
            vehicle_id, trip_id, entity.id, vehicle_ts, header_ts, lat, lon, raw_sha256,
        )
        raw_rows.append((header_ts, entity.id, trip_id, vehicle_id, vehicle_ts, lat, lon, raw_sha256))

    with conn.cursor() as cur:
        if current_rows:
            execute_values(
                cur,
                current_sql,
                list(current_rows.values()),
                template="(%s, %s, %s, %s, %s, %s, %s, %s, now())",
                page_size=BATCH_PAGE_SIZE,
            )
            execute_values(
                cur,
                raw_sql,
                raw_rows,
                template="(now(), %s, %s, %s, %s, %s, %s, %s, %s)",
                page_size=BATCH_PAGE_SIZE,
            )

        # Retention: the map needs minutes of history, not days, so the table stays small.
        retention_minutes = int(os.getenv("RAW_RETENTION_MINUTES", "15"))
        cur.execute(
            """
            delete from transit.vehicle_positions_raw
            where vehicle_timestamp < now() - make_interval(mins => %s)
            """,
            (retention_minutes,),
        )
        duration = record_feed_status(
            cur, "vehicle_positions", started, header_ts, entities, len(current_rows), from_header,
        )

    print(
        f"vehicle_positions_current upserted: {len(current_rows)} of {entities} in feed "
        f"({from_header} timed by the feed header) in {duration:.1f}s"
    )


def upsert_trip_updates(conn) -> None:
    started = time.monotonic()
    raw, feed = fetch_feed(TRIP_UPDATES_URL)
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    header_ts = ts_to_dt(getattr(feed.header, "timestamp", None))

    parent_sql = """
        insert into transit.trip_updates_current (
            trip_id,
            feed_entity_id,
            route_id,
            trip_schedule_relationship,
            feed_header_timestamp,
            raw_sha256,
            updated_at
        )
        values %s
        on conflict (trip_id) do update
        set feed_entity_id = excluded.feed_entity_id,
            route_id = excluded.route_id,
            trip_schedule_relationship = excluded.trip_schedule_relationship,
            feed_header_timestamp = excluded.feed_header_timestamp,
            raw_sha256 = excluded.raw_sha256,
            updated_at = now()
    """

    # A trip's stop list is replaced whole: stops it no longer lists are removed.
    delete_children_sql = """
        delete from transit.trip_update_stop_times_current
        where trip_id = any(%s)
    """

    child_sql = """
        insert into transit.trip_update_stop_times_current (
            trip_id,
            stop_sequence,
            stop_id,
            arrival_time,
            departure_time,
            schedule_relationship,
            updated_at
        )
        values %s
        on conflict (trip_id, stop_sequence) do update
        set stop_id = excluded.stop_id,
            arrival_time = excluded.arrival_time,
            departure_time = excluded.departure_time,
            schedule_relationship = excluded.schedule_relationship,
            updated_at = now()
    """

    # Keyed like the primary keys: one statement cannot upsert the same row twice.
    parents: dict[str, tuple] = {}
    children: dict[tuple[str, int], tuple] = {}
    entities = 0

    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        entities += 1

        tu = entity.trip_update
        trip_id = tu.trip.trip_id if tu.HasField("trip") and tu.trip.trip_id else None
        route_id = tu.trip.route_id if tu.HasField("trip") and tu.trip.route_id else None
        trip_sched_rel = tu.trip.schedule_relationship if tu.HasField("trip") else None

        if not trip_id:
            continue

        parents[trip_id] = (trip_id, entity.id, route_id, trip_sched_rel, header_ts, raw_sha256)

        for stu in tu.stop_time_update:
            arrival_time = ts_to_dt(stu.arrival.time) if stu.HasField("arrival") and getattr(stu.arrival, "time", None) else None
            departure_time = ts_to_dt(stu.departure.time) if stu.HasField("departure") and getattr(stu.departure, "time", None) else None
            stop_sequence = stu.stop_sequence if getattr(stu, "stop_sequence", None) else None
            stop_id = stu.stop_id if getattr(stu, "stop_id", None) else None
            schedule_relationship = stu.schedule_relationship if getattr(stu, "schedule_relationship", None) is not None else None

            if stop_sequence is None:
                continue

            children[(trip_id, stop_sequence)] = (
                trip_id, stop_sequence, stop_id, arrival_time, departure_time, schedule_relationship,
            )

    with conn.cursor() as cur:
        if parents:
            execute_values(
                cur,
                parent_sql,
                list(parents.values()),
                template="(%s, %s, %s, %s, %s, %s, now())",
                page_size=BATCH_PAGE_SIZE,
            )
            cur.execute(delete_children_sql, (list(parents),))
        if children:
            execute_values(
                cur,
                child_sql,
                list(children.values()),
                template="(%s, %s, %s, %s, %s, %s, now())",
                page_size=BATCH_PAGE_SIZE,
            )

        if parents:
            cur.execute(
                """
                delete from transit.trip_updates_current
                where updated_at < now() - interval '10 minutes'
                """
            )
            cur.execute(
                """
                delete from transit.trip_update_stop_times_current
                where updated_at < now() - interval '10 minutes'
                """
            )
        duration = record_feed_status(cur, "trip_updates", started, header_ts, entities, len(parents))

    print(
        f"trip_updates_current upserted: {len(parents)}, "
        f"stop_times_current upserted: {len(children)} in {duration:.1f}s"
    )


def upsert_alerts(conn) -> None:
    started = time.monotonic()
    raw, feed = fetch_feed(ALERTS_URL)
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    header_ts = ts_to_dt(getattr(feed.header, "timestamp", None))

    parent_sql = """
        insert into transit.alerts_current (
            feed_entity_id,
            active_start,
            active_end,
            header_text,
            description_html,
            feed_header_timestamp,
            raw_sha256,
            updated_at
        )
        values (%s, %s, %s, %s, %s, %s, %s, now())
        on conflict (feed_entity_id) do update
        set active_start = excluded.active_start,
            active_end = excluded.active_end,
            header_text = excluded.header_text,
            description_html = excluded.description_html,
            feed_header_timestamp = excluded.feed_header_timestamp,
            raw_sha256 = excluded.raw_sha256,
            updated_at = now()
    """

    delete_child_sql = """
        delete from transit.alert_informed_entities_current
        where feed_entity_id = %s
    """

    child_sql = """
        insert into transit.alert_informed_entities_current (
            feed_entity_id,
            agency_id,
            route_id,
            stop_id
        )
        values (%s, %s, %s, %s)
        on conflict do nothing
    """

    parent_count = 0
    child_count = 0
    seen_alert_ids: set[str] = set()

    with conn.cursor() as cur:
        for entity in feed.entity:
            if not entity.HasField("alert"):
                continue

            alert = entity.alert
            alert_id = entity.id
            seen_alert_ids.add(alert_id)

            active_start = None
            active_end = None
            if len(alert.active_period) > 0:
                ap = alert.active_period[0]
                active_start = ts_to_dt(getattr(ap, "start", None))
                active_end = ts_to_dt(getattr(ap, "end", None))

            header_text = first_translation_text(alert.header_text)
            description_html = first_translation_text(alert.description_text)

            cur.execute(
                parent_sql,
                (
                    alert_id,
                    active_start,
                    active_end,
                    header_text,
                    description_html,
                    header_ts,
                    raw_sha256,
                ),
            )
            parent_count += 1

            cur.execute(delete_child_sql, (alert_id,))

            for ie in alert.informed_entity:
                agency_id = ie.agency_id if getattr(ie, "agency_id", None) else None
                route_id = ie.route_id if getattr(ie, "route_id", None) else None
                stop_id = ie.stop_id if getattr(ie, "stop_id", None) else None

                cur.execute(
                    child_sql,
                    (
                        alert_id,
                        agency_id,
                        route_id,
                        stop_id,
                    ),
                )
                child_count += 1

        cur.execute(
            """
            delete from transit.alert_informed_entities_current
            where feed_entity_id not in (
                select feed_entity_id from transit.alerts_current
                where updated_at >= now() - interval '10 minutes'
            )
            """
        )
        cur.execute(
            """
            delete from transit.alerts_current
            where updated_at < now() - interval '10 minutes'
            """
        )
        duration = record_feed_status(cur, "alerts", started, header_ts, len(seen_alert_ids), parent_count)

    print(
        f"alerts_current upserted: {parent_count}, "
        f"informed_entities_current inserted: {child_count} in {duration:.1f}s"
    )


def run_once(conn) -> None:
    failures: list[tuple[str, Exception]] = []
    feed_updates = (
        ("vehicle_positions", upsert_vehicle_positions),
        ("trip_updates", upsert_trip_updates),
        ("alerts", upsert_alerts),
    )

    # Commit per feed: one failing feed rolls back only its own writes.
    for feed_name, update_feed in feed_updates:
        try:
            update_feed(conn)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            failures.append((feed_name, exc))
            print(f"{feed_name} poll error: {exc}", file=sys.stderr)

    if len(failures) == len(feed_updates):
        raise RuntimeError("all Calgary realtime feeds failed")


def next_pass_delay(interval_seconds: float, elapsed_seconds: float) -> float:
    """Seconds to wait before the next pass; at least 1 s so a slow pass never spins."""
    return max(1.0, interval_seconds - elapsed_seconds)


def cli_db_flags(argv: list[str]) -> dict[str, str | None]:
    """The database flags given explicitly on the command line, for the runtime conflict check."""
    pre = argparse.ArgumentParser(add_help=False)
    for flag in CLI_DB_FLAGS:
        pre.add_argument(flag)
    known, _rest = pre.parse_known_args(argv)
    return {flag: getattr(known, flag[2:].replace("-", "_")) for flag in CLI_DB_FLAGS}


def main() -> int:
    # The runtime gate runs before the parser reads defaults from the environment. In
    # development, any database flag on the command line must equal the approved target.
    state = runtime_state.bootstrap_entry_point("poller", cli=cli_db_flags(sys.argv[1:]))
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--host", default=os.getenv("PGHOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PGPORT", "5432")))
    parser.add_argument("--dbname", default=os.getenv("PGDATABASE"))
    parser.add_argument("--user", default=os.getenv("PGUSER"))
    parser.add_argument("--password", default=os.getenv("PGPASSWORD"))
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=int(os.getenv("POLL_INTERVAL_SECONDS", "30")),
    )
    parser.add_argument(
        "--start-hour",
        type=int,
        default=int(os.getenv("POLL_START_HOUR", "8")),
    )
    parser.add_argument(
        "--end-hour",
        type=int,
        default=int(os.getenv("POLL_END_HOUR", "21")),
    )
    parser.add_argument(
        "--timezone",
        default=os.getenv("POLL_TIMEZONE", "America/Edmonton"),
    )
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    if state.mode == "development":
        conn = runtime_db.connect_verified()
    elif args.database_url:
        conn = psycopg2.connect(args.database_url)
    else:
        missing = [
            name
            for name, value in (
                ("PGDATABASE/--dbname", args.dbname),
                ("PGUSER/--user", args.user),
                ("PGPASSWORD/--password", args.password),
            )
            if not value
        ]
        if missing:
            parser.error("missing database configuration: " + ", ".join(missing))
        conn = psycopg2.connect(
            host=args.host,
            port=args.port,
            dbname=args.dbname,
            user=args.user,
            password=args.password,
        )

    try:
        conn.autocommit = False

        if env_bool("TRANSIT_APPLY_MIGRATIONS", True):
            apply_migrations(conn)

        if args.once:
            run_once(conn)
            return 0

        last_static_sync_attempt = 0.0
        static_sync_interval = max(
            300,
            int(os.getenv("GTFS_SYNC_INTERVAL_SECONDS", "21600")),
        )

        while True:
            pass_started = time.monotonic()
            # A revoked development state ends the process instead of looping on errors.
            runtime_state.assert_usable()
            polling_enabled = env_bool("POLL_ENABLED", True)
            kill_switch = env_bool("ADMIN_KILL_SWITCH", False)

            if kill_switch:
                print("polling disabled by ADMIN_KILL_SWITCH")
            elif not polling_enabled:
                print("polling disabled by POLL_ENABLED=false")
            else:
                monotonic_now = time.monotonic()
                if (
                    env_bool("GTFS_AUTO_SYNC_ENABLED", True)
                    and monotonic_now - last_static_sync_attempt >= static_sync_interval
                ):
                    last_static_sync_attempt = monotonic_now
                    try:
                        result = sync_static_gtfs(conn)
                        print(f"static GTFS sync: {result}")
                    except Exception as exc:
                        conn.rollback()
                        print(f"static GTFS sync error: {exc}", file=sys.stderr)

                if within_hours(args.start_hour, args.end_hour, args.timezone):
                    try:
                        run_once(conn)
                    except Exception as e:
                        conn.rollback()
                        print(f"poll error: {e}", file=sys.stderr)
                else:
                    print("outside polling hours, sleeping")

            # Sleep only what is left of the interval, so a pass starts every 30 s rather
            # than every 30 s plus however long the writes took.
            time.sleep(next_pass_delay(args.interval_seconds, time.monotonic() - pass_started))

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
