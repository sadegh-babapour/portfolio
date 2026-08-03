from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from nicegui import app as fastapi_app
from nicegui import ui
import asyncio
import logging
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

# ── static mounts ─────────────────────────────────────────────────
fastapi_app.mount('/static', StaticFiles(directory='static'), name='static')
# fastapi_app.mount('/map', StaticFiles(directory='frontend/dist', html=True), name='frontend')
fastapi_app.mount(
    '/calgary-transit-live',
    StaticFiles(directory='frontend/dist', html=True),
    name='calgary-transit-live',
)

# ── components ────────────────────────────────────────────────────
from app.components.footer import footer  # noqa: E402,F401

# ── services ──────────────────────────────────────────────────────
from app.services.db import (  # noqa: E402
    create_daily_sample,
    fetch_all_route_names,
    fetch_latest_vehicles,
    fetch_lrt_shape,
    fetch_lrt_stations,
    fetch_lrt_routes,
    fetch_lrt_vehicles,
    fetch_route_geometry,
    fetch_stops_for_route,
    fetch_vehicle_full_history,
    fetch_vehicles_history,
    get_or_create_daily_sample,
    get_pool,
    init_pool,
)
from app.services.gtfs_updater import start_gtfs_updater  # noqa: E402
from app.services.poller import start_poller  # noqa: E402
from app.services import poller as poller_service  # noqa: E402
from app.services import schedule  # noqa: E402


# ── pages ─────────────────────────────────────────────────────────
def _import_pages():
    import app.pages.about  # noqa: F401
    import app.pages.contact  # noqa: F401
    import app.pages.dashboard  # noqa: F401
    import app.pages.home  # noqa: F401
    import app.pages.projects  # noqa: F401
    import app.pages.resume  # noqa: F401
    import app.pages.transit_map  # noqa: F401


# ── startup ───────────────────────────────────────────────────────
@fastapi_app.on_startup
async def startup():
    init_pool()
    asyncio.create_task(start_poller())
    asyncio.create_task(start_gtfs_updater(get_pool()))


# ── helpers ───────────────────────────────────────────────────────
def _serialize(row: dict) -> dict:
    return {k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in row.items()}


# ── vehicle endpoints ─────────────────────────────────────────────
@fastapi_app.get('/api/vehicles')
async def vehicles_api():
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, fetch_latest_vehicles)
    return JSONResponse([_serialize(dict(r)) for r in data])


@fastapi_app.get('/api/vehicles/tracked')
async def tracked_vehicles_api():
    loop = asyncio.get_event_loop()
    sample = await loop.run_in_executor(None, lambda: get_or_create_daily_sample(3))
    all_ids = [vid for ids in sample.values() for vid in ids]

    if not all_ids:
        return JSONResponse({'sample': {}, 'positions': [], 'history': {}})

    positions = await loop.run_in_executor(
        None, lambda: fetch_latest_vehicles(vehicle_ids=all_ids)
    )
    history = await loop.run_in_executor(
        None, lambda: fetch_vehicles_history(all_ids, limit=60)
    )

    return JSONResponse(
        {
            'sample': sample,
            'positions': [_serialize(dict(r)) for r in positions],
            'history': {
                vid: [_serialize(pt) for pt in pts]
                for vid, pts in history.items()
            },
        }
    )


@fastapi_app.get('/api/vehicles/by-routes')
async def vehicles_by_routes_api(routes: str):
    route_ids = [route.strip().upper() for route in routes.split(',') if route.strip()]
    if not route_ids:
        return JSONResponse({'routes': [], 'positions': [], 'history': {}})

    loop = asyncio.get_event_loop()
    positions = await loop.run_in_executor(
        None, lambda: fetch_latest_vehicles(route_ids=route_ids)
    )
    vehicle_ids = [row['vehicle_id'] for row in positions]
    history = await loop.run_in_executor(
        None, lambda: fetch_vehicles_history(vehicle_ids, limit=60)
    ) if vehicle_ids else {}

    return JSONResponse(
        {
            'routes': route_ids,
            'positions': [_serialize(dict(r)) for r in positions],
            'history': {
                vid: [_serialize(pt) for pt in pts]
                for vid, pts in history.items()
            },
        }
    )


