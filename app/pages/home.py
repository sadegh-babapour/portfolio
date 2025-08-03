from nicegui import ui
from app.components.navbar import navbar
from app.components.navbar import with_layout

@ui.page('/')
@with_layout
def home():
    with ui.column().classes('mx-auto max-w-screen-xl p-8'):
        ui.label('Welcome to My Portfolio!').classes('text-4xl mb-4')
        ui.label('Explore my work, skills, and get in touch.')