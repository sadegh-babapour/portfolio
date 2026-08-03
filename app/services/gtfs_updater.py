# import asyncio
# import csv
# import io
# import logging
# import os
# import zipfile

# import httpx
# from dotenv import load_dotenv

# load_dotenv()
# log = logging.getLogger(__name__)

# GTFS_ZIP_URL = "https://data.calgary.ca/download/npk7-z3bj/application%2Fzip"


# # ── SQL ────────────────────────────────────────────────────────────

# CREATE_TABLES_SQL = """
# CREATE TABLE IF NOT EXISTS gtfs_meta (
#     key   TEXT PRIMARY KEY,
#     value TEXT
# );
# CREATE TABLE IF NOT EXISTS gtfs_trips (
#     trip_id          TEXT PRIMARY KEY,
#     route_id         TEXT,
#     route_short_name TEXT,
#     headsign         TEXT,
#     direction_id     SMALLINT,
#     shape_id         TEXT,
#     service_id       TEXT
# );
# CREATE INDEX IF NOT EXISTS idx_gtfs_trips_route ON gtfs_trips (route_short_name);
# CREATE INDEX IF NOT EXISTS idx_gtfs_trips_shape ON gtfs_trips (shape_id);

# CREATE TABLE IF NOT EXISTS gtfs_stops (
#     stop_id    TEXT PRIMARY KEY,
#     stop_code  TEXT,
#     stop_name  TEXT,
#     stop_lat   DOUBLE PRECISION,
#     stop_lon   DOUBLE PRECISION
# );

# CREATE TABLE IF NOT EXISTS gtfs_stop_times (
#     trip_id          TEXT NOT NULL,
#     stop_sequence    INTEGER NOT NULL,
#     stop_id          TEXT NOT NULL,
#     arrival_time     TEXT,
#     departure_time   TEXT,
#     shape_dist       REAL,
#     timepoint        SMALLINT,
#     PRIMARY KEY (trip_id, stop_sequence)
# );
# CREATE INDEX IF NOT EXISTS idx_gst_stop ON gtfs_stop_times (stop_id);
# CREATE INDEX IF NOT EXISTS idx_gst_trip ON gtfs_stop_times (trip_id);
# """


# # ── ETag stored in DB not filesystem ──────────────────────────────

# def _load_etag(pool) -> str | None:
#     try:
#         with pool.connection() as conn:
#             with conn.cursor() as cur:
#                 cur.execute("SELECT value FROM gtfs_meta WHERE key = 'etag'")
#                 row = cur.fetchone()
#                 return row["value"] if row else None
#     except Exception:
#         return None


# def _save_etag(pool, etag: str) -> None:
#     try:
#         with pool.connection() as conn:
#             with conn.cursor() as cur:
#                 cur.execute("""
#                     INSERT INTO gtfs_meta (key, value) VALUES ('etag', %s)
#                     ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
#                 """, (etag,))
#     except Exception as e:
#         log.warning("Failed to save ETag: %s", e)


# def _tables_populated(pool) -> bool:
#     """Returns True if gtfs_stops has 1000+ rows — meaning data is loaded."""
#     try:
#         with pool.connection() as conn:
#             with conn.cursor() as cur:
#                 cur.execute("SELECT count(*) as n FROM gtfs_stops")
#                 return cur.fetchone()["n"] >= 1000
#     except Exception:
#         return False


# # ── loaders ────────────────────────────────────────────────────────

# def _load_routes_lookup(zf: zipfile.ZipFile) -> dict[str, str]:
#     lookup = {}
#     with zf.open("routes.txt") as f:
#         reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
#         for row in reader:
#             lookup[row["route_id"]] = row["route_short_name"]
#     return lookup