@fastapi_app.post('/api/vehicles/resample')
async def resample_api():
    loop = asyncio.get_event_loop()
    sample = await loop.run_in_executor(None, create_daily_sample)
    return JSONResponse({'sample': sample})


# ── route endpoints ───────────────────────────────────────────────
@fastapi_app.get('/api/routes/lrt')
async def lrt_routes_api():
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, fetch_lrt_routes)
    return JSONResponse(
        [
            {
                'route_short_name': r['route_short_name'],
                'route_long_name': r['route_long_name'],
                'coordinates': r['coordinates'],
            }
            for r in data
        ]
    )


@fastapi_app.get('/api/routes/{route_id}/geometry')
async def route_geometry_api(route_id: str):
    route_id = route_id.strip().upper()
    loop = asyncio.get_event_loop()
    coords = await loop.run_in_executor(None, lambda: fetch_route_geometry(route_id))
    if not coords:
        raise HTTPException(status_code=404, detail=f"Route {route_id} not found")
    return JSONResponse({'route_id': route_id, 'coordinates': coords})


@fastapi_app.get('/api/routes/{route_id}/stops')
async def route_stops_api(route_id: str):
    route_id = route_id.strip().upper()
    loop = asyncio.get_event_loop()
    stops = await loop.run_in_executor(None, lambda: fetch_stops_for_route(route_id))
    return JSONResponse([_serialize(dict(s)) for s in stops])


@fastapi_app.get('/api/routes')
async def all_routes_api():
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, fetch_all_route_names)
    return JSONResponse([dict(r) for r in data])


# ── LRT endpoints ─────────────────────────────────────────────────
@fastapi_app.get('/api/lrt/stations')
async def lrt_stations_api():
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, fetch_lrt_stations)
    return JSONResponse([dict(r) for r in data])


@fastapi_app.get('/api/lrt/shape/{line}')
async def lrt_shape_api(line: str):
    if line not in ('red', 'blue'):
        raise HTTPException(status_code=400, detail="line must be 'red' or 'blue'")
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, lambda: fetch_lrt_shape(line))
    return JSONResponse([[r['lat'], r['lon']] for r in data])


@fastapi_app.get('/api/lrt/vehicles')
async def lrt_vehicles_api():
    loop = asyncio.get_event_loop()
    vehicles = await loop.run_in_executor(None, fetch_lrt_vehicles)
    result = []
    for vehicle in vehicles:
        history = await loop.run_in_executor(
            None, lambda vid=vehicle['vehicle_id']: fetch_vehicle_full_history(vid)
        )
        result.append({
            **_serialize(dict(vehicle)),
            'history': [_serialize(dict(h)) for h in history],
        })
    return JSONResponse(result)


# ── poller controls ───────────────────────────────────────────────
@fastapi_app.get('/api/poller/status')
async def poller_status_api():
    return JSONResponse({
        'active': schedule.should_poll(),
        'in_hours': schedule.is_operating_hours(),
    })


@fastapi_app.post('/api/poller/pause')
async def poller_pause_api():
    poller_service.pause()
    return JSONResponse({'active': False})


@fastapi_app.post('/api/poller/resume')
async def poller_resume_api():
    poller_service.resume()
    return JSONResponse({'active': True})


# ── debug ─────────────────────────────────────────────────────────
@fastapi_app.get('/api/debug/raw-feed')
async def raw_feed_debug():
    import httpx
    from google.transit import gtfs_realtime_pb2

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        resp = await client.get(
            "https://data.calgary.ca/download/am7c-qe3u/application%2Foctet-stream"
        )
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(resp.content)
    results = []
    for entity in feed.entity[:10]:
        if entity.HasField("vehicle"):
            v = entity.vehicle
            results.append(
                {
                    "vehicle_id": v.vehicle.id,
                    "vehicle_label": v.vehicle.label,
                    "trip_id": v.trip.trip_id,
                    "route_id": v.trip.route_id,
                    "direction_id": v.trip.direction_id,
                    "stop_id": v.stop_id,
                    "stop_sequence": v.current_stop_sequence,
                    "timestamp": v.timestamp,
                }
            )
    return JSONResponse(results)


# ── run ───────────────────────────────────────────────────────────
if __name__ in {"__main__", "__mp_main__"}:
    _import_pages()
    ui.run(
        title='My Portfolio',
        port=int(os.getenv("PORT", default=8086)),
        host='0.0.0.0',
        dark=False,
    )
