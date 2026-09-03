from __future__ import annotations

from nicegui import ui

from app.components.charts import enable_viewport_chart_animations, viewport_chart
from app.components.navbar import with_layout
from app.dashboard.service import build_live_transit_analysis, load_cached_analysis


def _metric(title: str, value: object, note: str) -> None:
    with ui.card().classes("w-full h-full p-5 gap-2"):
        ui.label(title).classes("text-sm text-grey-7")
        ui.label(str(value)).classes("text-3xl font-semibold")
        ui.label(note).classes("text-xs text-grey-7")


def _chart_card(title: str, summary: str, options: dict) -> None:
    with ui.card().classes("w-full min-w-0 p-4 sm:p-5 gap-3"):
        ui.label(title).classes("text-xl font-semibold")
        viewport_chart(options, classes="w-full h-80", aria_label=title)
        ui.label(summary).classes("text-sm text-grey-7 leading-relaxed")


def _live_dashboard(live: dict) -> None:
    ui.label("Live PostgreSQL analysis").classes("text-2xl font-semibold")
    ui.label(
        "Aggregates are calculated when this page renders from the same transit "
        "tables that power the Calgary map. No vehicle identifiers are exposed."
    ).classes("text-base text-grey-7 leading-relaxed")
    ui.link(
        "See the Calgary Transit pipeline case study",
        "/projects#project-calgary-transit-live",
    ).classes("text-primary font-semibold no-underline hover:underline")

    if not live.get("available"):
        with ui.card().classes("w-full p-5"):
            ui.label("Live analysis is temporarily unavailable.").classes("text-negative")
            ui.label(
                "The cached analytical case study below remains available."
            ).classes("text-sm text-grey-7")
        return

    route_match = live["route_match_percent"]
    with ui.element("section").classes(
        "grid w-full grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
    ):
        _metric("Recent vehicles", live["recent_vehicles"], "latest 3 minutes")
        _metric("Active routes", live["active_routes"], "route IDs with fresh vehicles")
        _metric(
            "Route enrichment",
            f"{route_match:.1f}%" if route_match is not None else "N/A",
            "fresh vehicles matched to static GTFS",
        )
        _metric(
            "Retained observations",
            live["retained_observations"],
            "raw position rows · latest 15 minutes",
        )

    cadence = live["observation_cadence"]
    routes = live["top_routes"]
    modes = live["route_modes"]
    with ui.element("section").classes(
        "grid w-full grid-cols-1 gap-5 lg:grid-cols-2 xl:grid-cols-3"
    ):
        if modes:
            _chart_card(
                "Fresh fleet by service type",
                "A current quality slice of map-usable records by Calgary route category; "
                "it measures feed coverage, not ridership.",
                {
                    "tooltip": {"trigger": "item"},
                    "legend": {"type": "scroll", "bottom": 0},
                    "series": [
                        {
                            "name": "Fresh vehicles",
                            "type": "pie",
                            "radius": ["38%", "68%"],
                            "center": ["50%", "44%"],
                            "data": [
                                {"name": row["mode"].replace("_", " ").title(), "value": row["vehicles"]}
                                for row in modes
                            ],
                        }
                    ],
                },
            )

        if cadence:
            labels = [row["minute"][11:16] for row in cadence]
            _chart_card(
                "Realtime ingestion cadence",
                f"{sum(row['observations'] for row in cadence):,} position rows across "
                f"{len(cadence)} observed minutes. Times are UTC.",
                {
                    "tooltip": {"trigger": "axis"},
                    "legend": {"data": ["Observations", "Distinct vehicles"], "bottom": 0},
                    "grid": {"left": 45, "right": 18, "top": 24, "bottom": 58},
                    "xAxis": {"type": "category", "data": labels},
                    "yAxis": {"type": "value", "minInterval": 1},
                    "series": [
                        {
                            "name": "Observations",
                            "type": "line",
                            "smooth": True,
                            "data": [row["observations"] for row in cadence],
                            "itemStyle": {"color": "#2563eb"},
                        },
                        {
                            "name": "Distinct vehicles",
                            "type": "line",
                            "data": [row["vehicles"] for row in cadence],
                            "itemStyle": {"color": "#d97706"},
                        },
                    ],
                },
            )
        else:
            with ui.card().classes("w-full p-5"):
                ui.label("Realtime ingestion cadence").classes("text-xl font-semibold")
                ui.label("No observations are retained outside live polling hours.").classes(
                    "text-sm text-grey-7"
                )

        if routes:
            _chart_card(
                "Busiest active routes",
                "Top ten routes by fresh vehicle records; this is service coverage, not ridership.",
                {
                    "tooltip": {"trigger": "axis"},
                    "grid": {"left": 45, "right": 18, "top": 24, "bottom": 48},
                    "xAxis": {"type": "category", "data": [row["route"] for row in routes]},
                    "yAxis": {"type": "value", "minInterval": 1},
                    "series": [
                        {
                            "name": "Fresh vehicles",
                            "type": "bar",
                            "data": [row["vehicles"] for row in routes],
                            "itemStyle": {"color": "#0f766e"},
                        }
                    ],
                },
            )
        else:
            with ui.card().classes("w-full p-5"):
                ui.label("Busiest active routes").classes("text-xl font-semibold")
                ui.label("No fresh route records are available right now.").classes(
                    "text-sm text-grey-7"
                )

    with ui.card().classes("w-full p-5 gap-2"):
        ui.label("Live pipeline provenance").classes("text-xl font-semibold")
        ui.label(f"Analysis generated: {live['generated_at']} UTC").classes("text-sm")
        ui.label(f"Latest VehiclePositions: {live['latest_vehicle_timestamp']}").classes(
            "text-sm text-grey-7"
        )
        ui.label(f"Latest TripUpdates: {live['latest_trip_update_timestamp']}").classes(
            "text-sm text-grey-7"
        )
        ui.label(f"Latest Alerts: {live['latest_alert_timestamp']}").classes(
            "text-sm text-grey-7"
        )
        ui.label(
            "Source: City of Calgary GTFS and GTFS-Realtime. Freshness and completeness "
            "depend on the source feeds; polling runs 08:00–21:00 America/Edmonton."
        ).classes("text-sm text-grey-7 leading-relaxed")


