from nicegui import ui

from app.components.navbar import with_layout


@ui.page('/')
@with_layout
def home():
    ui.add_head_html('''
      <meta name="description" content="Bizqlab is a data engineering and analytics portfolio with public case studies, live demonstrations and build notes for signed-in users.">
      <link rel="canonical" href="https://www.bizqlab.com/">
      <meta property="og:site_name" content="Bizqlab">
      <meta property="og:title" content="Bizqlab — Data engineering and analytics portfolio">
      <meta property="og:description" content="Public case studies and working demonstrations of data pipelines, database design, operational monitoring, analytics, and visualization.">
      <meta property="og:type" content="website">
      <meta property="og:url" content="https://www.bizqlab.com/">
      <meta property="og:image" content="https://www.bizqlab.com/static/bizqlab_logo.png">
      <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "WebSite",
          "name": "Bizqlab",
          "url": "https://www.bizqlab.com/",
          "logo": "https://www.bizqlab.com/static/bizqlab_logo.png",
          "description": "A data engineering and analytics portfolio with public case studies, live demonstrations and build notes for signed-in users."
        }
      </script>
    ''')
    with ui.column().classes('w-full max-w-7xl mx-auto px-4 py-8 sm:px-8 gap-10'):
        with ui.element('section').classes(
            'grid w-full grid-cols-1 items-center gap-8 lg:grid-cols-[minmax(0,1.35fr)_minmax(18rem,.65fr)]'
        ):
            with ui.column().classes('gap-5 max-w-4xl'):
                ui.image('/static/bizqlab_logo.png').props(
                    'alt="Bizqlab logo" fit=contain'
                ).classes('w-32 h-32 sm:w-40 sm:h-40 rounded-2xl bg-white shadow-sm')
                ui.label('Bizqlab').classes('text-sm uppercase tracking-widest text-primary font-bold')
                ui.label('Data systems, made understandable').classes(
                    'text-4xl sm:text-5xl lg:text-6xl font-bold leading-tight'
                )
                ui.label(
                    'Data pipelines, analytics and the apps on top, built and running live.'
                ).classes('text-lg sm:text-xl text-grey-7 leading-relaxed')
                with ui.row().classes('gap-3 flex-wrap'):
                    ui.button('See projects', on_click=lambda: ui.navigate.to('/projects')).props(
                        'unelevated no-caps icon=account_tree'
                    )
                    ui.button(
                        'Résumé', on_click=lambda: ui.navigate.to('/resume')
                    ).props('outline no-caps icon=description')

            with ui.card().classes('w-full p-6 sm:p-8 gap-4'):
                ui.icon('stream', size='lg').classes('text-primary')
                ui.label('Live now: Calgary Transit').classes('text-2xl font-semibold')
                ui.label(
                    'Buses from the city\'s realtime feed, through a Python poller, '
                    'PostgreSQL and an Express API, onto a React map.'
                ).classes('text-grey-7 leading-relaxed')
                ui.link('Open the map →', '/calgary-transit-live/').classes(
                    'text-primary font-semibold no-underline hover:underline'
                )

        with ui.column().classes('w-full gap-4'):
            ui.label('What Bizqlab does').classes('text-2xl font-semibold')
            ui.label(
                'Working examples of data pipelines, databases and analytics, with notes on '
                'how each is built and where it falls short.'
            ).classes('text-base text-grey-7 leading-relaxed max-w-4xl')
            with ui.element('section').classes('grid w-full grid-cols-1 gap-5 md:grid-cols-3'):
                cards = (
                    ('database', 'Data engineering', 'Ingestion, modelling, migrations and retention.'),
                    ('analytics', 'Analytics', 'Charts that say where the data came from and how fresh it is.'),
                    ('web', 'Apps', 'Interfaces you can use, not just a repository to read.'),
                )
                for icon, title, copy in cards:
                    with ui.card().classes('w-full h-full p-6 gap-3'):
                        ui.icon(icon, size='md').classes('text-primary')
                        ui.label(title).classes('text-xl font-semibold')
                        ui.label(copy).classes('text-sm text-grey-7 leading-relaxed')

        with ui.card().classes('w-full p-6 sm:p-8 gap-3'):
            ui.label('How I work').classes('text-xl font-semibold')
            for item in (
                'Start from the question and how reliable the source is.',
                'Keep ingestion, storage, APIs and screens separate.',
                'Show freshness and limits instead of hiding them.',
                'Test where separately deployed services meet.',
            ):
                with ui.row().classes('items-start gap-2 no-wrap'):
                    ui.icon('check_circle', size='xs').classes('mt-1 text-primary')
                    ui.label(item).classes('text-sm leading-relaxed')

        with ui.row().classes('w-full items-center gap-x-4 gap-y-1 flex-wrap text-sm text-grey-7'):
            ui.label(
                'No account needed to browse. Google sign-in uses your name and verified '
                'email to unlock project build notes.'
            )
            ui.link('How account data is used', '/privacy').classes(
                'text-primary font-semibold no-underline hover:underline'
            )