# def _load_trips(zf: zipfile.ZipFile, routes: dict[str, str], cur) -> int:
#     cur.execute("TRUNCATE gtfs_trips")
#     count = 0
#     with zf.open("trips.txt") as f:
#         reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
#         batch = []
#         for row in reader:
#             short = routes.get(row["route_id"], row.get("route_short_name", ""))
#             batch.append((
#                 row["trip_id"], row["route_id"], short,
#                 row.get("trip_headsign", ""),
#                 int(row.get("direction_id", 0) or 0),
#                 row.get("shape_id", ""), row.get("service_id", ""),
#             ))
#             if len(batch) >= 5000:
#                 cur.executemany("""
#                     INSERT INTO gtfs_trips
#                         (trip_id, route_id, route_short_name, headsign,
#                          direction_id, shape_id, service_id)
#                     VALUES (%s,%s,%s,%s,%s,%s,%s)
#                     ON CONFLICT (trip_id) DO UPDATE SET
#                         route_short_name = EXCLUDED.route_short_name,
#                         headsign         = EXCLUDED.headsign,
#                         direction_id     = EXCLUDED.direction_id,
#                         shape_id         = EXCLUDED.shape_id
#                 """, batch)
#                 count += len(batch)
#                 batch = []
#         if batch:
#             cur.executemany("""
#                 INSERT INTO gtfs_trips
#                     (trip_id, route_id, route_short_name, headsign,
#                      direction_id, shape_id, service_id)
#                 VALUES (%s,%s,%s,%s,%s,%s,%s)
#                 ON CONFLICT (trip_id) DO UPDATE SET
#                     route_short_name = EXCLUDED.route_short_name,
#                     headsign         = EXCLUDED.headsign,
#                     direction_id     = EXCLUDED.direction_id,
#                     shape_id         = EXCLUDED.shape_id
#             """, batch)
#             count += len(batch)
#     return count


# def _load_stops(zf: zipfile.ZipFile, cur) -> int:
#     cur.execute("TRUNCATE gtfs_stops")
#     count = 0
#     with zf.open("stops.txt") as f:
#         reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
#         batch = []
#         for row in reader:
#             try:
#                 batch.append((
#                     row["stop_id"], row.get("stop_code", ""),
#                     row.get("stop_name", ""),
#                     float(row["stop_lat"]), float(row["stop_lon"]),
#                 ))
#             except (ValueError, KeyError):
#                 continue
#             if len(batch) >= 2000:
#                 cur.executemany("""
#                     INSERT INTO gtfs_stops
#                         (stop_id, stop_code, stop_name, stop_lat, stop_lon)
#                     VALUES (%s,%s,%s,%s,%s)
#                     ON CONFLICT (stop_id) DO UPDATE SET
#                         stop_name = EXCLUDED.stop_name,
#                         stop_lat  = EXCLUDED.stop_lat,
#                         stop_lon  = EXCLUDED.stop_lon
#                 """, batch)
#                 count += len(batch)
#                 batch = []
#         if batch:
#             cur.executemany("""
#                 INSERT INTO gtfs_stops
#                     (stop_id, stop_code, stop_name, stop_lat, stop_lon)
#                 VALUES (%s,%s,%s,%s,%s)
#                 ON CONFLICT (stop_id) DO UPDATE SET
#                     stop_name = EXCLUDED.stop_name,
#                     stop_lat  = EXCLUDED.stop_lat,
#                     stop_lon  = EXCLUDED.stop_lon
#             """, batch)
#             count += len(batch)
#     return count


# def _load_stop_times(zf: zipfile.ZipFile, cur) -> int:
#     cur.execute("TRUNCATE gtfs_stop_times")
#     count = 0
#     with zf.open("stop_times.txt") as f:
#         reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
#         batch = []
#         for row in reader:
#             try:
#                 dist = float(row["shape_dist_traveled"]) if row.get("shape_dist_traveled") else None
#                 batch.append((
#                     row["trip_id"], int(row["stop_sequence"]), row["stop_id"],
#                     row.get("arrival_time", ""), row.get("departure_time", ""),
#                     dist, int(row.get("timepoint", 0) or 0),
#                 ))
#             except (ValueError, KeyError):
#                 continue
#             if len(batch) >= 10000:
#                 cur.executemany("""
#                     INSERT INTO gtfs_stop_times
#                         (trip_id, stop_sequence, stop_id, arrival_time,
#                          departure_time, shape_dist, timepoint)
#                     VALUES (%s,%s,%s,%s,%s,%s,%s)
#                     ON CONFLICT DO NOTHING
#                 """, batch)
#                 count += len(batch)
#                 batch = []
#                 log.info("  stop_times: %d rows...", count)
#         if batch:
#             cur.executemany("""
#                 INSERT INTO gtfs_stop_times
#                     (trip_id, stop_sequence, stop_id, arrival_time,
#                      departure_time, shape_dist, timepoint)
#                 VALUES (%s,%s,%s,%s,%s,%s,%s)
#                 ON CONFLICT DO NOTHING
#             """, batch)
#             count += len(batch)
#     return count


