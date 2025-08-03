from nicegui import ui
from app.components.navbar import navbar
from app.components.navbar import with_layout

@ui.page('/about')
@with_layout
def about():
    with ui.column().classes('mx-auto max-w-screen-xl p-8'):
        ui.label('About Me').classes('text-4xl mb-4')
        ui.label('I am a Python developer with a focus on data apps, dashboards, and web tooling.')