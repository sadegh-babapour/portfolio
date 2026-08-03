from __future__ import annotations

import argparse
import hashlib
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import psycopg2
import requests
from google.transit import gtfs_realtime_pb2

import os
from zoneinfo import ZoneInfo


VEHICLE_POSITIONS_URL = "https://data.calgary.ca/download/am7c-qe3u/application%2Foctet-stream"
TRIP_UPDATES_URL = "https://data.calgary.ca/download/gs4m-mdc2/application%2Foctet-stream"
ALERTS_URL = "https://data.calgary.ca/download/jhgn-ynqj/application%2Foctet-stream"

LOCAL_TZ = ZoneInfo("America/Edmonton")


@dataclass
class DbConfig:
    host: str
    port: int
    dbname: str
    user: str
    password: str


def ts_to_dt(ts: int | None):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


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


# def within_hours(start_hour: int, end_hour: int) -> bool:
#     now_local = datetime.now(LOCAL_TZ)
#     return start_hour <= now_local.hour < end_hour

def within_hours(start_hour: int, end_hour: int, tz_name: str) -> bool:
    now_local = datetime.now(ZoneInfo(tz_name))
    return start_hour <= now_local.hour < end_hour

def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

def upsert_vehicle_positions(conn) -> None:
    raw, feed = fetch_feed(VEHICLE_POSITIONS_URL)
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    header_ts = ts_to_dt(getattr(feed.header, "timestamp", None))

    sql = """
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
        values (%s, %s, %s, %s, %s, %s, %s, %s, now())
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
    values (now(), %s, %s, %s, %s, %s, %s, %s, %s)
    on conflict (trip_id, vehicle_id, vehicle_timestamp) do nothing
"""


    count = 0
    with conn.cursor() as cur:
        for entity in feed.entity:
            if not entity.HasField("vehicle"):
                continue

            vp = entity.vehicle
            trip_id = vp.trip.trip_id if vp.HasField("trip") and vp.trip.trip_id else None
            vehicle_id = vp.vehicle.id if vp.HasField("vehicle") and vp.vehicle.id else None
            lat = vp.position.latitude if vp.HasField("position") else None
            lon = vp.position.longitude if vp.HasField("position") else None
            vehicle_ts = ts_to_dt(getattr(vp, "timestamp", None))

            if not trip_id or not vehicle_id or lat is None or lon is None or vehicle_ts is None:
                continue

            cur.execute(
                sql,
                (
                    vehicle_id,
                    trip_id,
                    entity.id,
                    vehicle_ts,
                    header_ts,
                    lat,
                    lon,
                    raw_sha256,
                ),
            )
            cur.execute(
                raw_sql,
                (
                    header_ts,
                    entity.id,
                    trip_id,
                    vehicle_id,
                    vehicle_ts,
                    lat,
                    lon,
                    raw_sha256,
                ),
            )
            count += 1

        retention_minutes = int(os.getenv("RAW_RETENTION_MINUTES", "15"))
        cur.execute(
            f"""
            delete from transit.vehicle_positions_raw
            where vehicle_timestamp < now() - interval '{retention_minutes} minutes'
            """
        )


    print(f"vehicle_positions_current upserted: {count}")


def upsert_trip_updates(conn) -> None:
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
        values (%s, %s, %s, %s, %s, %s, now())
        on conflict (trip_id) do update
        set feed_entity_id = excluded.feed_entity_id,
            route_id = excluded.route_id,
            trip_schedule_relationship = excluded.trip_schedule_relationship,
            feed_header_timestamp = excluded.feed_header_timestamp,
            raw_sha256 = excluded.raw_sha256,
            updated_at = now()
    """

    delete_child_sql = """
        delete from transit.trip_update_stop_times_current
        where trip_id = %s
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
        values (%s, %s, %s, %s, %s, %s, now())
        on conflict (trip_id, stop_sequence) do update
        set stop_id = excluded.stop_id,
            arrival_time = excluded.arrival_time,
            departure_time = excluded.departure_time,
            schedule_relationship = excluded.schedule_relationship,
            updated_at = now()
    """

    parent_count = 0
    child_count = 0

    with conn.cursor() as cur:
        seen_trip_ids: set[str] = set()

        for entity in feed.entity:
            if not entity.HasField("trip_update"):
                continue

            tu = entity.trip_update
            trip_id = tu.trip.trip_id if tu.HasField("trip") and tu.trip.trip_id else None
            route_id = tu.trip.route_id if tu.HasField("trip") and tu.trip.route_id else None
            trip_sched_rel = tu.trip.schedule_relationship if tu.HasField("trip") else None

            if not trip_id:
                continue

            cur.execute(
                parent_sql,
                (
                    trip_id,
                    entity.id,
                    route_id,
                    trip_sched_rel,
                    header_ts,
                    raw_sha256,
                ),
            )
            parent_count += 1

            cur.execute(delete_child_sql, (trip_id,))
            seen_trip_ids.add(trip_id)

            for stu in tu.stop_time_update:
                arrival_time = ts_to_dt(stu.arrival.time) if stu.HasField("arrival") and getattr(stu.arrival, "time", None) else None
                departure_time = ts_to_dt(stu.departure.time) if stu.HasField("departure") and getattr(stu.departure, "time", None) else None
                stop_sequence = stu.stop_sequence if getattr(stu, "stop_sequence", None) else None
                stop_id = stu.stop_id if getattr(stu, "stop_id", None) else None
                schedule_relationship = stu.schedule_relationship if getattr(stu, "schedule_relationship", None) is not None else None

                if stop_sequence is None:
                    continue

                cur.execute(
                    child_sql,
                    (
                        trip_id,
                        stop_sequence,
                        stop_id,
                        arrival_time,
                        departure_time,
                        schedule_relationship,
                    ),
                )
                child_count += 1

        if seen_trip_ids:
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

    print(f"trip_updates_current upserted: {parent_count}, stop_times_current upserted: {child_count}")


def upsert_alerts(conn) -> None:
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

    print(f"alerts_current upserted: {parent_count}, informed_entities_current inserted: {child_count}")


def run_once(conn) -> None:
    upsert_vehicle_positions(conn)
    upsert_trip_updates(conn)
    upsert_alerts(conn)
    conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--dbname", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    # parser.add_argument("--interval-seconds", type=int, default=30)
    # parser.add_argument("--start-hour", type=int, default=9)
    # parser.add_argument("--end-hour", type=int, default=19)

    parser.add_argument(
    "--interval-seconds",
    type=int,
    default=int(os.getenv("POLL_INTERVAL_SECONDS", "30")),)
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

    conn = psycopg2.connect(
        host=args.host,
        port=args.port,
        dbname=args.dbname,
        user=args.user,
        password=args.password,
    )

    try:
        conn.autocommit = False

        if args.once:
            run_once(conn)
            return 0

        while True:
            polling_enabled = env_bool("POLL_ENABLED", True)
            kill_switch = env_bool("ADMIN_KILL_SWITCH", False)

            if kill_switch:
                print("polling disabled by ADMIN_KILL_SWITCH")
            elif not polling_enabled:
                print("polling disabled by POLL_ENABLED=false")
            elif within_hours(args.start_hour, args.end_hour, args.timezone):
                try:
                    run_once(conn)
                except Exception as e:
                    conn.rollback()
                    print(f"poll error: {e}", file=sys.stderr)
            else:
                print("outside polling hours, sleeping")

            time.sleep(args.interval_seconds)

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())