import logging

from nicegui import ui
from app.components.pdf_viewer import create_pdf_viewer
from app.components.navbar import with_layout
from app.content import ContentValidationError, load_resume_timeline


log = logging.getLogger(__name__)

@ui.page('/resume')
@with_layout
def resume():
    with ui.column().classes('w-full px-4 py-6 sm:px-6 lg:px-8'):
        ui.label('My Resume').classes('text-4xl mb-4')
        try:
            timeline = load_resume_timeline()
        except ContentValidationError as exc:
            log.error('Unable to load résumé timeline: %s', exc)
            ui.label('The career timeline is temporarily unavailable.').classes(
                'w-full max-w-2xl mx-auto text-negative'
            )
        else:
            ui.label(timeline.heading).classes('text-2xl w-full max-w-2xl mx-auto')
            ui.label(timeline.intro).classes(
                'w-full max-w-2xl mx-auto text-base text-grey-7 mb-4'
            )
            with ui.timeline(side='right', layout='comfortable').classes(
                'w-full max-w-2xl mx-auto mb-8'
            ):
                for entry in timeline.entries:
                    details = [entry.summary]
                    details.extend(f'• {highlight}' for highlight in entry.highlights)
                    if entry.skills:
                        details.append(f"Skills: {', '.join(entry.skills)}")
                    ui.timeline_entry(
                        '\n'.join(details),
                        title=entry.period,
                        subtitle=f'{entry.title} · {entry.organization}',
                        icon=entry.icon,
                        color=entry.color,
                    )
        ui.separator().classes('my-8')
        ui.label('Resume Document').classes('text-2xl mb-4')
        create_pdf_viewer('/resume/document.pdf')
