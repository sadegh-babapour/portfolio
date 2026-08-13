from __future__ import annotations

import hmac
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import requests
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token as google_id_token
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.config import AuthSettings
from app.auth.models import (
    AuthEvent,
    AuthSession,
    ExternalIdentity,
    OidcLoginState,
    User,
    UserRole,
)
from app.auth.security import new_opaque_token, safe_return_path, token_digest
from app.contact.database import session_scope


log = logging.getLogger(__name__)
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_PROVIDER = "google"
SESSION_COOKIE = "portfolio_session"
CSRF_COOKIE = "portfolio_auth_csrf"
BROWSER_COOKIE = "portfolio_oidc_browser"


class AuthenticationError(RuntimeError):
    """Raised when an identity response cannot safely create a local session."""


@dataclass(frozen=True)
class LoginStart:
    authorization_url: str
    browser_token: str
    max_age: int


@dataclass(frozen=True)
class ConsumedLogin:
    nonce_digest: str
    return_path: str


@dataclass(frozen=True)
class IssuedSession:
    token: str
    csrf_token: str
    return_path: str
    max_age: int


@dataclass(frozen=True)
class SessionUser:
    user_id: uuid.UUID
    display_name: str
    email: str
    roles: frozenset[str]
    session_id: uuid.UUID
    csrf_digest: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def callback_url(settings: AuthSettings) -> str:
    return f"{settings.public_base_url}/api/auth/google/callback"


def _event(
    database: Session,
    event_type: str,
    *,
    user_id: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    database.add(
        AuthEvent(
            user_id=user_id,
            event_type=event_type,
            detail=detail or {},
        )
    )


def _cleanup(database: Session, settings: AuthSettings, now: datetime) -> None:
    database.execute(delete(OidcLoginState).where(OidcLoginState.expires_at < now))
    database.execute(delete(AuthSession).where(AuthSession.expires_at < now))
    cutoff = now - timedelta(days=settings.event_retention_days)
    database.execute(delete(AuthEvent).where(AuthEvent.created_at < cutoff))


def begin_google_login(settings: AuthSettings, return_to: str | None) -> LoginStart:
    now = utc_now()
    state = new_opaque_token()
    nonce = new_opaque_token()
    browser_token = new_opaque_token()
    expires_at = now + timedelta(minutes=settings.login_state_ttl_minutes)
    return_path = safe_return_path(return_to)

    with session_scope() as database:
        _cleanup(database, settings, now)
        database.add(
            OidcLoginState(
                state_digest=token_digest(state),
                nonce_digest=token_digest(nonce),
                browser_digest=token_digest(browser_token),
                return_path=return_path,
                expires_at=expires_at,
            )
        )
        _event(database, "login_started", detail={"provider": GOOGLE_PROVIDER})
        database.commit()

    parameters = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": callback_url(settings),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "prompt": "select_account",
        }
    )
    return LoginStart(
        authorization_url=f"{GOOGLE_AUTHORIZE_URL}?{parameters}",
        browser_token=browser_token,
        max_age=settings.login_state_ttl_minutes * 60,
    )


def consume_login_state(state: str, browser_token: str) -> ConsumedLogin:
    now = utc_now()
    with session_scope() as database:
        login_state = database.scalar(
            select(OidcLoginState)
            .where(OidcLoginState.state_digest == token_digest(state))
            .with_for_update()
        )
        if (
            login_state is None
            or login_state.consumed_at is not None
            or login_state.expires_at <= now
            or not hmac.compare_digest(
                login_state.browser_digest, token_digest(browser_token)
            )
        ):
            raise AuthenticationError("Login state is invalid or expired")

        login_state.consumed_at = now
        consumed = ConsumedLogin(
            nonce_digest=login_state.nonce_digest,
            return_path=safe_return_path(login_state.return_path),
        )
        database.commit()
        return consumed


def exchange_google_code(code: str, settings: AuthSettings) -> dict[str, Any]:
    response = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": callback_url(settings),
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("id_token"), str):
        raise AuthenticationError("Google did not return an ID token")
    return payload


def verify_google_identity(
    encoded_id_token: str,
    expected_nonce_digest: str,
    settings: AuthSettings,
) -> dict[str, Any]:
    claims = google_id_token.verify_oauth2_token(
        encoded_id_token,
        GoogleRequest(),
        audience=settings.google_client_id,
    )
    nonce = claims.get("nonce")
    if not isinstance(nonce, str) or not hmac.compare_digest(
        token_digest(nonce), expected_nonce_digest
    ):
        raise AuthenticationError("Google nonce validation failed")
    if claims.get("email_verified") is not True:
        raise AuthenticationError("Google email is not verified")
    for field in ("sub", "email"):
        if not isinstance(claims.get(field), str) or not claims[field].strip():
            raise AuthenticationError(f"Google identity is missing {field}")
    return claims


