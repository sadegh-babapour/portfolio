from __future__ import annotations

import os
from dataclasses import dataclass


def normalize_database_url(value: str) -> str:
    if value.startswith("postgres://"):
        return "postgresql+psycopg2://" + value.removeprefix("postgres://")
    if value.startswith("postgresql://"):
        return "postgresql+psycopg2://" + value.removeprefix("postgresql://")
    return value


@dataclass(frozen=True)
class ContactSettings:
    database_url: str
    public_base_url: str
    allowed_origins: tuple[str, ...]
    token_pepper: str
    ip_hash_key: str
    turnstile_site_key: str
    turnstile_secret_key: str
    turnstile_expected_hostnames: tuple[str, ...]
    from_email: str
    to_email: str
    resend_api_key: str

    @classmethod
    def from_env(cls) -> ContactSettings:
        public_base_url = os.getenv("CONTACT_PUBLIC_BASE_URL", "").rstrip("/")
        origin_value = os.getenv("CONTACT_ALLOWED_ORIGINS", public_base_url)
        return cls(
            database_url=normalize_database_url(os.getenv("DATABASE_URL", "")),
            public_base_url=public_base_url,
            allowed_origins=tuple(
                origin.strip().rstrip("/")
                for origin in origin_value.split(",")
                if origin.strip()
            ),
            token_pepper=os.getenv("CONTACT_TOKEN_PEPPER", ""),
            ip_hash_key=os.getenv("CONTACT_IP_HASH_KEY", ""),
            turnstile_site_key=os.getenv("TURNSTILE_SITE_KEY", ""),
            turnstile_secret_key=os.getenv("TURNSTILE_SECRET_KEY", ""),
            turnstile_expected_hostnames=tuple(
                hostname.strip().lower()
                for hostname in os.getenv("TURNSTILE_EXPECTED_HOSTNAMES", "").split(",")
                if hostname.strip()
            ),
            from_email=os.getenv("CONTACT_FROM_EMAIL", ""),
            to_email=os.getenv("CONTACT_TO_EMAIL", ""),
            resend_api_key=os.getenv("RESEND_API_KEY", ""),
        )

    def missing(self) -> tuple[str, ...]:
        values = {
            "DATABASE_URL": self.database_url,
            "CONTACT_PUBLIC_BASE_URL": self.public_base_url,
            "CONTACT_ALLOWED_ORIGINS": self.allowed_origins,
            "CONTACT_TOKEN_PEPPER": self.token_pepper,
            "CONTACT_IP_HASH_KEY": self.ip_hash_key,
            "TURNSTILE_SITE_KEY": self.turnstile_site_key,
            "TURNSTILE_SECRET_KEY": self.turnstile_secret_key,
            "TURNSTILE_EXPECTED_HOSTNAMES": self.turnstile_expected_hostnames,
            "CONTACT_FROM_EMAIL": self.from_email,
            "CONTACT_TO_EMAIL": self.to_email,
            "RESEND_API_KEY": self.resend_api_key,
        }
        missing = [name for name, value in values.items() if not value]
        if self.token_pepper and len(self.token_pepper) < 32:
            missing.append("CONTACT_TOKEN_PEPPER (minimum 32 characters)")
        if self.ip_hash_key and len(self.ip_hash_key) < 32:
            missing.append("CONTACT_IP_HASH_KEY (minimum 32 characters)")
        if self.public_base_url.startswith("https://") and self.turnstile_site_key.startswith(
            ("1x000000", "2x000000", "3x000000")
        ):
            missing.append("TURNSTILE_SITE_KEY (test key forbidden in production)")
        return tuple(missing)

    @property
    def configured(self) -> bool:
        return not self.missing()