# def load_gtfs_from_zip(zip_bytes: bytes, pool) -> dict:
#     with pool.connection() as conn:
#         conn.execute(CREATE_TABLES_SQL)
#         with conn.transaction():
#             with conn.cursor() as cur:
#                 with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
#                     log.info("Loading routes lookup...")
#                     routes = _load_routes_lookup(zf)
#                     log.info("Loading trips...")
#                     trips_count = _load_trips(zf, routes, cur)
#                     log.info("Loading stops...")
#                     stops_count = _load_stops(zf, cur)
#                     log.info("Loading stop_times (this may take a minute)...")
#                     st_count = _load_stop_times(zf, cur)

#     log.info("GTFS load complete: %d trips, %d stops, %d stop_times",
#              trips_count, stops_count, st_count)
#     return {"trips": trips_count, "stops": stops_count, "stop_times": st_count}


# async def check_and_update_gtfs(pool, force: bool = False) -> bool:
#     """
#     Downloads and loads GTFS zip only if ETag changed (stored in DB).
#     Returns True if data was updated.
#     """
#     last_etag = await asyncio.get_event_loop().run_in_executor(
#         None, _load_etag, pool
#     )

#     async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
#         if not force and last_etag:
#             head = await client.head(GTFS_ZIP_URL)
#             current_etag = head.headers.get("etag", "")
#             if current_etag and current_etag == last_etag:
#                 log.info("GTFS zip unchanged (ETag match) — skipping download.")
#                 return False

#         log.info("Downloading Calgary Transit GTFS zip...")
#         resp = await client.get(GTFS_ZIP_URL)
#         resp.raise_for_status()
#         zip_bytes = resp.content
#         new_etag  = resp.headers.get("etag", "")

#     log.info("Downloaded %d bytes. Loading into DB...", len(zip_bytes))
#     await asyncio.get_event_loop().run_in_executor(
#         None, load_gtfs_from_zip, zip_bytes, pool
#     )

#     if new_etag:
#         await asyncio.get_event_loop().run_in_executor(
#             None, _save_etag, pool, new_etag
#         )

#     return True

# async def start_gtfs_updater(pool) -> None:
#     """
#     Background task — weekly ETag check only.
#     Initial load must be done manually via: python -m app.services.gtfs_updater --force
#     On startup just logs the current state, never downloads automatically.
#     """
#     WEEK_SECONDS = 7 * 24 * 3600

#     # just log current state on startup, never trigger a download
#     try:
#         is_populated = await asyncio.get_event_loop().run_in_executor(
#             None, _tables_populated, pool
#         )
#         if is_populated:
#             log.info("GTFS tables populated — skipping startup download.")
#         else:
#             log.warning(
#                 "GTFS tables empty — run manually: "
#                 "python -m app.services.gtfs_updater --force"
#             )
#     except Exception as e:
#         log.warning("GTFS status check failed: %s", e)

#     # weekly check — only downloads if ETag changed
#     while True:
#         await asyncio.sleep(WEEK_SECONDS)
#         log.info("Weekly GTFS update check...")
#         try:
#             await check_and_update_gtfs(pool, force=False)
#         except Exception as e:
#             log.warning("Weekly GTFS update failed: %s", e)

# if __name__ == "__main__":
#     import sys
#     logging.basicConfig(level=logging.INFO,
#                         format="%(asctime)s %(levelname)s — %(message)s")

#     async def main():
#         from app.services.db import init_pool, get_pool
#         init_pool()
#         pool = get_pool()
#         if not pool:
#             print("No DB pool — check DATABASE_URL")
#             sys.exit(1)
#         force = "--force" in sys.argv
#         updated = await check_and_update_gtfs(pool, force=force)
#         print("Updated:", updated)

