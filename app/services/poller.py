# app/services/poller.py
# Fetches Calgary Transit GTFS-RT vehicle positions every 30 seconds,
# decodes the protobuf, and writes to Postgres via db.upsert_vehicles().
# Also trims the raw table every 10 minutes (replaces pg_cron).

import asyncio
import logging
import httpx
from google.transit import gtfs_realtime_pb2

from app.services.db import upsert_vehicles, get_pool

log = logging.getLogger(__name__)

FEED_URL       = "https://data.calgary.ca/download/am7c-qe3u/application%2Foctet-stream"
POLL_INTERVAL  = 30   # seconds between feed fetches
TRIM_INTERVAL  = 600  # seconds between cleanup runs (10 minutes)
KEEP_HOURS     = 2    # how many hours of raw history to retain


def _decode_feed(raw_bytes: bytes) -> list[dict]:
    """Parse protobuf bytes → list of vehicle dicts ready for upsert."""
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(raw_bytes)

    vehicles = []
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        v = entity.vehicle

        if not v.HasField("position"):
            continue

        vehicle_id = v.vehicle.id or entity.id
        if not vehicle_id:
            continue

        row = {
            "vehicle_id": str(vehicle_id),
            "lat":        v.position.latitude,
            "lon":        v.position.longitude,
            "bearing":    int(v.position.bearing) if v.position.bearing else None,
            "speed":      float(v.position.speed) if v.position.speed else None,
            "route_id":   v.trip.route_id or None,
            "occupancy":  None,
        }

        if v.HasField("occupancy_status"):
            row["occupancy"] = gtfs_realtime_pb2.VehiclePosition.OccupancyStatus.Name(
                v.occupancy_status
            )

        vehicles.append(row)

    return vehicles


async def poll_once() -> int:
    """Fetch feed, decode, write to DB. Returns number of vehicles written."""
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(FEED_URL)
        resp.raise_for_status()

    vehicles = _decode_feed(resp.content)
    if vehicles:
        upsert_vehicles(vehicles)
        log.info("Polled %d vehicles from Calgary Transit feed.", len(vehicles))
    else:
        log.warning("Feed returned 0 vehicles — may be empty or malformed.")

    return len(vehicles)


def trim_raw_table() -> None:
    """Delete raw rows older than KEEP_HOURS. Runs in the poller loop."""
    pool = get_pool()
    if not pool:
        return
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM vehicle_positions_raw
                WHERE fetched_at < now() - INTERVAL '%s hours'
            """, (KEEP_HOURS,))
            deleted = cur.rowcount
    if deleted:
        log.info("Trimmed %d old rows from vehicle_positions_raw.", deleted)


async def start_poller() -> None:
    """
    Infinite loop — poll every POLL_INTERVAL seconds.
    Every TRIM_INTERVAL seconds also cleans up old raw rows.
    Errors are caught and logged so one bad fetch never kills the loop.
    """
    await asyncio.sleep(2)  # let DB pool finish initialising

    if get_pool() is None:
        log.warning("No DB pool available — poller will not start.")
        return

    log.info("Calgary Transit poller started (interval=%ds).", POLL_INTERVAL)

    polls_since_trim = 0
    trim_every_n = TRIM_INTERVAL // POLL_INTERVAL  # 600 / 30 = 20 polls

    while True:
        try:
            await poll_once()
            polls_since_trim += 1

            if polls_since_trim >= trim_every_n:
                trim_raw_table()
                polls_since_trim = 0

        except httpx.HTTPError as e:
            log.error("HTTP error fetching transit feed: %s", e)
        except Exception as e:
            log.exception("Unexpected error in transit poller: %s", e)

        await asyncio.sleep(POLL_INTERVAL)