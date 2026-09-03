from __future__ import annotations

from nicegui import ui


ADMIN_LINKS = (
    ("Operational health", "/admin"),
    ("Blog publishing", "/admin/blog"),
    ("View public blog", "/blog"),
)


def admin_navigation(current_path: str) -> None:
    """Render the small owner-console navigation shared by admin pages."""
    with ui.element("nav").classes(
        "w-full flex flex-wrap items-center gap-2 rounded-xl border p-2"
    ).props('aria-label="Administration"'):
        ui.label("Admin").classes("px-2 text-xs font-bold uppercase tracking-wide text-grey-7")
        for label, path in ADMIN_LINKS:
            classes = "rounded-lg px-3 py-2 text-sm font-semibold no-underline"
            if path == current_path:
                classes += " bg-primary text-white"
            else:
                classes += " text-primary hover:underline"
            ui.link(label, path).classes(classes)