#     asyncio.run(main())
import asyncio
import csv
import io
import logging
import zipfile

import httpx
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

GTFS_ZIP_URL = "https://data.calgary.ca/download/npk7-z3bj/application%2Fzip"

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS gtfs_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS gtfs_trips (
    trip_id          TEXT PRIMARY KEY,
    route_id         TEXT,
    route_short_name TEXT,
    headsign         TEXT,
    direction_id     SMALLINT,
    shape_id         TEXT,
    service_id       TEXT
);
CREATE INDEX IF NOT EXISTS idx_gtfs_trips_route ON gtfs_trips (route_short_name);
CREATE INDEX IF NOT EXISTS idx_gtfs_trips_shape ON gtfs_trips (shape_id);

CREATE TABLE IF NOT EXISTS gtfs_stops (
    stop_id    TEXT PRIMARY KEY,
    stop_code  TEXT,
    stop_name  TEXT,
    stop_lat   DOUBLE PRECISION,
    stop_lon   DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS gtfs_stop_times (
    trip_id          TEXT NOT NULL,
    stop_sequence    INTEGER NOT NULL,
    stop_id          TEXT NOT NULL,
    arrival_time     TEXT,
    departure_time   TEXT,
    shape_dist       REAL,
    timepoint        SMALLINT,
    PRIMARY KEY (trip_id, stop_sequence)
);
CREATE INDEX IF NOT EXISTS idx_gst_stop ON gtfs_stop_times (stop_id);
CREATE INDEX IF NOT EXISTS idx_gst_trip ON gtfs_stop_times (trip_id);

CREATE TABLE IF NOT EXISTS gtfs_shapes (
    shape_id            TEXT NOT NULL,
    shape_pt_sequence   INTEGER NOT NULL,
    shape_pt_lat        DOUBLE PRECISION NOT NULL,
    shape_pt_lon        DOUBLE PRECISION NOT NULL,
    shape_dist_traveled REAL,
    PRIMARY KEY (shape_id, shape_pt_sequence)
);
CREATE INDEX IF NOT EXISTS idx_gtfs_shapes_shape ON gtfs_shapes (shape_id);
"""


def _load_etag(pool) -> str | None:
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM gtfs_meta WHERE key = 'etag'")
                row = cur.fetchone()
                return row["value"] if row else None
    except Exception:
        return None


def _save_etag(pool, etag: str) -> None:
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO gtfs_meta (key, value) VALUES ('etag', %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """,
                    (etag,),
                )
    except Exception as exc:
        log.warning("Failed to save ETag: %s", exc)


def _tables_populated(pool) -> bool:
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) as n FROM gtfs_stops")
                return cur.fetchone()["n"] >= 1000
    except Exception:
        return False


def _load_routes_lookup(zf: zipfile.ZipFile) -> dict[str, str]:
    lookup = {}
    with zf.open("routes.txt") as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
        for row in reader:
            lookup[row["route_id"]] = row["route_short_name"]
    return lookup


def _load_trips(zf: zipfile.ZipFile, routes: dict[str, str], cur) -> int:
    cur.execute("TRUNCATE gtfs_trips")
    count = 0
    with zf.open("trips.txt") as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
        batch = []
        for row in reader:
            short = routes.get(row["route_id"], row.get("route_short_name", ""))
            batch.append((
                row["trip_id"],
                row["route_id"],
                short,
                row.get("trip_headsign", ""),
                int(row.get("direction_id", 0) or 0),
                row.get("shape_id", ""),
                row.get("service_id", ""),
            ))
            if len(batch) >= 5000:
                cur.executemany(
                    """
                    INSERT INTO gtfs_trips
                        (trip_id, route_id, route_short_name, headsign,
                         direction_id, shape_id, service_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (trip_id) DO UPDATE SET
                        route_id         = EXCLUDED.route_id,
                        route_short_name = EXCLUDED.route_short_name,
                        headsign         = EXCLUDED.headsign,
                        direction_id     = EXCLUDED.direction_id,
                        shape_id         = EXCLUDED.shape_id,
                        service_id       = EXCLUDED.service_id
                    """,
                    batch,
                )
                count += len(batch)
                batch = []
        if batch:
            cur.executemany(
                """
                INSERT INTO gtfs_trips
                    (trip_id, route_id, route_short_name, headsign,
                     direction_id, shape_id, service_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (trip_id) DO UPDATE SET
                    route_id         = EXCLUDED.route_id,
                    route_short_name = EXCLUDED.route_short_name,
                    headsign         = EXCLUDED.headsign,
                    direction_id     = EXCLUDED.direction_id,
                    shape_id         = EXCLUDED.shape_id,
                    service_id       = EXCLUDED.service_id
                """,
                batch,
            )
            count += len(batch)
    return count


