from nicegui import ui


def footer():
    """A slim footer line; colours come from static/site.css."""
    with ui.footer(fixed=False, bordered=False, elevated=False, wrap=True).classes('portfolio-footer'):
        with ui.row().classes('w-full max-w-7xl mx-auto justify-between items-center gap-4 px-4 py-3 sm:px-8 text-sm'):
            ui.label('© 2026 Bizqlab')
            with ui.row().classes('gap-4'):
                ui.link('Privacy', '/privacy').classes('no-underline')
                ui.link('Terms', '/terms').classes('no-underline')
