# import asyncio
# import logging
# import httpx
# from google.transit import gtfs_realtime_pb2
# from app.services.db import upsert_vehicles, get_pool, trim_raw_table, fetch_trips_batch
# from app.services import schedule

# log = logging.getLogger(__name__)

# FEED_URL      = "https://data.calgary.ca/download/am7c-qe3u/application%2Foctet-stream"
# POLL_INTERVAL = 30
# TRIM_INTERVAL = 300   # trim every 5 minutes


# def pause():
#     schedule.manual_pause()


# def resume():
#     schedule.manual_resume()


# def is_active() -> bool:
#     return schedule.should_poll()


# def _decode_feed(raw_bytes: bytes) -> list[dict]:
#     """
#     Parse vehicle positions protobuf.
#     Captures trip_id and direction_id for later enrichment.
#     route_id enrichment happens after via gtfs_trips table.
#     """
#     feed = gtfs_realtime_pb2.FeedMessage()
#     feed.ParseFromString(raw_bytes)

#     vehicles = []
#     for entity in feed.entity:
#         if not entity.HasField("vehicle"):
#             continue
#         v = entity.vehicle
#         if not v.HasField("position"):
#             continue
#         vehicle_id = v.vehicle.id or entity.id
#         if not vehicle_id:
#             continue

#         row = {
#             "vehicle_id":   str(vehicle_id),
#             "lat":          v.position.latitude,
#             "lon":          v.position.longitude,
#             "bearing":      int(v.position.bearing) if v.position.bearing else None,
#             "speed":        float(v.position.speed) if v.position.speed else None,
#             "route_id":     v.trip.route_id or None,
#             "trip_id":      v.trip.trip_id or None,
#             "direction_id": v.trip.direction_id if v.trip.direction_id else None,
#             "headsign":     None,
#             "occupancy":    None,
#         }

#         if v.HasField("occupancy_status"):
#             row["occupancy"] = gtfs_realtime_pb2.VehiclePosition.OccupancyStatus.Name(
#                 v.occupancy_status
#             )

#         vehicles.append(row)

#     return vehicles


# def _enrich_with_trips(vehicles: list[dict]) -> list[dict]:
#     trip_ids = [v["trip_id"] for v in vehicles if v.get("trip_id")]
#     if not trip_ids:
#         return vehicles
#     try:
#         trips = fetch_trips_batch(trip_ids)
#         log.info("Enriched %d/%d vehicles with trip data", len(trips), len(vehicles))  # ADD THIS
#     except Exception as e:
#         log.debug("Trip enrichment skipped: %s", e)
#         return vehicles

#     for v in vehicles:
#         tid = v.get("trip_id")
#         if tid and tid in trips:
#             t = trips[tid]
#             if not v["route_id"]:
#                 v["route_id"] = t.get("route_short_name")
#             v["headsign"] = t.get("headsign")

#     return vehicles






# async def poll_once() -> int:
#     async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
#         resp = await client.get(FEED_URL)
#         resp.raise_for_status()

#     vehicles = _decode_feed(resp.content)
#     vehicles = _enrich_with_trips(vehicles)  # direct call, no executor
#     # TEMP DEBUG
#     sample = [v for v in vehicles[:3]]
#     log.info("Sample before upsert: %s", [(v['vehicle_id'], v.get('trip_id'), v.get('route_id'), v.get('headsign')) for v in sample])

#     if vehicles:
#         await asyncio.get_event_loop().run_in_executor(None, upsert_vehicles, vehicles)
    
#         log.info("Polled %d vehicles from Calgary Transit feed.", len(vehicles))
#     else:
#         log.warning("Feed returned 0 vehicles.")

#     return len(vehicles)


# async def start_poller() -> None:
#     await asyncio.sleep(2)

#     if get_pool() is None:
#         log.warning("No DB pool available — poller will not start.")
#         return

#     log.info("Calgary Transit poller started (interval=%ds).", POLL_INTERVAL)

#     asyncio.create_task(schedule.schedule_monitor())

#     polls_since_trim = 0
#     trim_every_n     = TRIM_INTERVAL // POLL_INTERVAL  # 10 polls

#     while True:
#         try:
#             if schedule.should_poll():
#                 await poll_once()
#                 polls_since_trim += 1

