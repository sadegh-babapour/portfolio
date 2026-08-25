from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_ANALYTICS_RETENTION_DAYS = 90
MAX_ANALYTICS_RETENTION_DAYS = 365


@dataclass(frozen=True)
class AnalyticsSettings:
    retention_days: int

    @classmethod
    def from_env(cls) -> "AnalyticsSettings":
        raw_value = os.getenv(
            "ANALYTICS_RETENTION_DAYS", str(DEFAULT_ANALYTICS_RETENTION_DAYS)
        )
        try:
            retention_days = int(raw_value)
        except ValueError:
            retention_days = DEFAULT_ANALYTICS_RETENTION_DAYS
        if not 1 <= retention_days <= MAX_ANALYTICS_RETENTION_DAYS:
            retention_days = DEFAULT_ANALYTICS_RETENTION_DAYS
        return cls(retention_days=retention_days)
