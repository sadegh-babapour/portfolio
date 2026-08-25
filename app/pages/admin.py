from __future__ import annotations

from nicegui import ui

from app.admin.service import build_admin_summary, require_admin
from app.auth.service import SESSION_COOKIE
from app.components.navbar import with_layout


def _metric(title: str, value: object, note: str = "") -> None:
    with ui.card().classes("w-full h-full p-5 gap-2"):
        ui.label(title).classes("text-sm text-grey-7")
        ui.label(str(value)).classes("text-3xl font-semibold")
        if note:
            ui.label(note).classes("text-xs text-grey-7")


@ui.page("/admin")
@with_layout
def admin():
    request = ui.context.client.request
    require_admin(request.cookies.get(SESSION_COOKIE))
    summary = build_admin_summary()
    traffic = summary["traffic"]
    identity = summary["identity"]
    contact = summary["contact"]
    transit = summary["transit"]

    with ui.column().classes("w-full max-w-6xl mx-auto px-4 py-8 sm:px-8 gap-6"):
        ui.label("Operational health").classes("text-4xl")
        ui.label(
            "Owner-only, read-only aggregates. Page renders are not unique visitors."
        ).classes("text-base text-grey-7")

        ui.label("Traffic").classes("text-2xl font-semibold")
        with ui.element("section").classes("grid w-full grid-cols-1 gap-4 sm:grid-cols-3"):
            _metric("Last 24 hours", traffic["today"], "anonymous page renders")
            _metric("Last 7 days", traffic["seven_days"], "anonymous page renders")
            _metric("Last 30 days", traffic["thirty_days"], "anonymous page renders")

        with ui.element("section").classes("grid w-full grid-cols-1 gap-5 lg:grid-cols-2"):
            with ui.card().classes("w-full p-5 gap-3"):
                ui.label("Top pages · 30 days").classes("text-xl font-semibold")
                ui.table(
                    columns=[
                        {"name": "path", "label": "Page", "field": "path", "align": "left"},
                        {"name": "views", "label": "Renders", "field": "views", "align": "right"},
                    ],
                    rows=summary["top_paths"],
                    row_key="path",
                ).classes("w-full").props("flat dense")
            with ui.card().classes("w-full p-5 gap-3"):
                ui.label("Daily renders · 14 days").classes("text-xl font-semibold")
                ui.table(
                    columns=[
                        {"name": "day", "label": "UTC day", "field": "day", "align": "left"},
                        {"name": "views", "label": "Renders", "field": "views", "align": "right"},
                    ],
                    rows=summary["daily_views"],
                    row_key="day",
                ).classes("w-full").props("flat dense")

        ui.label("Accounts and contact").classes("text-2xl font-semibold")
        with ui.element("section").classes("grid w-full grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"):
            _metric("Active users", identity["active_users"], f'{identity["users"]} total')
            _metric("Active sessions", identity["active_sessions"])
            _metric("Logins · 7 days", identity["successful_logins_7d"])
            _metric("Contacts · 30 days", contact["thirty_days"])
        if contact["statuses"]:
            ui.label(
                "Contact states: "
                + ", ".join(f"{key.replace('_', ' ')}: {value}" for key, value in contact["statuses"].items())
            ).classes("text-sm text-grey-7")

        ui.label("Calgary Transit freshness").classes("text-2xl font-semibold")
        with ui.card().classes("w-full p-5 gap-3"):
            with ui.row().classes("items-center gap-3 flex-wrap"):
                ui.badge(str(transit["status"]).replace("_", " ").title()).props("outline")
                ui.label("Operating window: 08:00–21:00 America/Edmonton").classes("text-sm text-grey-7")
            if transit["status"] != "unavailable":
                age = transit["vehicle_age_seconds"]
                ui.label(
                    f"Recent vehicles: {transit['recent_vehicle_count']} · "
                    f"Newest vehicle age: {round(age)} seconds" if age is not None
                    else f"Recent vehicles: {transit['recent_vehicle_count']} · no vehicle timestamp"
                )
                ui.label(f"Latest vehicle feed: {transit['latest_vehicle_timestamp']}").classes("text-sm text-grey-7")
                ui.label(f"Latest trip feed: {transit['latest_trip_update_timestamp']}").classes("text-sm text-grey-7")
                ui.label(f"Latest alert feed: {transit['latest_alert_timestamp']}").classes("text-sm text-grey-7")
            else:
                ui.label("Transit freshness could not be read from PostgreSQL.").classes("text-negative")

        ui.label(
            f"Anonymous page-render records are automatically deleted after "
            f"{summary['analytics_retention_days']} days."
        ).classes("text-sm text-grey-7")