def _cached_dashboard(snapshot: dict) -> None:
    ui.label("Versioned cached analysis").classes("text-2xl font-semibold")
    ui.label(
        "A committed theme-park demonstration snapshot shows the low-latency delivery "
        "pattern for slower-changing analytical products. It is sample data, not live operations."
    ).classes("text-base text-grey-7 leading-relaxed")
    ui.link(
        "See the analytics delivery case study",
        "/projects#project-theme-park-analytics",
    ).classes("text-primary font-semibold no-underline hover:underline")

    if not snapshot.get("available"):
        ui.label("The committed analysis snapshot is unavailable.").classes("text-negative")
        return

    tables = snapshot["tables"]
    daily = sorted(tables["daily_stats"], key=lambda row: row["date"])
    revenue = sorted(tables["revenue_summary"], key=lambda row: row["date"])
    total_attendance = sum(int(row["total_attendance"]) for row in daily)
    total_revenue = sum(float(row["total_revenue"]) for row in revenue)

    with ui.element("section").classes("grid w-full grid-cols-1 gap-4 sm:grid-cols-3"):
        _metric("Snapshot rows", snapshot["row_count"], "four validated tables")
        _metric("Attendance", f"{total_attendance:,}", "four-day sample")
        _metric("Revenue", f"${total_revenue:,.0f}", "four-day sample")

    with ui.element("section").classes("grid w-full grid-cols-1 gap-5 lg:grid-cols-2"):
        _chart_card(
            "Attendance and member mix",
            f"Total sample attendance is {total_attendance:,}; stacked bars separate "
            "general and member admissions.",
            {
                "tooltip": {"trigger": "axis"},
                "legend": {"data": ["General", "Members"], "bottom": 0},
                "grid": {"left": 50, "right": 18, "top": 24, "bottom": 58},
                "xAxis": {"type": "category", "data": [row["date"] for row in daily]},
                "yAxis": {"type": "value"},
                "series": [
                    {
                        "name": "General",
                        "type": "bar",
                        "stack": "attendance",
                        "data": [row["general_admissions"] for row in daily],
                        "itemStyle": {"color": "#2563eb"},
                    },
                    {
                        "name": "Members",
                        "type": "bar",
                        "stack": "attendance",
                        "data": [row["member_admissions"] for row in daily],
                        "itemStyle": {"color": "#7c3aed"},
                    },
                ],
            },
        )
        _chart_card(
            "Revenue composition",
            "Revenue combines admissions, membership, food and beverage, merchandise, and parking.",
            {
                "tooltip": {"trigger": "axis"},
                "legend": {"type": "scroll", "bottom": 0},
                "grid": {"left": 58, "right": 18, "top": 24, "bottom": 72},
                "xAxis": {"type": "category", "data": [row["date"] for row in revenue]},
                "yAxis": {"type": "value"},
                "series": [
                    {
                        "name": label,
                        "type": "bar",
                        "stack": "revenue",
                        "data": [float(row[field]) for row in revenue],
                    }
                    for label, field in (
                        ("Admissions", "admission_revenue"),
                        ("Membership", "membership_revenue"),
                        ("Food & beverage", "food_beverage_revenue"),
                        ("Merchandise", "merchandise_revenue"),
                        ("Parking", "parking_revenue"),
                    )
                ],
            },
        )

    with ui.card().classes("w-full p-5 gap-3"):
        ui.label("Snapshot quality contract").classes("text-xl font-semibold")
        ui.table(
            columns=[
                {"name": "table", "label": "Dataset", "field": "table", "align": "left"},
                {"name": "rows", "label": "Rows", "field": "rows", "align": "right"},
                {"name": "status", "label": "Non-empty", "field": "status", "align": "center"},
            ],
            rows=snapshot["quality"],
            row_key="table",
        ).classes("w-full").props("flat dense")
        ui.label(
            f"Snapshot date: {snapshot['cache_date']} · generated: {snapshot['last_updated']}. "
            "A production snapshot job would publish only after schema and quality checks pass."
        ).classes("text-sm text-grey-7 leading-relaxed")


