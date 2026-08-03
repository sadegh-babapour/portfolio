from nicegui import ui
from app.components.pdf_viewer import create_pdf_viewer
from app.components.navbar import with_layout

@ui.page('/resume')
@with_layout
def resume():
    with ui.column().classes('w-full px-4 py-6 sm:px-6 lg:px-8'):
        ui.label('My Resume').classes('text-4xl mb-4')
        with ui.timeline(side='right', layout='comfortable').classes('w-full max-w-2xl mx-auto mb-8'):
            ui.timeline_entry('Started at Company A', title='2020', subtitle='Junior Developer', icon='work', color='green')
            ui.timeline_entry('Graduated with B.Sc. in CS', title='2022', subtitle='University XYZ', icon='school', color='blue')
            ui.timeline_entry('Joined Data Science Bootcamp', title='2023', subtitle='Bootcamp Institute', icon='school', color='purple')
        ui.separator().classes('my-8')
        ui.label('Resume Document').classes('text-2xl mb-4')
        create_pdf_viewer('/resume/document.pdf')
