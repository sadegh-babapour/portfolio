from fastapi import FastAPI
from fastapi.responses import JSONResponse
from app.services.db import fetch_latest_vehicles

from fastapi.staticfiles import StaticFiles
from nicegui import ui
from nicegui import app as fastapi_app
import asyncio
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

# Mount static files
fastapi_app.mount('/static', StaticFiles(directory='static'), name='static')
fastapi_app.mount('/map', StaticFiles(directory='frontend/dist', html=True), name='frontend')

# Components
from app.components.footer import footer

# DB pool + poller (transit map)
from app.services.db import init_pool
from app.services.poller import start_poller


def _import_pages():
    import app.pages.home
    import app.pages.about
    import app.pages.resume
    import app.pages.projects
    import app.pages.contact
    import app.pages.dashboard
    import app.pages.transit_map   # was NEW
    # import app.pages.transit_map_v2  # v2 — hidden from navbar, test at /transitv2


@fastapi_app.on_startup
async def startup():
    """Initialise DB pool and launch the transit poller as a background task."""
    init_pool()
    asyncio.create_task(start_poller())


@fastapi_app.get('/api/vehicles')
async def vehicles_api():
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, fetch_latest_vehicles)
    return JSONResponse([
        {k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in row.items()}
        for row in data
    ])


if __name__ in {"__main__", "__mp_main__"}:
    _import_pages()
    ui.run(
        title='My Portfolio',
        port=int(os.getenv("PORT", default=8086)),
        host='0.0.0.0',
        dark=False,
    )
# python -m app.main #local