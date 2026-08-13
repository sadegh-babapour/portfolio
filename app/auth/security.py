from __future__ import annotations

import hashlib
import secrets
from urllib.parse import urlsplit


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def safe_return_path(value: str | None, default: str = "/projects") -> str:
    if not value:
        return default
    if "\r" in value or "\n" in value:
        return default
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return default
    if parsed.path.startswith("//") or "\\" in value:
        return default
    return value