@ui.page("/dashboard")
@with_layout
def dashboard_page():
    ui.page_title("Bizqlab Analytics Dashboard")
    live = build_live_transit_analysis()
    snapshot = load_cached_analysis()

    with ui.column().classes("w-full max-w-7xl mx-auto px-4 py-8 sm:px-8 gap-7"):
        with ui.column().classes("gap-3 max-w-4xl"):
            ui.label("Data Platform Analytics").classes("text-4xl sm:text-5xl font-bold")
            ui.label(
                "Two delivery patterns in one portfolio: live PostgreSQL aggregates for "
                "fresh operational questions, and a small versioned snapshot for stable analysis."
            ).classes("text-lg text-grey-7 leading-relaxed")

        with ui.element("section").classes(
            "grid w-full grid-cols-1 gap-4 md:grid-cols-2"
        ):
            with ui.card().classes("w-full h-full p-5 gap-2 border"):
                ui.icon("directions_bus", size="md").classes("text-primary")
                ui.label("Project 1 · Realtime transit pipeline").classes(
                    "text-xl font-semibold"
                )
                ui.label(
                    "The live metrics below validate ingestion cadence, static-GTFS "
                    "enrichment, active-route coverage, and retained observations used by the map."
                ).classes("text-sm text-grey-7 leading-relaxed")
            with ui.card().classes("w-full h-full p-5 gap-2 border"):
                ui.icon("inventory_2", size="md").classes("text-primary")
                ui.label("Project 2 · Versioned analytics delivery").classes(
                    "text-xl font-semibold"
                )
                ui.label(
                    "The snapshot section demonstrates schema validation, quality gates, "
                    "provenance, and fast delivery for slower-changing analytical data."
                ).classes("text-sm text-grey-7 leading-relaxed")

        _live_dashboard(live)
        ui.separator()
        _cached_dashboard(snapshot)
        enable_viewport_chart_animations()
