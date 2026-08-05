from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.contact.config import ContactSettings
from app.contact.database import session_scope
from app.contact.mail import deliver_contact_message, send_verification_email
from app.contact.models import ContactAttempt, ContactAuditEvent, ContactMessage
from app.contact.security import (
    clean_message,
    clean_text,
    keyed_digest,
    new_verification_token,
    normalize_email,
    validate_category,
    verification_digest,
)
from app.contact.turnstile import verify_turnstile


log = logging.getLogger(__name__)
GENERIC_ACCEPTED_MESSAGE = (
    "If the address is valid, a verification email will arrive shortly."
)


class RateLimitExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class ContactInput:
    name: str
    email: str
    subject: str
    category: str
    message: str
    website: str
    turnstile_token: str


@dataclass(frozen=True)
class CleanContact:
    name: str
    email: str
    subject: str
    category: str
    message: str


def validate_contact(value: ContactInput) -> CleanContact:
    return CleanContact(
        name=clean_text(value.name, "Name", 2, 100),
        email=normalize_email(value.email),
        subject=clean_text(value.subject, "Subject", 3, 120),
        category=validate_category(value.category),
        message=clean_message(value.message),
    )


def _advisory_key(digest: str) -> int:
    value = int(digest[:16], 16)
    return value - 2**64 if value >= 2**63 else value


def _enforce_rate_limit(session, ip_hash: str, email_hash: str, now: datetime) -> None:
    session.execute(select(func.pg_advisory_xact_lock(_advisory_key(ip_hash))))
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(days=1)
    ip_hour = session.scalar(
        select(func.count()).select_from(ContactAttempt).where(
            ContactAttempt.ip_hash == ip_hash,
            ContactAttempt.created_at >= hour_ago,
        )
    )
    email_day = session.scalar(
        select(func.count()).select_from(ContactAttempt).where(
            ContactAttempt.email_hash == email_hash,
            ContactAttempt.created_at >= day_ago,
        )
    )
    if (ip_hour or 0) >= 5 or (email_day or 0) >= 3:
        raise RateLimitExceeded


async def accept_contact(
    value: ContactInput,
    *,
    remote_ip: str,
    settings: ContactSettings,
) -> str:
    if value.website.strip():
        return GENERIC_ACCEPTED_MESSAGE

    clean = validate_contact(value)
    ip_hash = keyed_digest(remote_ip, settings.ip_hash_key)
    email_hash = keyed_digest(clean.email, settings.ip_hash_key)
    now = datetime.now(timezone.utc)

    with session_scope() as session:
        try:
            _enforce_rate_limit(session, ip_hash, email_hash, now)
        except RateLimitExceeded:
            session.rollback()
            raise
        attempt = ContactAttempt(
            ip_hash=ip_hash,
            email_hash=email_hash,
            outcome="started",
        )
        session.add(attempt)
        session.commit()
        attempt_id = attempt.id

    turnstile = await asyncio.to_thread(
        verify_turnstile,
        secret=settings.turnstile_secret_key,
        token=value.turnstile_token,
        remote_ip=remote_ip,
        expected_hostnames=settings.turnstile_expected_hostnames,
    )
    if not turnstile.success:
        with session_scope() as session:
            attempt = session.get(ContactAttempt, attempt_id)
            if attempt:
                attempt.outcome = "turnstile_rejected"
            session.commit()
        log.warning("Turnstile rejected contact submission: %s", turnstile.error_codes)
        raise PermissionError("Bot verification failed")

    raw_token = new_verification_token()
    digest = verification_digest(raw_token, settings.token_pepper)
    message = ContactMessage(
        name=clean.name,
        email=clean.email,
        subject=clean.subject,
        category=clean.category,
        body=clean.message,
        status="pending_verification",
        verification_digest=digest,
        verification_expires_at=now + timedelta(minutes=30),
    )
    with session_scope() as session:
        session.add(message)
        session.flush()
        attempt = session.get(ContactAttempt, attempt_id)
        if attempt:
            attempt.outcome = "accepted"
        session.add(
            ContactAuditEvent(message_id=message.id, event_type="contact.accepted", detail={})
        )
        session.commit()

    verification_url = f"{settings.public_base_url}/api/contact/verify?token={raw_token}"
    try:
        await asyncio.to_thread(
            send_verification_email,
            settings,
            clean.email,
            clean.name,
            verification_url,
        )
    except Exception:
        log.exception("Unable to send contact verification email")
        with session_scope() as session:
            stored = session.get(ContactMessage, message.id)
            if stored:
                stored.status = "verification_delivery_failed"
                session.add(
                    ContactAuditEvent(
                        message_id=stored.id,
                        event_type="contact.verification_delivery_failed",
                        detail={},
                    )
                )
                session.commit()
        raise
    return GENERIC_ACCEPTED_MESSAGE


async def verify_and_deliver(raw_token: str, settings: ContactSettings) -> str:
    digest = verification_digest(raw_token, settings.token_pepper)
    now = datetime.now(timezone.utc)
    with session_scope() as session:
        message = session.scalar(
            select(ContactMessage)
            .where(ContactMessage.verification_digest == digest)
            .with_for_update()
        )
        if not message or message.verified_at or message.verification_expires_at < now:
            return "invalid"
        message.verified_at = now
        message.status = "verified"
        session.add(
            ContactAuditEvent(message_id=message.id, event_type="contact.verified", detail={})
        )
        session.commit()

    try:
        await asyncio.to_thread(
            deliver_contact_message,
            settings,
            name=message.name,
            verified_email=message.email,
            category=message.category,
            subject=message.subject,
            body=message.body,
        )
    except Exception:
        log.exception("Unable to deliver verified contact message")
        with session_scope() as session:
            stored = session.get(ContactMessage, message.id)
            if stored:
                stored.status = "delivery_failed"
                session.add(
                    ContactAuditEvent(
                        message_id=stored.id,
                        event_type="contact.delivery_failed",
                        detail={},
                    )
                )
                session.commit()
        return "delivery_failed"

    with session_scope() as session:
        stored = session.get(ContactMessage, message.id)
        if stored:
            stored.status = "delivered"
            stored.delivered_at = datetime.now(timezone.utc)
            session.add(
                ContactAuditEvent(message_id=stored.id, event_type="contact.delivered", detail={})
            )
            session.commit()
    return "delivered"
