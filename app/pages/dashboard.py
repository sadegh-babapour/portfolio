"""/dashboard: live transit numbers from app/dashboard/service.py, drawn with ECharts.
Only aggregates are shown, never vehicle IDs.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from nicegui import ui

from app.components.charts import (
    AXIS,
    LEGEND,
    MUTED,
    TOOLTIP,
    enable_viewport_chart_animations,
    viewport_chart,
)
from app.components.navbar import with_layout
from app.dashboard.service import build_live_transit_analysis


CALGARY = ZoneInfo("America/Edmonton")


def _calgary_time(value: datetime | str | None) -> str:
    """19:03 in Calgary time; the database returns UTC."""
    if value is None:
        return "none yet"
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.astimezone(CALGARY).strftime("%H:%M")


def _mode_label(mode: str) -> str:
    return mode.upper() if len(mode) <= 3 else mode.replace("_", " ").capitalize()


def _metric(title: str, value: object, note: str) -> None:
    with ui.card().classes("w-full h-full p-4 sm:p-5 gap-1 sm:gap-2"):
        ui.label(title).classes("text-sm text-grey-7")
        ui.label(str(value)).classes("text-2xl sm:text-3xl font-semibold")
        ui.label(note).classes("text-xs text-grey-7")


def _chart_card(title: str, summary: str, options: dict) -> None:
    with ui.card().classes("w-full min-w-0 p-4 sm:p-5 gap-3"):
        ui.label(title).classes("text-xl font-semibold")
        viewport_chart(options, classes="w-full h-64 sm:h-80", aria_label=title)
        ui.label(summary).classes("text-sm text-grey-7 leading-relaxed")


def _live_dashboard(live: dict) -> None:
    if not live.get("available"):
        with ui.card().classes("w-full p-5"):
            ui.label("Live numbers are unavailable right now.").classes("text-negative")
        return

    route_match = live["route_match_percent"]
    with ui.element("section").classes(
        "grid w-full grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4"
    ):
        _metric("Buses reporting", live["recent_vehicles"], "last 3 minutes")
        _metric("Active routes", live["active_routes"], "with a bus reporting")
        _metric(
            "Matched to a route",
            f"{route_match:.1f}%" if route_match is not None else "N/A",
            "joined to the schedule",
        )
        _metric(
            "Positions stored",
            f"{live['retained_observations']:,}",
            "last 15 minutes",
        )

    cadence = live["observation_cadence"]
    routes = live["top_routes"]
    modes = live["route_modes"]
    if modes:
        with ui.card().classes("w-full p-4 sm:p-5 gap-2"):
            ui.label("Buses by service type").classes("text-xl font-semibold")
            viewport_chart(
                {
                    "tooltip": {"trigger": "item", **TOOLTIP},
                    "legend": {"bottom": 0, "left": 0, **LEGEND},
                    "grid": {"left": 0, "right": 0, "top": 4, "bottom": 30},
                    "xAxis": {"type": "value", "show": False, "max": "dataMax"},
                    "yAxis": {"type": "category", "show": False, "data": ["Buses"]},
                    "series": [
                        {
                            "name": f"{_mode_label(row['mode'])} · {row['vehicles']}",
                            "type": "bar",
                            "stack": "modes",
                            "barWidth": 22,
                            "data": [row["vehicles"]],
                        }
                        for row in modes
                    ],
                },
                classes="w-full h-20",
                aria_label="Buses by service type",
            )

    with ui.element("section").classes("grid w-full grid-cols-1 gap-5 lg:grid-cols-2"):
        if cadence:
            labels = [_calgary_time(row["minute"]) for row in cadence]
            _chart_card(
                "Positions per minute",
                f"{sum(row['observations'] for row in cadence):,} positions in "
                f"{len(cadence)} minutes, Calgary time.",
                {
                    "tooltip": {"trigger": "axis", **TOOLTIP},
                    "legend": {"data": ["Positions", "Buses"], "bottom": 0, **LEGEND},
                    "grid": {"left": 45, "right": 18, "top": 24, "bottom": 58},
                    "xAxis": {"type": "category", "data": labels, **AXIS},
                    "yAxis": {"type": "value", "minInterval": 1, **AXIS},
                    "series": [
                        {
                            "name": "Positions",
                            "type": "line",
                            "smooth": True,
                            "symbol": "none",
                            "areaStyle": {"opacity": 0.12},
                            "data": [row["observations"] for row in cadence],
                        },
                        {
                            "name": "Buses",
                            "type": "line",
                            "smooth": True,
                            "symbol": "none",
                            "data": [row["vehicles"] for row in cadence],
                        },
                    ],
                },
            )
        else:
            with ui.card().classes("w-full p-5"):
                ui.label("Positions per minute").classes("text-xl font-semibold")
                ui.label("Nothing is collected outside 08:00–21:00.").classes(
                    "text-sm text-grey-7"
                )

        if routes:
            _chart_card(
                "Busiest routes",
                "Top ten routes by buses reporting.",
                {
                    "tooltip": {"trigger": "axis", **TOOLTIP},
                    "grid": {"left": 45, "right": 18, "top": 24, "bottom": 48},
                    "xAxis": {
                        "type": "category",
                        "data": [row["route"] for row in routes],
                        **AXIS,
                        "axisLabel": {"color": MUTED, "interval": 0, "hideOverlap": False},
                    },
                    "yAxis": {"type": "value", "minInterval": 1, **AXIS},
                    "series": [
                        {
                            "name": "Buses",
                            "type": "bar",
                            "barMaxWidth": 34,
                            "data": [row["vehicles"] for row in routes],
                            "itemStyle": {"borderRadius": [6, 6, 0, 0]},
                        }
                    ],
                },
            )
        else:
            with ui.card().classes("w-full p-5"):
                ui.label("Busiest routes").classes("text-xl font-semibold")
                ui.label("No buses reporting right now.").classes(
                    "text-sm text-grey-7"
                )

    with ui.card().classes("w-full p-4 sm:p-5 gap-2"):
        ui.label("Freshness").classes("text-xl font-semibold")
        ui.label(
            f"Page built {_calgary_time(live['generated_at'])} · "
            f"positions {_calgary_time(live['latest_vehicle_timestamp'])} · "
            f"trip updates {_calgary_time(live['latest_trip_update_timestamp'])} · "
            f"alerts {_calgary_time(live['latest_alert_timestamp'])} (Calgary time)"
        ).classes("text-sm")
        ui.label(
            "Source: City of Calgary GTFS and GTFS-Realtime, collected 08:00–21:00."
        ).classes("text-sm text-grey-7")


@ui.page("/dashboard")
@with_layout
def dashboard_page():
    ui.page_title("Live transit dashboard — Bizqlab")
    live = build_live_transit_analysis()

    with ui.column().classes("w-full max-w-7xl mx-auto px-4 py-8 sm:px-8 gap-7"):
        with ui.column().classes("gap-3 max-w-4xl"):
            ui.label("Live transit dashboard").classes("text-4xl sm:text-5xl font-bold")
            ui.label(
                "Calgary Transit pipeline numbers, recalculated every 30 seconds."
            ).classes("text-lg text-grey-7 leading-relaxed")
            ui.link(
                "How the pipeline works",
                "/projects#project-calgary-transit-live",
            ).classes("text-primary font-semibold no-underline hover:underline")

        _live_dashboard(live)
        enable_viewport_chart_animations()
