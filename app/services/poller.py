
# import asyncio
# import logging
# import httpx
# from google.transit import gtfs_realtime_pb2
# from app.services.db import upsert_vehicles, get_pool, trim_raw_table

# log = logging.getLogger(__name__)

# FEED_URL      = "https://data.calgary.ca/download/am7c-qe3u/application%2Foctet-stream"
# POLL_INTERVAL = 30
# TRIM_INTERVAL = 600

# _running = {'active': True}


# def pause():
#     _running['active'] = False
#     log.info("Transit poller paused.")


# def resume():
#     _running['active'] = True
#     log.info("Transit poller resumed.")


# def is_active() -> bool:
#     return _running['active']


# def _decode_feed(raw_bytes: bytes) -> list[dict]:
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
#             "vehicle_id": str(vehicle_id),
#             "lat":        v.position.latitude,
#             "lon":        v.position.longitude,
#             "bearing":    int(v.position.bearing) if v.position.bearing else None,
#             "speed":      float(v.position.speed) if v.position.speed else None,
#             "route_id":   v.trip.route_id or None,
#             "occupancy":  None,
#         }
#         if v.HasField("occupancy_status"):
#             row["occupancy"] = gtfs_realtime_pb2.VehiclePosition.OccupancyStatus.Name(
#                 v.occupancy_status
#             )
#         vehicles.append(row)
#     return vehicles


# async def poll_once() -> int:
#     async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
#         resp = await client.get(FEED_URL)
#         resp.raise_for_status()
#     vehicles = _decode_feed(resp.content)
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
#     polls_since_trim = 0
#     trim_every_n = TRIM_INTERVAL // POLL_INTERVAL
#     while True:
#         try:
#             if _running['active']:
#                 await poll_once()
#                 polls_since_trim += 1
#                 if polls_since_trim >= trim_every_n:
#                     await asyncio.get_event_loop().run_in_executor(None, trim_raw_table)
#                     polls_since_trim = 0
#             else:
#                 log.debug("Poller paused — skipping fetch.")
#         except httpx.HTTPError as e:
#             log.error("HTTP error fetching transit feed: %s", e)
#         except Exception as e:
#             log.exception("Unexpected error in transit poller: %s", e)
#         await asyncio.sleep(POLL_INTERVAL)
# app/services/poller.py
import asyncio
import logging
import httpx
from google.transit import gtfs_realtime_pb2
from app.services.db import upsert_vehicles, get_pool, trim_raw_table
from app.services import schedule

log = logging.getLogger(__name__)

FEED_URL      = "https://data.calgary.ca/download/am7c-qe3u/application%2Foctet-stream"
POLL_INTERVAL = 30
TRIM_INTERVAL = 600


def pause():
    schedule.manual_pause()


def resume():
    schedule.manual_resume()


def is_active() -> bool:
    return schedule.should_poll()


def _decode_feed(raw_bytes: bytes) -> list[dict]:
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
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(FEED_URL)
        resp.raise_for_status()
    vehicles = _decode_feed(resp.content)
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

    # start schedule monitor as separate task
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

        except httpx.HTTPError as e:
            log.error("HTTP error fetching transit feed: %s", e)
        except Exception as e:
            log.exception("Unexpected error in transit poller: %s", e)

        await asyncio.sleep(POLL_INTERVAL)