#                 if polls_since_trim >= trim_every_n:
#                     await asyncio.get_event_loop().run_in_executor(None, trim_raw_table)
#                     polls_since_trim = 0
#             else:
#                 log.debug("Outside operating hours — skipping fetch.")

#         except httpx.HTTPError as e:
#             log.error("HTTP error fetching transit feed: %s", e)
#         except Exception as e:
#             log.exception("Unexpected error in transit poller: %s", e)

#         await asyncio.sleep(POLL_INTERVAL)
import asyncio
import logging

import httpx
from google.transit import gtfs_realtime_pb2

from app.services import schedule
from app.services.db import fetch_trips_batch, get_pool, trim_raw_table, upsert_vehicles

log = logging.getLogger(__name__)

FEED_URL = "https://data.calgary.ca/download/am7c-qe3u/application%2Foctet-stream"
POLL_INTERVAL = 30
TRIM_INTERVAL = 300


def pause():
    schedule.manual_pause()


def resume():
    schedule.manual_resume()


def is_active() -> bool:
    return schedule.should_poll()


def _decode_feed(raw_bytes: bytes) -> list[dict]:
    """
    Parse vehicle positions protobuf.
    Capture trip_id and raw route_id, then normalize with GTFS in enrichment.
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(raw_bytes)

    vehicles: list[dict] = []
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
            "lat": v.position.latitude,
            "lon": v.position.longitude,
            "bearing": int(v.position.bearing) if v.position.bearing else None,
            "speed": float(v.position.speed) if v.position.speed else None,
            "route_id": v.trip.route_id or None,
            "trip_id": v.trip.trip_id or None,
            # proto3 scalar fields default to 0, so keep it only when trip info exists
            "direction_id": int(v.trip.direction_id) if v.trip.trip_id or v.trip.route_id else None,
            "headsign": None,
            "occupancy": None,
        }

        if v.HasField("occupancy_status"):
            row["occupancy"] = gtfs_realtime_pb2.VehiclePosition.OccupancyStatus.Name(
                v.occupancy_status
            )

        vehicles.append(row)

    return vehicles


def _enrich_with_trips(vehicles: list[dict]) -> list[dict]:
    trip_ids = [v["trip_id"] for v in vehicles if v.get("trip_id")]
    if not trip_ids:
        return vehicles

    try:
        trips = fetch_trips_batch(trip_ids)
    except Exception as exc:
        log.debug("Trip enrichment skipped: %s", exc)
        return vehicles

    for vehicle in vehicles:
        trip_id = vehicle.get("trip_id")
        if not trip_id or trip_id not in trips:
            continue
        trip = trips[trip_id]
        # Always prefer the normalized GTFS route_short_name over the raw feed route_id.
        vehicle["route_id"] = trip.get("route_short_name") or vehicle.get("route_id")
        vehicle["headsign"] = trip.get("headsign") or vehicle.get("headsign")
        if vehicle.get("direction_id") is None:
            vehicle["direction_id"] = trip.get("direction_id")

    return vehicles


async def poll_once() -> int:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(FEED_URL)
        resp.raise_for_status()

    vehicles = _decode_feed(resp.content)
    vehicles = _enrich_with_trips(vehicles)

    if vehicles:
        await asyncio.get_event_loop().run_in_executor(None, upsert_vehicles, vehicles)
        log.info("Polled %d vehicles from Calgary Transit feed.", len(vehicles))
    else:
        log.warning("Feed returned 0 vehicles.")

    return len(vehicles)


async def start_poller() -> None:
    await asyncio.sleep(2)

    if get_pool() is None:
        log.warning("No DB pool available — poller will not start.")
        return

    log.info("Calgary Transit poller started (interval=%ds).", POLL_INTERVAL)

    asyncio.create_task(schedule.schedule_monitor())

    polls_since_trim = 0
    trim_every_n = TRIM_INTERVAL // POLL_INTERVAL

    while True:
        try:
            if schedule.should_poll():
                await poll_once()
                polls_since_trim += 1

                if polls_since_trim >= trim_every_n:
                    await asyncio.get_event_loop().run_in_executor(None, trim_raw_table)
                    polls_since_trim = 0
            else:
                log.debug("Outside operating hours — skipping fetch.")

        except httpx.HTTPError as exc:
            log.error("HTTP error fetching transit feed: %s", exc)
        except Exception as exc:
            log.exception("Unexpected error in transit poller: %s", exc)

        await asyncio.sleep(POLL_INTERVAL)