def _upsert_identity(
    database: Session,
    claims: dict[str, Any],
    settings: AuthSettings,
    now: datetime,
) -> User:
    subject = claims["sub"].strip()
    email = claims["email"].strip().lower()
    display_name = str(claims.get("name") or email.split("@", 1)[0])[:100]
    identity = database.scalar(
        select(ExternalIdentity)
        .where(
            ExternalIdentity.provider == GOOGLE_PROVIDER,
            ExternalIdentity.subject == subject,
        )
        .with_for_update()
    )
    if identity is None:
        user = User(
            display_name=display_name,
            primary_email=email,
            status="active",
            last_login_at=now,
        )
        database.add(user)
        database.flush()
        identity = ExternalIdentity(
            user_id=user.id,
            provider=GOOGLE_PROVIDER,
            subject=subject,
            email=email,
            email_verified=True,
            last_login_at=now,
        )
        database.add(identity)
    else:
        user = database.get(User, identity.user_id)
        if user is None:
            raise AuthenticationError("Local identity record is incomplete")
        if user.status != "active":
            _event(database, "login_denied", user_id=user.id, detail={"reason": "disabled"})
            database.commit()
            raise AuthenticationError("Account is not active")
        identity.email = email
        identity.email_verified = True
        identity.last_login_at = now
        user.display_name = display_name
        user.primary_email = email
        user.last_login_at = now

    registered = database.get(UserRole, (user.id, "registered"))
    if registered is None:
        database.add(UserRole(user_id=user.id, role="registered", source="google_login"))

    admin = database.get(UserRole, (user.id, "admin"))
    is_admin = settings.is_admin_identity(subject, email)
    if is_admin and admin is None:
        database.add(UserRole(user_id=user.id, role="admin", source="google_allowlist"))
    elif not is_admin and admin is not None and admin.source == "google_allowlist":
        database.delete(admin)
    return user


def issue_local_session(
    claims: dict[str, Any],
    return_path: str,
    settings: AuthSettings,
    previous_session_token: str | None = None,
) -> IssuedSession:
    now = utc_now()
    session_token = new_opaque_token()
    csrf_token = new_opaque_token()
    expires_at = now + timedelta(hours=settings.session_ttl_hours)

    with session_scope() as database:
        user = _upsert_identity(database, claims, settings, now)
        if previous_session_token:
            previous = database.scalar(
                select(AuthSession).where(
                    AuthSession.token_digest == token_digest(previous_session_token)
                )
            )
            if previous is not None and previous.revoked_at is None:
                previous.revoked_at = now
        database.add(
            AuthSession(
                user_id=user.id,
                token_digest=token_digest(session_token),
                csrf_digest=token_digest(csrf_token),
                expires_at=expires_at,
            )
        )
        _event(database, "login_succeeded", user_id=user.id, detail={"provider": GOOGLE_PROVIDER})
        database.commit()

    return IssuedSession(
        token=session_token,
        csrf_token=csrf_token,
        return_path=safe_return_path(return_path),
        max_age=settings.session_ttl_hours * 3600,
    )


def current_session(session_token: str | None) -> SessionUser | None:
    if not session_token:
        return None
    now = utc_now()
    with session_scope() as database:
        row = database.execute(
            select(AuthSession, User)
            .join(User, User.id == AuthSession.user_id)
            .where(AuthSession.token_digest == token_digest(session_token))
        ).one_or_none()
        if row is None:
            return None
        auth_session, user = row
        if (
            auth_session.revoked_at is not None
            or auth_session.expires_at <= now
            or user.status != "active"
        ):
            return None
        roles = frozenset(
            database.scalars(
                select(UserRole.role).where(UserRole.user_id == user.id)
            ).all()
        )
        return SessionUser(
            user_id=user.id,
            display_name=user.display_name,
            email=user.primary_email,
            roles=roles,
            session_id=auth_session.id,
            csrf_digest=auth_session.csrf_digest,
        )


def require_mutation_session(
    session_token: str | None,
    csrf_cookie: str | None,
    csrf_header: str | None,
) -> SessionUser:
    session_user = current_session(session_token)
    if (
        session_user is None
        or not csrf_cookie
        or not csrf_header
        or not hmac.compare_digest(csrf_cookie, csrf_header)
        or not hmac.compare_digest(token_digest(csrf_header), session_user.csrf_digest)
    ):
        raise AuthenticationError("Session or CSRF validation failed")
    return session_user


def revoke_session(session_user: SessionUser) -> None:
    with session_scope() as database:
        auth_session = database.get(AuthSession, session_user.session_id)
        if auth_session is not None and auth_session.revoked_at is None:
            auth_session.revoked_at = utc_now()
            _event(database, "logout", user_id=session_user.user_id)
            database.commit()


def delete_account(session_user: SessionUser) -> None:
    with session_scope() as database:
        user = database.get(User, session_user.user_id)
        if user is None:
            return
        _event(database, "account_deleted", user_id=user.id)
        database.flush()
        database.delete(user)
        database.commit()
