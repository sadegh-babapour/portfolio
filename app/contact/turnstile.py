from __future__ import annotations

from dataclasses import dataclass

import requests


SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


@dataclass(frozen=True)
class TurnstileResult:
    success: bool
    error_codes: tuple[str, ...]


def verify_turnstile(
    *,
    secret: str,
    token: str,
    remote_ip: str,
    expected_hostnames: tuple[str, ...],
) -> TurnstileResult:
    try:
        response = requests.post(
            SITEVERIFY_URL,
            data={"secret": secret, "response": token, "remoteip": remote_ip},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return TurnstileResult(False, ("siteverify-unavailable",))

    errors = tuple(str(code) for code in payload.get("error-codes", []))
    valid = (
        payload.get("success") is True
        and str(payload.get("hostname", "")).lower() in expected_hostnames
        and payload.get("action") == "contact"
    )
    return TurnstileResult(valid, errors if not valid else ())