def _load_stops(zf: zipfile.ZipFile, cur) -> int:
    cur.execute("TRUNCATE gtfs_stops")
    count = 0
    with zf.open("stops.txt") as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
        batch = []
        for row in reader:
            try:
                batch.append((
                    row["stop_id"],
                    row.get("stop_code", ""),
                    row.get("stop_name", ""),
                    float(row["stop_lat"]),
                    float(row["stop_lon"]),
                ))
            except (ValueError, KeyError):
                continue
            if len(batch) >= 2000:
                cur.executemany(
                    """
                    INSERT INTO gtfs_stops
                        (stop_id, stop_code, stop_name, stop_lat, stop_lon)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (stop_id) DO UPDATE SET
                        stop_name = EXCLUDED.stop_name,
                        stop_lat  = EXCLUDED.stop_lat,
                        stop_lon  = EXCLUDED.stop_lon
                    """,
                    batch,
                )
                count += len(batch)
                batch = []
        if batch:
            cur.executemany(
                """
                INSERT INTO gtfs_stops
                    (stop_id, stop_code, stop_name, stop_lat, stop_lon)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (stop_id) DO UPDATE SET
                    stop_name = EXCLUDED.stop_name,
                    stop_lat  = EXCLUDED.stop_lat,
                    stop_lon  = EXCLUDED.stop_lon
                """,
                batch,
            )
            count += len(batch)
    return count


def _load_stop_times(zf: zipfile.ZipFile, cur) -> int:
    cur.execute("TRUNCATE gtfs_stop_times")
    count = 0
    with zf.open("stop_times.txt") as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
        batch = []
        for row in reader:
            try:
                dist = float(row["shape_dist_traveled"]) if row.get("shape_dist_traveled") else None
                batch.append((
                    row["trip_id"],
                    int(row["stop_sequence"]),
                    row["stop_id"],
                    row.get("arrival_time", ""),
                    row.get("departure_time", ""),
                    dist,
                    int(row.get("timepoint", 0) or 0),
                ))
            except (ValueError, KeyError):
                continue
            if len(batch) >= 10000:
                cur.executemany(
                    """
                    INSERT INTO gtfs_stop_times
                        (trip_id, stop_sequence, stop_id, arrival_time,
                         departure_time, shape_dist, timepoint)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT DO NOTHING
                    """,
                    batch,
                )
                count += len(batch)
                batch = []
                log.info("  stop_times: %d rows...", count)
        if batch:
            cur.executemany(
                """
                INSERT INTO gtfs_stop_times
                    (trip_id, stop_sequence, stop_id, arrival_time,
                     departure_time, shape_dist, timepoint)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
                """,
                batch,
            )
            count += len(batch)
    return count


