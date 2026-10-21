from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, func, select, text

from app.admin.config import AnalyticsSettings
from app.admin.models import PageViewEvent
from app.auth.models import AuthEvent, AuthSession, User
from app.auth.service import SessionUser, current_session
from app.contact.database import session_scope
from app.contact.models import ContactMessage


log = logging.getLogger(__name__)

TRACKED_PAGE_PATHS = frozenset(
    {
        "/",
        "/about",
        "/resume",
        "/projects",
        "/contact",
        "/dashboard",
        "/blog",
        "/account",
        "/privacy",
        "/terms",
        "/calgary-transit-live/",
    }
)


def tracked_page_path(path: str) -> str | None:
    """Return a stable route label only for deliberately tracked HTML entry points."""
    return path if path in TRACKED_PAGE_PATHS else None


def record_page_view(path: str) -> None:
    normalized = tracked_page_path(path)
    if normalized is None:
        return
    settings = AnalyticsSettings.from_env()
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.retention_days)
    with session_scope() as database:
        database.add(PageViewEvent(path=normalized))
        database.execute(delete(PageViewEvent).where(PageViewEvent.created_at < cutoff))
        database.commit()


def require_admin(session_token: str | None) -> SessionUser:
    user = current_session(session_token)
    if user is None or "admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Administrator access is required")
    return user


def classify_transit_health(
    within_operating_hours: bool,
    vehicle_age_seconds: float | None,
    recent_vehicle_count: int,
) -> str:
    if not within_operating_hours:
        return "outside_operating_hours"
    if (
        vehicle_age_seconds is not None
        and vehicle_age_seconds <= 180
        and recent_vehicle_count > 0
    ):
        return "healthy"
    return "degraded"


def _transit_health(database) -> dict[str, Any]:
    try:
        row = database.execute(
            text(
                """
                select
                  now() as checked_at,
                  extract(hour from now() at time zone 'America/Edmonton') >= 8
                    and extract(hour from now() at time zone 'America/Edmonton') < 21
                    as within_operating_hours,
                  max(vehicle_timestamp) as latest_vehicle_timestamp,
                  extract(epoch from (now() - max(vehicle_timestamp))) as vehicle_age_seconds,
                  count(*) filter (
                    where vehicle_timestamp >= now() - interval '3 minutes'
                  ) as recent_vehicle_count,
                  (select max(feed_header_timestamp) from transit.trip_updates_current)
                    as latest_trip_update_timestamp,
                  (select max(feed_header_timestamp) from transit.alerts_current)
                    as latest_alert_timestamp
                from transit.vehicle_positions_current
                """
            )
        ).mappings().one()
    except Exception:
        log.exception("Unable to read transit freshness for the admin summary")
        return {"status": "unavailable"}

    age = float(row["vehicle_age_seconds"]) if row["vehicle_age_seconds"] is not None else None
    recent_count = int(row["recent_vehicle_count"] or 0)
    within_hours = row["within_operating_hours"] is True
    return {
        "status": classify_transit_health(within_hours, age, recent_count),
        "checked_at": row["checked_at"],
        "within_operating_hours": within_hours,
        "latest_vehicle_timestamp": row["latest_vehicle_timestamp"],
        "vehicle_age_seconds": age,
        "recent_vehicle_count": recent_count,
        "latest_trip_update_timestamp": row["latest_trip_update_timestamp"],
        "latest_alert_timestamp": row["latest_alert_timestamp"],
    }


def build_admin_summary() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    two_weeks_ago = now - timedelta(days=13)

    with session_scope() as database:
        traffic = {
            "today": database.scalar(
                select(func.count(PageViewEvent.id)).where(PageViewEvent.created_at >= day_ago)
            ) or 0,
            "seven_days": database.scalar(
                select(func.count(PageViewEvent.id)).where(PageViewEvent.created_at >= week_ago)
            ) or 0,
            "thirty_days": database.scalar(
                select(func.count(PageViewEvent.id)).where(PageViewEvent.created_at >= month_ago)
            ) or 0,
        }
        top_paths = [
            {"path": path, "views": count}
            for path, count in database.execute(
                select(PageViewEvent.path, func.count(PageViewEvent.id).label("views"))
                .where(PageViewEvent.created_at >= month_ago)
                .group_by(PageViewEvent.path)
                .order_by(text("views desc"), PageViewEvent.path)
                .limit(10)
            ).all()
        ]
        daily_views = [
            {"day": day.isoformat(), "views": count}
            for day, count in database.execute(
                select(func.date(PageViewEvent.created_at), func.count(PageViewEvent.id))
                .where(PageViewEvent.created_at >= two_weeks_ago)
                .group_by(func.date(PageViewEvent.created_at))
                .order_by(func.date(PageViewEvent.created_at))
            ).all()
        ]

        identity = {
            "users": database.scalar(select(func.count(User.id))) or 0,
            "active_users": database.scalar(
                select(func.count(User.id)).where(User.status == "active")
            ) or 0,
            "active_sessions": database.scalar(
                select(func.count(AuthSession.id)).where(
                    AuthSession.expires_at > now,
                    AuthSession.revoked_at.is_(None),
                )
            ) or 0,
            "successful_logins_24h": database.scalar(
                select(func.count(AuthEvent.id)).where(
                    AuthEvent.event_type == "login_succeeded",
                    AuthEvent.created_at >= day_ago,
                )
            ) or 0,
            "successful_logins_7d": database.scalar(
                select(func.count(AuthEvent.id)).where(
                    AuthEvent.event_type == "login_succeeded",
                    AuthEvent.created_at >= week_ago,
                )
            ) or 0,
        }
        contact_statuses = {
            status: count
            for status, count in database.execute(
                select(ContactMessage.status, func.count(ContactMessage.id))
                .group_by(ContactMessage.status)
                .order_by(ContactMessage.status)
            ).all()
        }
        contacts_30d = database.scalar(
            select(func.count(ContactMessage.id)).where(ContactMessage.created_at >= month_ago)
        ) or 0
        transit = _transit_health(database)

    return {
        "generated_at": now,
        "traffic": traffic,
        "top_paths": top_paths,
        "daily_views": daily_views,
        "identity": identity,
        "contact": {"thirty_days": contacts_30d, "statuses": contact_statuses},
        "transit": transit,
        "analytics_retention_days": AnalyticsSettings.from_env().retention_days,
    }
