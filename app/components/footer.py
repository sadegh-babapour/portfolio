from nicegui import ui

# Footer initializer props (equivalent API)
FOOTER_PROPS = dict(
    fixed=False,
    bordered=True,
    elevated=True,
    wrap=True,
    # add_scroll_padding=False,
)

# Draw footer
def footer():
    with ui.footer(**FOOTER_PROPS).classes('bg-primary text-white shadow'):
        with ui.row().classes('justify-center items-center gap-4 p-4'):
            ui.label('© 2025 My Portfolio')
            ui.link('Privacy', '/privacy').classes('text-white hover:underline')
            ui.link('Terms', '/terms').classes('text-white hover:underline')