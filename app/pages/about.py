from nicegui import ui

from app.components.navbar import with_layout


@ui.page('/about')
@with_layout
def about():
    with ui.column().classes('w-full max-w-7xl mx-auto px-4 py-8 sm:px-8 gap-8'):
        with ui.column().classes('gap-3 max-w-4xl'):
            ui.label('About this portfolio').classes('text-4xl sm:text-5xl font-bold')
            ui.label(
                'I build Python-centered data applications and care about the full path '
                'from source reliability and database design to a useful human interface.'
            ).classes('text-lg sm:text-xl text-grey-7 leading-relaxed')

        with ui.element('section').classes('grid w-full grid-cols-1 gap-5 lg:grid-cols-2'):
            with ui.card().classes('w-full h-full p-6 sm:p-8 gap-4'):
                ui.icon('engineering', size='lg').classes('text-primary')
                ui.label('How I approach the work').classes('text-2xl font-semibold')
                for item in (
                    'Start with the business question and the reliability of the source.',
                    'Keep ownership boundaries clear between ingestion, storage, APIs, and presentation.',
                    'Expose freshness, uncertainty, and limitations instead of hiding them.',
                    'Test the interfaces where independently deployed services meet.',
                ):
                    with ui.row().classes('items-start gap-2 no-wrap'):
                        ui.icon('check_circle', size='xs').classes('mt-1 text-primary')
                        ui.label(item).classes('text-sm leading-relaxed')

            with ui.card().classes('w-full h-full p-6 sm:p-8 gap-4'):
                ui.icon('hub', size='lg').classes('text-primary')
                ui.label('What you can inspect here').classes('text-2xl font-semibold')
                ui.label(
                    'The Projects page explains architecture and trade-offs, the Dashboard '
                    'shows a static analytical snapshot, and Calgary Transit demonstrates a '
                    'live multi-service data product.'
                ).classes('text-grey-7 leading-relaxed')
                with ui.row().classes('gap-3 flex-wrap mt-auto'):
                    ui.link('Project case studies', '/projects').classes(
                        'text-primary font-semibold no-underline hover:underline'
                    )
                    ui.link('Contact', '/contact').classes(
                        'text-primary font-semibold no-underline hover:underline'
                    )
