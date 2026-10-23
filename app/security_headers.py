"""Standard browser security headers on every HTTP response.

No Content-Security-Policy yet: NiceGUI pages depend on inline scripts and styles,
so a useful policy is a separate piece of work.
"""
from __future__ import annotations

from fastapi import Request
from nicegui import app as fastapi_app


SECURITY_HEADERS = {
    # HTTPS only for a year; browsers ignore this over plain HTTP (local runs).
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    # The résumé viewer is framed by our own pages; nobody else may frame the site.
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # The transit map's "near me" search is the only browser feature in use.
    "Permissions-Policy": "geolocation=(self), camera=(), microphone=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}


@fastapi_app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response
