from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from sqlalchemy import text

from app.contact.database import session_scope


log = logging.getLogger(__name__)
SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / "dashboard_cache.json"
EXPECTED_SNAPSHOT_TABLES = (
    "daily_stats",
    "membership_summary",
    "revenue_summary",
    "member_visits",
)
LIVE_ANALYSIS_CACHE_SECONDS = 30
_LIVE_CACHE_LOCK = threading.Lock()
_LIVE_CACHE_VALUE: dict[str, Any] | None = None
_LIVE_CACHE_EXPIRES_AT = 0.0


def load_cached_analysis(path: Path = SNAPSHOT_PATH) -> dict[str, Any]:
    """Load and summarize the committed, non-sensitive demonstration snapshot."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.exception("Unable to load the dashboard snapshot")
        return {"available": False, "tables": {}, "quality": []}

    raw_tables = document.get("data")
    if not isinstance(raw_tables, dict):
        return {"available": False, "tables": {}, "quality": []}

    tables = {
        name: rows if isinstance((rows := raw_tables.get(name)), list) else []
        for name in EXPECTED_SNAPSHOT_TABLES
    }
    quality = [
        {
            "table": name,
            "rows": len(rows),
            "status": "pass" if rows else "empty",
        }
        for name, rows in tables.items()
    ]
    return {
        "available": all(item["status"] == "pass" for item in quality),
        "cache_date": document.get("cache_date"),
        "last_updated": document.get("last_updated"),
        "tables": tables,
        "quality": quality,
        "row_count": sum(item["rows"] for item in quality),
    }


def build_live_transit_analysis() -> dict[str, Any]:
    """Return bounded aggregate transit quality metrics; never expose vehicle IDs."""
    global _LIVE_CACHE_EXPIRES_AT, _LIVE_CACHE_VALUE

    now = time.monotonic()
    with _LIVE_CACHE_LOCK:
        if _LIVE_CACHE_VALUE is not None and now < _LIVE_CACHE_EXPIRES_AT:
            return _LIVE_CACHE_VALUE
        result = _query_live_transit_analysis()
        _LIVE_CACHE_VALUE = result
        _LIVE_CACHE_EXPIRES_AT = now + LIVE_ANALYSIS_CACHE_SECONDS
        return result


def _query_live_transit_analysis() -> dict[str, Any]:
    try:
        with session_scope() as database:
            database.execute(text("set local statement_timeout = '2000ms'"))
            overview = database.execute(
                text(
                    """
                    select
                      now() as generated_at,
                      count(*) filter (
                        where vehicle_timestamp >= now() - interval '3 minutes'
                      )::integer as recent_vehicles,
                      count(distinct route_short_name) filter (
                        where vehicle_timestamp >= now() - interval '3 minutes'
                      )::integer as active_routes,
                      count(*) filter (
                        where vehicle_timestamp >= now() - interval '3 minutes'
                          and route_short_name is not null
                      )::integer as route_matched_vehicles,
                      max(vehicle_timestamp) as latest_vehicle_timestamp,
                      (select max(feed_header_timestamp) from transit.trip_updates_current)
                        as latest_trip_update_timestamp,
                      (select max(feed_header_timestamp) from transit.alerts_current)
                        as latest_alert_timestamp,
                      (select count(*)::integer from transit.vehicle_positions_raw
                        where vehicle_timestamp >= now() - interval '15 minutes')
                        as retained_observations
                    from transit.v_vehicle_dashboard
                    """
                )
            ).mappings().one()
            route_modes = [
                {"mode": mode or "unclassified", "vehicles": int(count)}
                for mode, count in database.execute(
                    text(
                        """
                        select coalesce(route_mode, 'unclassified') as route_mode,
                               count(*)::integer as vehicles
                        from transit.v_vehicle_dashboard
                        where vehicle_timestamp >= now() - interval '3 minutes'
                        group by coalesce(route_mode, 'unclassified')
                        order by vehicles desc, route_mode
                        """
                    )
                ).all()
            ]
            top_routes = [
                {"route": route, "vehicles": int(count)}
                for route, count in database.execute(
                    text(
                        """
                        select route_short_name, count(*)::integer as vehicles
                        from transit.v_vehicle_dashboard
                        where vehicle_timestamp >= now() - interval '3 minutes'
                          and route_short_name is not null
                        group by route_short_name
                        order by vehicles desc, route_short_name
                        limit 10
                        """
                    )
                ).all()
            ]
            observation_cadence = [
                {
                    "minute": minute.isoformat(),
                    "observations": int(observations),
                    "vehicles": int(vehicles),
                }
                for minute, observations, vehicles in database.execute(
                    text(
                        """
                        select date_trunc('minute', vehicle_timestamp) as minute,
                               count(*)::integer as observations,
                               count(distinct vehicle_id)::integer as vehicles
                        from transit.vehicle_positions_raw
                        where vehicle_timestamp >= now() - interval '15 minutes'
                        group by date_trunc('minute', vehicle_timestamp)
                        order by minute
                        """
                    )
                ).all()
            ]
    except Exception:
        log.exception("Unable to build the public transit analysis")
        return {"available": False}

    recent = int(overview["recent_vehicles"] or 0)
    matched = int(overview["route_matched_vehicles"] or 0)
    return {
        "available": True,
        "generated_at": overview["generated_at"],
        "recent_vehicles": recent,
        "active_routes": int(overview["active_routes"] or 0),
        "route_match_percent": round((matched / recent) * 100, 1) if recent else None,
        "retained_observations": int(overview["retained_observations"] or 0),
        "latest_vehicle_timestamp": overview["latest_vehicle_timestamp"],
        "latest_trip_update_timestamp": overview["latest_trip_update_timestamp"],
        "latest_alert_timestamp": overview["latest_alert_timestamp"],
        "route_modes": route_modes,
        "top_routes": top_routes,
        "observation_cadence": observation_cadence,
    }
