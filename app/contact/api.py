from __future__ import annotations

import logging
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from nicegui import app as fastapi_app
from pydantic import BaseModel, Field

from app.contact.config import ContactSettings
from app.contact.security import ContactValidationError, new_csrf_token, verify_csrf_token
from app.contact.service import (
    ContactInput,
    RateLimitExceeded,
    accept_contact,
    verify_and_deliver,
)


log = logging.getLogger(__name__)
CSRF_COOKIE = "portfolio_contact_csrf"


class ContactSubmission(BaseModel):
    name: str = Field(max_length=200)
    email: str = Field(max_length=300)
    subject: str = Field(max_length=200)
    category: str = Field(max_length=80)
    message: str = Field(max_length=6000)
    website: str = Field(default="", max_length=200)
    turnstile_token: str = Field(max_length=2048)


def _require_settings() -> ContactSettings:
    settings = ContactSettings.from_env()
    if not settings.configured:
        log.error("Contact workflow is missing configuration: %s", settings.missing())
        raise HTTPException(status_code=503, detail="Contact service is temporarily unavailable")
    return settings


def _request_ip(request: Request) -> str:
    return request.headers.get("cf-connecting-ip") or (
        request.client.host if request.client else "unknown"
    )


def _validate_origin(request: Request, allowed_origins: tuple[str, ...]) -> None:
    origin = request.headers.get("origin", "")
    supplied = urlsplit(origin)
    accepted = {
        (parsed.scheme, parsed.netloc)
        for parsed in (urlsplit(value) for value in allowed_origins)
    }
    if (supplied.scheme, supplied.netloc) not in accepted:
        raise HTTPException(status_code=403, detail="Request origin is not allowed")


def _validate_csrf(request: Request, settings: ContactSettings) -> None:
    cookie_token = request.cookies.get(CSRF_COOKIE, "")
    header_token = request.headers.get("x-csrf-token", "")
    if cookie_token != header_token or not verify_csrf_token(
        header_token, settings.token_pepper
    ):
        raise HTTPException(status_code=403, detail="Form session expired; reload and try again")


@fastapi_app.get("/api/contact/csrf", include_in_schema=False)
async def contact_csrf(response: Response):
    settings = _require_settings()
    token = new_csrf_token(settings.token_pepper)
    response.set_cookie(
        CSRF_COOKIE,
        token,
        max_age=3600,
        secure=settings.public_base_url.startswith("https://"),
        httponly=True,
        samesite="strict",
        path="/api/contact",
    )
    return {"csrf_token": token, "site_key": settings.turnstile_site_key}


@fastapi_app.post("/api/contact/messages", status_code=202, include_in_schema=False)
async def create_contact_message(payload: ContactSubmission, request: Request):
    settings = _require_settings()
    _validate_origin(request, settings.allowed_origins)
    _validate_csrf(request, settings)
    try:
        message = await accept_contact(
            ContactInput(**payload.model_dump()),
            remote_ip=_request_ip(request),
            settings=settings,
        )
    except ContactValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail="Please wait before trying again") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail="Bot verification failed; try again") from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Unable to accept the message right now; please try again later",
        ) from exc
    return {"message": message}


@fastapi_app.get("/api/contact/verify", response_class=HTMLResponse, include_in_schema=False)
async def verify_contact_message(token: str = ""):
    settings = _require_settings()
    if not token or len(token) > 200:
        result = "invalid"
    else:
        result = await verify_and_deliver(token, settings)

    copy = {
        "delivered": (
            "Message verified and delivered",
            "Thank you. Your verified message has been sent successfully.",
        ),
        "delivery_failed": (
            "Address verified",
            "Delivery is temporarily delayed. You do not need to submit again.",
        ),
        "invalid": (
            "Link unavailable",
            "This verification link is invalid, expired, or has already been used.",
        ),
    }[result]
    return HTMLResponse(
        "<!doctype html><html><head><meta name='viewport' "
        "content='width=device-width,initial-scale=1'><title>Contact verification</title>"
        "<style>body{font:16px system-ui;margin:0;display:grid;place-items:center;"
        "min-height:100vh;background:#0f172a;color:#e2e8f0}.card{max-width:34rem;"
        "padding:2rem;margin:1rem;border:1px solid #334155;border-radius:1rem;"
        "background:#1e293b}a{color:#7dd3fc}</style></head><body><main class='card'>"
        f"<h1>{copy[0]}</h1><p>{copy[1]}</p><a href='/contact'>Return to contact</a>"
        "</main></body></html>"
    )
