from nicegui import ui

from app.components.navbar import with_layout


@ui.page('/')
@with_layout
def home():
    with ui.column().classes('w-full max-w-7xl mx-auto px-4 py-8 sm:px-8 gap-10'):
        with ui.element('section').classes(
            'grid w-full grid-cols-1 items-center gap-8 lg:grid-cols-[minmax(0,1.35fr)_minmax(18rem,.65fr)]'
        ):
            with ui.column().classes('gap-5 max-w-4xl'):
                ui.label('Data systems, made understandable').classes(
                    'text-4xl sm:text-5xl lg:text-6xl font-bold leading-tight'
                )
                ui.label(
                    'A working portfolio of data engineering, analytics, and web '
                    'applications—from realtime ingestion to decision-ready interfaces.'
                ).classes('text-lg sm:text-xl text-grey-7 leading-relaxed')
                with ui.row().classes('gap-3 flex-wrap'):
                    ui.button('Explore projects', on_click=lambda: ui.navigate.to('/projects')).props(
                        'unelevated icon=account_tree'
                    )
                    ui.button(
                        'View résumé', on_click=lambda: ui.navigate.to('/resume')
                    ).props('outline icon=description')

            with ui.card().classes('w-full p-6 sm:p-8 gap-4'):
                ui.icon('stream', size='lg').classes('text-primary')
                ui.label('Live engineering example').classes('text-2xl font-semibold')
                ui.label(
                    'Follow Calgary vehicle observations through a Python poller, '
                    'PostgreSQL, Express, and a responsive React map.'
                ).classes('text-grey-7 leading-relaxed')
                ui.link('Open Calgary Transit Live →', '/calgary-transit-live/').classes(
                    'text-primary font-semibold no-underline hover:underline'
                )

        with ui.element('section').classes('grid w-full grid-cols-1 gap-5 md:grid-cols-3'):
            cards = (
                ('database', 'Data engineering', 'Ingestion, relational modeling, migrations, retention, and operational boundaries.'),
                ('analytics', 'Data analysis', 'Clear analytical views with explicit provenance, freshness, and limitations.'),
                ('web', 'Product delivery', 'Responsive interfaces that let people experience the work instead of only reading a repository.'),
            )
            for icon, title, copy in cards:
                with ui.card().classes('w-full h-full p-6 gap-3'):
                    ui.icon(icon, size='md').classes('text-primary')
                    ui.label(title).classes('text-xl font-semibold')
                    ui.label(copy).classes('text-sm text-grey-7 leading-relaxed')
