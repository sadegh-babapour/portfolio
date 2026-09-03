from __future__ import annotations

import logging
from urllib.parse import urlencode, urlsplit

from fastapi import HTTPException, Request
from pydantic import BaseModel
from fastapi.responses import RedirectResponse
from nicegui import app as fastapi_app

from app.auth.config import AuthSettings
from app.auth.service import (
    BROWSER_COOKIE,
    CSRF_COOKIE,
    SESSION_COOKIE,
    AuthenticationError,
    begin_google_login,
    consume_login_state,
    current_session,
    exchange_google_code,
    add_favorite_stop,
    issue_local_session,
    list_favorite_stop_ids,
    remove_favorite_stop,
    require_mutation_session,
    revoke_session,
    verify_google_identity,
)


log = logging.getLogger(__name__)


class FavoriteStopRequest(BaseModel):
    stop_id: str


def _settings() -> AuthSettings:
    settings = AuthSettings.from_env()
    if not settings.configured:
        log.warning("Authentication is missing configuration: %s", settings.missing())
        raise HTTPException(status_code=503, detail="Sign-in is temporarily unavailable")
    return settings


def _secure_cookie(settings: AuthSettings) -> bool:
    return settings.public_base_url.startswith("https://")


def _uses_public_host(request: Request, settings: AuthSettings) -> bool:
    supplied = urlsplit(str(request.url))
    expected = urlsplit(settings.public_base_url)
    return supplied.netloc == expected.netloc


def _canonical_login_url(settings: AuthSettings, return_to: str) -> str:
    query = urlencode({"return_to": return_to})
    return f"{settings.public_base_url}/api/auth/google/login?{query}"


def _validate_origin(request: Request, settings: AuthSettings) -> None:
    supplied = urlsplit(request.headers.get("origin", ""))
    expected = urlsplit(settings.public_base_url)
    if (supplied.scheme, supplied.netloc) != (expected.scheme, expected.netloc):
        raise HTTPException(status_code=403, detail="Request origin is not allowed")


def _clear_auth_cookies(response: RedirectResponse, settings: AuthSettings) -> None:
    secure = _secure_cookie(settings)
    response.delete_cookie(SESSION_COOKIE, path="/", secure=secure, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=secure, samesite="strict")


@fastapi_app.get("/api/auth/google/login", include_in_schema=False)
def google_login(request: Request, return_to: str = "/projects"):
    settings = _settings()
    if not _uses_public_host(request, settings):
        response = RedirectResponse(
            _canonical_login_url(settings, return_to),
            status_code=303,
        )
        response.headers["Cache-Control"] = "no-store"
        return response
    try:
        login = begin_google_login(settings, return_to)
    except Exception as exc:
        log.exception("Unable to begin Google authentication")
        raise HTTPException(status_code=503, detail="Sign-in is temporarily unavailable") from exc
    response = RedirectResponse(login.authorization_url, status_code=303)
    response.set_cookie(
        BROWSER_COOKIE,
        login.browser_token,
        max_age=login.max_age,
        secure=_secure_cookie(settings),
        httponly=True,
        samesite="lax",
        path="/api/auth/google",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@fastapi_app.get("/api/auth/google/callback", include_in_schema=False)
def google_callback(request: Request, state: str = "", code: str = "", error: str = ""):
    settings = _settings()
    browser_token = request.cookies.get(BROWSER_COOKIE, "")
    if not state or len(state) > 200 or not browser_token:
        return RedirectResponse("/projects?auth=failed", status_code=303)

    try:
        consumed = consume_login_state(state, browser_token)
        if error:
            return RedirectResponse("/projects?auth=cancelled", status_code=303)
        if not code or len(code) > 4096:
            raise AuthenticationError("Authorization code is missing")
        token_payload = exchange_google_code(code, settings)
        claims = verify_google_identity(
            token_payload["id_token"], consumed.nonce_digest, settings
        )
        issued = issue_local_session(
            claims,
            consumed.return_path,
            settings,
            previous_session_token=request.cookies.get(SESSION_COOKIE),
        )
    except Exception:
        log.exception("Google authentication callback failed")
        return RedirectResponse("/projects?auth=failed", status_code=303)

    response = RedirectResponse(issued.return_path, status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        issued.token,
        max_age=issued.max_age,
        secure=_secure_cookie(settings),
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        issued.csrf_token,
        max_age=issued.max_age,
        secure=_secure_cookie(settings),
        httponly=False,
        samesite="strict",
        path="/",
    )
    response.delete_cookie(
        BROWSER_COOKIE,
        path="/api/auth/google",
        secure=_secure_cookie(settings),
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@fastapi_app.get("/api/auth/session", include_in_schema=False)
def auth_session(request: Request):
    user = current_session(request.cookies.get(SESSION_COOKIE))
    if user is None:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "user": {
            "display_name": user.display_name,
            "email": user.email,
            "roles": sorted(user.roles),
        },
    }


def _authenticated_user(request: Request):
    user = current_session(request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise HTTPException(status_code=401, detail="Sign-in is required")
    return user


def _mutation_user(request: Request):
    settings = _settings()
    _validate_origin(request, settings)
    try:
        return require_mutation_session(
            request.cookies.get(SESSION_COOKIE),
            request.cookies.get(CSRF_COOKIE),
            request.headers.get("x-csrf-token"),
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=403, detail="Session expired; reload and try again"
        ) from exc


@fastapi_app.get("/api/auth/favorite-stops", include_in_schema=False)
def favorite_stops(request: Request):
    return {"stop_ids": list_favorite_stop_ids(_authenticated_user(request))}


@fastapi_app.post("/api/auth/favorite-stops", include_in_schema=False)
def save_favorite_stop(request: Request, payload: FavoriteStopRequest):
    try:
        stop_id = add_favorite_stop(_mutation_user(request), payload.stop_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"stop_id": stop_id, "saved": True}


@fastapi_app.delete("/api/auth/favorite-stops/{stop_id}", include_in_schema=False)
def delete_favorite_stop(request: Request, stop_id: str):
    try:
        removed = remove_favorite_stop(_mutation_user(request), stop_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"stop_id": removed, "saved": False}


@fastapi_app.post("/api/auth/logout", include_in_schema=False)
def logout(request: Request):
    settings = _settings()
    _validate_origin(request, settings)
    try:
        user = require_mutation_session(
            request.cookies.get(SESSION_COOKIE),
            request.cookies.get(CSRF_COOKIE),
            request.headers.get("x-csrf-token"),
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=403, detail="Session expired; reload and try again") from exc
    revoke_session(user)
    response = RedirectResponse("/", status_code=303)
    _clear_auth_cookies(response, settings)
    return response


@fastapi_app.delete("/api/auth/account", include_in_schema=False)
def remove_account(request: Request):
    settings = _settings()
    _validate_origin(request, settings)
    try:
        require_mutation_session(
            request.cookies.get(SESSION_COOKIE),
            request.cookies.get(CSRF_COOKIE),
            request.headers.get("x-csrf-token"),
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=403, detail="Session expired; reload and try again") from exc
    raise HTTPException(
        status_code=409,
        detail=(
            "Account deletion is handled through a verified request. "
            "Use /contact?topic=account-deletion; we respond within three business days."
        ),
    )