def _load_shapes(zf: zipfile.ZipFile, cur) -> int:
    cur.execute("TRUNCATE gtfs_shapes")
    count = 0
    with zf.open("shapes.txt") as f:
        reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
        batch = []
        for row in reader:
            try:
                dist = float(row["shape_dist_traveled"]) if row.get("shape_dist_traveled") else None
                batch.append((
                    row["shape_id"],
                    int(row["shape_pt_sequence"]),
                    float(row["shape_pt_lat"]),
                    float(row["shape_pt_lon"]),
                    dist,
                ))
            except (ValueError, KeyError):
                continue
            if len(batch) >= 10000:
                cur.executemany(
                    """
                    INSERT INTO gtfs_shapes
                        (shape_id, shape_pt_sequence, shape_pt_lat, shape_pt_lon, shape_dist_traveled)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (shape_id, shape_pt_sequence) DO UPDATE SET
                        shape_pt_lat = EXCLUDED.shape_pt_lat,
                        shape_pt_lon = EXCLUDED.shape_pt_lon,
                        shape_dist_traveled = EXCLUDED.shape_dist_traveled
                    """,
                    batch,
                )
                count += len(batch)
                batch = []
                log.info("  shapes: %d rows...", count)
        if batch:
            cur.executemany(
                """
                INSERT INTO gtfs_shapes
                    (shape_id, shape_pt_sequence, shape_pt_lat, shape_pt_lon, shape_dist_traveled)
                VALUES (%s,%s,%s,%s,%s)
                ON CONFLICT (shape_id, shape_pt_sequence) DO UPDATE SET
                    shape_pt_lat = EXCLUDED.shape_pt_lat,
                    shape_pt_lon = EXCLUDED.shape_pt_lon,
                    shape_dist_traveled = EXCLUDED.shape_dist_traveled
                """,
                batch,
            )
            count += len(batch)
    return count


def load_gtfs_from_zip(zip_bytes: bytes, pool) -> dict:
    with pool.connection() as conn:
        conn.execute(CREATE_TABLES_SQL)
        with conn.transaction():
            with conn.cursor() as cur:
                with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                    log.info("Loading routes lookup...")
                    routes = _load_routes_lookup(zf)
                    log.info("Loading trips...")
                    trips_count = _load_trips(zf, routes, cur)
                    log.info("Loading stops...")
                    stops_count = _load_stops(zf, cur)
                    log.info("Loading stop_times (this may take a minute)...")
                    stop_times_count = _load_stop_times(zf, cur)
                    log.info("Loading shapes (this may take a minute)...")
                    shapes_count = _load_shapes(zf, cur)

    log.info(
        "GTFS load complete: %d trips, %d stops, %d stop_times, %d shapes",
        trips_count,
        stops_count,
        stop_times_count,
        shapes_count,
    )
    return {
        "trips": trips_count,
        "stops": stops_count,
        "stop_times": stop_times_count,
        "shapes": shapes_count,
    }


async def check_and_update_gtfs(pool, force: bool = False) -> bool:
    last_etag = await asyncio.get_event_loop().run_in_executor(None, _load_etag, pool)

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        if not force and last_etag:
            head = await client.head(GTFS_ZIP_URL)
            current_etag = head.headers.get("etag", "")
            if current_etag and current_etag == last_etag:
                log.info("GTFS zip unchanged (ETag match) — skipping download.")
                return False

        log.info("Downloading Calgary Transit GTFS zip...")
        resp = await client.get(GTFS_ZIP_URL)
        resp.raise_for_status()
        zip_bytes = resp.content
        new_etag = resp.headers.get("etag", "")

    log.info("Downloaded %d bytes. Loading into DB...", len(zip_bytes))
    await asyncio.get_event_loop().run_in_executor(None, load_gtfs_from_zip, zip_bytes, pool)

    if new_etag:
        await asyncio.get_event_loop().run_in_executor(None, _save_etag, pool, new_etag)

    return True


async def start_gtfs_updater(pool) -> None:
    WEEK_SECONDS = 7 * 24 * 3600

    try:
        is_populated = await asyncio.get_event_loop().run_in_executor(None, _tables_populated, pool)
        if is_populated:
            log.info("GTFS tables populated — skipping startup download.")
        else:
            log.warning(
                "GTFS tables empty — run manually: python -m app.services.gtfs_updater --force"
            )
    except Exception as exc:
        log.warning("GTFS status check failed: %s", exc)

    while True:
        await asyncio.sleep(WEEK_SECONDS)
        log.info("Weekly GTFS update check...")
        try:
            await check_and_update_gtfs(pool, force=False)
        except Exception as exc:
            log.warning("Weekly GTFS update failed: %s", exc)


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")

    async def main():
        from app.services.db import get_pool, init_pool

        init_pool()
        pool = get_pool()
        if not pool:
            print("No DB pool — check DATABASE_URL")
            sys.exit(1)
        force = "--force" in sys.argv
        updated = await check_and_update_gtfs(pool, force=force)
        print("Updated:", updated)

    asyncio.run(main())
