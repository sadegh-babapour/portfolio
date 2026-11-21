"""/admin/resume: edit the résumé timeline and replace the résumé PDF, without a deploy.
Same pattern as app/pages/admin_blog.py.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from functools import partial

from nicegui import ui
from nicegui.events import UploadEventArguments

from app.admin.service import require_admin
from app.auth.service import SESSION_COOKIE
from app.components.admin_nav import admin_navigation
from app.components.navbar import with_layout
from app.resume.document import MAX_PDF_BYTES, ResumePdfError, resume_pdf_path
from app.resume.upload import save_uploaded_pdf
from app.resume.service import (
    KINDS,
    ResumeValidationError,
    delete_entry,
    get_entry,
    list_entries,
    move_entry,
    save_entry,
)


log = logging.getLogger(__name__)


def _lines(value: str) -> list[str]:
    return [line for line in str(value or "").splitlines() if line.strip()]


def _commas(value: str) -> list[str]:
    return [item for item in str(value or "").split(",") if item.strip()]


@ui.page("/admin/resume")
@with_layout
def admin_resume():
    request = ui.context.client.request
    require_admin(request.cookies.get(SESSION_COOKIE))
    ui.page_title("Résumé timeline — Bizqlab")

    selected: dict[str, uuid.UUID | None] = {"id": None}

    with ui.column().classes("w-full max-w-7xl mx-auto px-4 py-8 sm:px-8 gap-6"):
        admin_navigation("/admin/resume")
        with ui.column().classes("gap-2"):
            ui.label("Résumé timeline").classes("text-4xl font-bold")
            ui.label(
                "Entries show on /resume as soon as you save. Newest first; use the arrows to reorder."
            ).classes("text-grey-7")

        with ui.element("section").classes(
            "grid w-full grid-cols-1 gap-5 lg:grid-cols-[minmax(15rem,22rem)_minmax(0,1fr)]"
        ):
            with ui.card().classes("w-full p-4 gap-3"):
                with ui.row().classes("w-full items-center justify-between gap-2"):
                    ui.label("Entries").classes("text-xl font-semibold")
                    new_button = ui.button("New entry", icon="add").props("outline no-caps")
                entries_container = ui.column().classes("w-full gap-1")

            with ui.card().classes("w-full min-w-0 p-4 sm:p-6 gap-4"):
                with ui.row().classes("w-full gap-3 flex-wrap sm:flex-nowrap"):
                    period = ui.input("Period", placeholder="2022 – present").classes(
                        "w-full sm:w-56"
                    ).props("outlined maxlength=60")
                    kind = ui.select(
                        {value: value.title() for value in KINDS}, label="Type", value="work"
                    ).classes("w-full sm:w-48").props("outlined")
                title = ui.input("Title", placeholder="Data Engineer").classes("w-full").props(
                    "outlined maxlength=160"
                )
                organization = ui.input(
                    "Organization", placeholder="Company or school, City"
                ).classes("w-full").props("outlined maxlength=160")
                summary = ui.textarea(
                    "Summary (optional)", placeholder="One or two sentences."
                ).classes("w-full").props("outlined autogrow maxlength=600")
                highlights = ui.textarea(
                    "Highlights, one per line (optional)",
                    placeholder="Built the nightly load that feeds finance reporting",
                ).classes("w-full").props("outlined autogrow")
                skills = ui.input(
                    "Skills, comma separated (optional)", placeholder="Python, SQL, dbt"
                ).classes("w-full").props("outlined")
                visible = ui.switch("Show on the résumé page", value=True)

                with ui.row().classes("w-full gap-3 flex-wrap"):
                    save_button = ui.button("Save", icon="save").props(
                        "unelevated no-caps color=primary"
                    )
                    delete_button = ui.button("Delete", icon="delete").props(
                        "outline no-caps color=negative"
                    )
                    delete_button.disable()
                status_label = ui.label("New unsaved entry").classes("min-h-6 text-sm text-grey-7")

        with ui.card().classes("w-full p-4 sm:p-6 gap-3"):
            ui.label("Résumé PDF").classes("text-xl font-semibold")
            pdf_status = ui.label().classes("text-sm text-grey-7")
            pdf_upload = ui.upload(
                label="Upload a new PDF (replaces the current one)",
                auto_upload=True,
                max_files=1,
                max_file_size=MAX_PDF_BYTES,
                on_rejected=lambda: ui.notify("PDF only, 5 MB or smaller.", type="warning"),
            ).props('accept=".pdf,application/pdf" flat bordered').classes("w-full max-w-md")

        with ui.dialog() as delete_dialog, ui.card().classes("w-full max-w-md p-5 gap-4"):
            ui.label("Delete this entry?").classes("text-xl font-semibold")
            ui.label("It is removed from the résumé page permanently.").classes(
                "text-sm text-grey-7"
            )
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=delete_dialog.close).props("flat no-caps")
                confirm_delete_button = ui.button("Delete permanently", icon="delete").props(
                    "unelevated no-caps color=negative"
                )

    def check_admin() -> None:
        require_admin(request.cookies.get(SESSION_COOKIE))

    def refresh_pdf_status() -> None:
        try:
            stat = resume_pdf_path().stat()
            pdf_status.set_text(
                f"Current file: {stat.st_size / 1024:,.0f} KB, replaced "
                f"{datetime.fromtimestamp(stat.st_mtime, timezone.utc):%Y-%m-%d %H:%M} UTC."
            )
        except OSError:
            pdf_status.set_text("No PDF yet; /resume shows a placeholder until you upload one.")

    async def upload_pdf(event: UploadEventArguments) -> None:
        try:
            await save_uploaded_pdf(event.file, check_admin)
            refresh_pdf_status()
            ui.notify("Résumé PDF replaced.", type="positive")
        except ResumePdfError as exc:
            ui.notify(str(exc), type="warning")
        except Exception:
            log.exception("Unable to replace the résumé PDF")
            ui.notify("The PDF could not be saved.", type="negative")
        finally:
            event.sender.reset()

    def refresh_entries() -> None:
        entries_container.clear()
        try:
            entries = list_entries(visible_only=False)
        except Exception:
            log.exception("Unable to list résumé entries")
            with entries_container:
                ui.label("Entries are temporarily unavailable.").classes("text-negative")
            return
        with entries_container:
            if not entries:
                ui.label("No entries yet. Choose New entry to begin.").classes(
                    "text-sm text-grey-7"
                )
            for index, entry in enumerate(entries):
                with ui.row().classes("w-full items-center gap-1 no-wrap"):
                    current = entry.id == selected["id"]
                    with ui.column().classes(
                        "grow min-w-0 gap-0 cursor-pointer rounded-lg px-3 py-2"
                        + (" bg-primary text-white" if current else " hover:bg-[var(--bq-chip)]")
                    ).on("click", partial(load_entry, entry.id)):
                        ui.label(entry.period).classes("text-sm font-semibold")
                        detail = f"{entry.title} · {entry.organization}"
                        if not entry.visible:
                            detail += " (hidden)"
                        ui.label(detail).classes("text-sm" + ("" if current else " text-grey-7"))
                    up = ui.button(icon="arrow_upward", on_click=partial(move, entry.id, -1)).props(
                        'flat round dense aria-label="Move up"'
                    )
                    down = ui.button(
                        icon="arrow_downward", on_click=partial(move, entry.id, 1)
                    ).props('flat round dense aria-label="Move down"')
                    if index == 0:
                        up.disable()
                    if index == len(entries) - 1:
                        down.disable()

    def load_entry(entry_id: uuid.UUID) -> None:
        try:
            check_admin()
            entry = get_entry(entry_id)
            if entry is None:
                raise ResumeValidationError("Entry was not found")
            selected["id"] = entry.id
            delete_button.enable()
            period.set_value(entry.period)
            kind.set_value(entry.kind)
            title.set_value(entry.title)
            organization.set_value(entry.organization)
            summary.set_value(entry.summary)
            highlights.set_value("\n".join(entry.highlights))
            skills.set_value(", ".join(entry.skills))
            visible.set_value(entry.visible)
            status_label.set_text("Editing a saved entry")
            refresh_entries()
        except Exception:
            log.exception("Unable to load résumé entry %s", entry_id)
            ui.notify("The entry could not be loaded.", type="negative")

    def reset_editor() -> None:
        selected["id"] = None
        delete_button.disable()
        for field in (period, title, organization, summary, highlights, skills):
            field.set_value("")
        kind.set_value("work")
        visible.set_value(True)
        status_label.set_text("New unsaved entry")
        refresh_entries()
        period.run_method("focus")

    def persist() -> None:
        try:
            check_admin()
            entry = save_entry(
                entry_id=selected["id"],
                period=str(period.value or ""),
                title=str(title.value or ""),
                organization=str(organization.value or ""),
                kind=str(kind.value or ""),
                summary=str(summary.value or ""),
                highlights=_lines(highlights.value),
                skills=_commas(skills.value),
                visible=bool(visible.value),
            )
            selected["id"] = entry.id
            delete_button.enable()
            status_label.set_text("Saved")
            refresh_entries()
            ui.notify("Entry saved.", type="positive")
        except ResumeValidationError as exc:
            status_label.set_text(str(exc))
            ui.notify(str(exc), type="warning")
        except Exception:
            log.exception("Unable to save résumé entry")
            status_label.set_text("The entry could not be saved. Please try again.")
            ui.notify("The entry could not be saved.", type="negative")

    def move(entry_id: uuid.UUID, step: int) -> None:
        try:
            check_admin()
            move_entry(entry_id, step)
            refresh_entries()
        except Exception:
            log.exception("Unable to move résumé entry %s", entry_id)
            ui.notify("The entry could not be moved.", type="negative")

    def confirm_delete() -> None:
        entry_id = selected["id"]
        delete_dialog.close()
        if entry_id is None:
            return
        try:
            check_admin()
            delete_entry(entry_id)
            reset_editor()
            ui.notify("Entry deleted.", type="positive")
        except Exception:
            log.exception("Unable to delete résumé entry %s", entry_id)
            ui.notify("The entry could not be deleted.", type="negative")

    pdf_upload.on_upload(upload_pdf)
    new_button.on("click", reset_editor)
    save_button.on("click", persist)
    delete_button.on("click", delete_dialog.open)
    confirm_delete_button.on("click", confirm_delete)

    refresh_pdf_status()
    refresh_entries()
