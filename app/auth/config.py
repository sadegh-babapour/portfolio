from __future__ import annotations

import os
from dataclasses import dataclass

from app.contact.config import normalize_database_url


def _positive_int(value: str | None, default: int) -> int:
    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _csv(name: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in os.getenv(name, "").split(",")
        if item.strip()
    )


@dataclass(frozen=True)
class AuthSettings:
    database_url: str
    public_base_url: str
    google_client_id: str
    google_client_secret: str
    admin_google_subjects: tuple[str, ...]
    admin_emails: tuple[str, ...]
    session_ttl_hours: int
    login_state_ttl_minutes: int
    event_retention_days: int

    @classmethod
    def from_env(cls) -> AuthSettings:
        public_base_url = os.getenv(
            "AUTH_PUBLIC_BASE_URL",
            os.getenv("CONTACT_PUBLIC_BASE_URL", ""),
        ).rstrip("/")
        return cls(
            database_url=normalize_database_url(os.getenv("DATABASE_URL", "")),
            public_base_url=public_base_url,
            google_client_id=os.getenv("GOOGLE_OIDC_CLIENT_ID", ""),
            google_client_secret=os.getenv("GOOGLE_OIDC_CLIENT_SECRET", ""),
            admin_google_subjects=_csv("AUTH_ADMIN_GOOGLE_SUBJECTS"),
            admin_emails=tuple(
                email.lower() for email in _csv("AUTH_ADMIN_EMAILS")
            ),
            session_ttl_hours=_positive_int(
                os.getenv("AUTH_SESSION_TTL_HOURS"), 12
            ),
            login_state_ttl_minutes=_positive_int(
                os.getenv("AUTH_LOGIN_STATE_TTL_MINUTES"), 10
            ),
            event_retention_days=_positive_int(
                os.getenv("AUTH_EVENT_RETENTION_DAYS"), 90
            ),
        )

    def missing(self) -> tuple[str, ...]:
        values = {
            "DATABASE_URL": self.database_url,
            "AUTH_PUBLIC_BASE_URL": self.public_base_url,
            "GOOGLE_OIDC_CLIENT_ID": self.google_client_id,
            "GOOGLE_OIDC_CLIENT_SECRET": self.google_client_secret,
            "AUTH_SESSION_TTL_HOURS": self.session_ttl_hours,
            "AUTH_LOGIN_STATE_TTL_MINUTES": self.login_state_ttl_minutes,
            "AUTH_EVENT_RETENTION_DAYS": self.event_retention_days,
        }
        return tuple(name for name, value in values.items() if not value)

    @property
    def configured(self) -> bool:
        return not self.missing()

    def is_admin_identity(self, subject: str, email: str) -> bool:
        return subject in self.admin_google_subjects or email.lower() in self.admin_emails
