from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ALLOWED_CATEGORIES = {"job-opportunity", "project", "networking", "other"}


class ContactValidationError(ValueError):
    pass


def clean_text(value: str, field: str, minimum: int, maximum: int) -> str:
    normalized = " ".join(value.split())
    if not minimum <= len(normalized) <= maximum:
        raise ContactValidationError(f"{field} must be {minimum}–{maximum} characters")
    return normalized


def clean_message(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not 20 <= len(normalized) <= 5000:
        raise ContactValidationError("Message must be 20–5000 characters")
    return normalized


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        raise ContactValidationError("Enter a valid email address")
    return email


def validate_category(value: str) -> str:
    if value not in ALLOWED_CATEGORIES:
        raise ContactValidationError("Choose a valid topic")
    return value


def keyed_digest(value: str, key: str) -> str:
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()


def verification_digest(token: str, pepper: str) -> str:
    return keyed_digest(token, pepper)


def new_verification_token() -> str:
    return secrets.token_urlsafe(32)


def new_csrf_token(secret: str, now: int | None = None) -> str:
    timestamp = now or int(time.time())
    nonce = secrets.token_urlsafe(24)
    payload = f"{timestamp}.{nonce}"
    signature = keyed_digest(payload, secret)
    return f"{payload}.{signature}"


def verify_csrf_token(token: str, secret: str, max_age_seconds: int = 3600) -> bool:
    try:
        timestamp_text, nonce, signature = token.split(".", 2)
        timestamp = int(timestamp_text)
    except (TypeError, ValueError):
        return False
    if not nonce or timestamp > int(time.time()) + 30:
        return False
    if int(time.time()) - timestamp > max_age_seconds:
        return False
    expected = keyed_digest(f"{timestamp}.{nonce}", secret)
    return hmac.compare_digest(signature, expected)
