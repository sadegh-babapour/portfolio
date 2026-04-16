from nicegui import ui
from app.components.navbar import navbar
from app.components.navbar import with_layout

@ui.page('/contact')
@with_layout
def contact():
    with ui.column().classes('mx-auto max-w-screen-xl p-8'):
        ui.label('Contact Me').classes('text-4xl mb-4')
        name = ui.input('Your Name').classes('w-full max-w-md')
        email = ui.input('Email').props('type=email').classes('w-full max-w-md')
        message = ui.textarea('Message').classes('w-full max-w-md')
        def submit():
            ui.notify(f"Thanks, {name.value}! Your message has been sent.")
        ui.button('Send', on_click=submit, icon='send').classes('mt-4')