from __future__ import annotations

import asyncio
import logging

from fastapi import Request
from nicegui import app as fastapi_app

from app.admin.service import (
    build_admin_summary,
    record_page_view,
    require_admin,
    tracked_page_path,
)
from app.auth.service import SESSION_COOKIE


log = logging.getLogger(__name__)


@fastapi_app.middleware("http")
async def collect_anonymous_page_render(request: Request, call_next):
    response = await call_next(request)
    path = tracked_page_path(request.url.path)
    if request.method == "GET" and path is not None and response.status_code < 400:
        try:
            await asyncio.to_thread(record_page_view, path)
        except Exception:
            log.exception("Unable to record an anonymous page render")
    return response


@fastapi_app.get("/api/admin/summary", include_in_schema=False)
def admin_summary(request: Request):
    require_admin(request.cookies.get(SESSION_COOKIE))
    return build_admin_summary()
