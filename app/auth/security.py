"""Small security helpers shared by sign-in and sessions.

The pattern used everywhere in app/auth: hand the browser a random token, store only
its SHA-256 digest. A copy of the database then can't be turned back into a working
cookie (see docs/lessons/07).
"""
from __future__ import annotations

import hashlib
import secrets
from urllib.parse import urlsplit


def new_opaque_token() -> str:
    # 32 random bytes, URL-safe text: unguessable and safe in cookies and query strings.
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def safe_return_path(value: str | None, default: str = "/projects") -> str:
    """Only same-site paths such as /resume; anything else falls back to the default.

    Stops an "open redirect": a link like ?return_to=https://evil.example would otherwise
    send a freshly signed-in user to someone else's site.
    """
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
