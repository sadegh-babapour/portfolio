import logging

from nicegui import ui
from app.components.pdf_viewer import create_pdf_viewer
from app.components.navbar import with_layout
from app.resume.document import resume_pdf_version
from app.resume.service import list_entries


log = logging.getLogger(__name__)
KIND_ICONS = {
    "work": "work",
    "education": "school",
    "project": "construction",
    "milestone": "flag",
}


@ui.page('/resume')
@with_layout
def resume():
    with ui.column().classes('w-full max-w-7xl mx-auto px-4 py-8 sm:px-8'):
        ui.label('Résumé').classes('text-4xl sm:text-5xl font-bold mb-6')
        try:
            entries = list_entries(visible_only=True)
        except Exception:
            log.exception('Unable to load the résumé timeline')
            entries = []
        if entries:
            ui.label('Career').classes('text-2xl font-semibold w-full max-w-4xl mx-auto')
            ui.label('Where I’ve worked and studied.').classes(
                'w-full max-w-4xl mx-auto text-base text-grey-7 mb-4'
            )
            with ui.timeline(side='right', layout='dense').classes(
                'w-full max-w-4xl mx-auto mb-8'
            ):
                for entry in entries:
                    with ui.timeline_entry(
                        title=entry.title,
                        subtitle=entry.period,
                        icon=KIND_ICONS.get(entry.kind, 'circle'),
                        color='primary',
                    ):
                        ui.label(entry.organization).classes('text-sm font-semibold text-grey-7')
                        if entry.summary:
                            ui.label(entry.summary).classes('text-sm leading-relaxed')
                        if entry.highlights:
                            with ui.element('ul').classes('list-disc pl-5 text-sm leading-relaxed'):
                                for highlight in entry.highlights:
                                    ui.label(highlight).classes('list-item')
                        if entry.skills:
                            with ui.row().classes('gap-1 flex-wrap pt-1'):
                                for skill in entry.skills:
                                    ui.chip(skill).props('outline dense').classes('text-xs')
            ui.separator().classes('my-8')
            ui.label('Full résumé').classes('text-2xl font-semibold mb-4')
        create_pdf_viewer(f'/resume/document.pdf?v={resume_pdf_version()}')
