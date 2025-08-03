from nicegui import ui
from app.components.navbar import navbar
from app.components.pdf_viewer import create_pdf_viewer
from app.components.navbar import with_layout

@ui.page('/resume')
@with_layout
def resume():
    with ui.column().classes('mx-auto max-w-screen-xl p-8'):
        ui.label('My Resume').classes('text-4xl mb-4')
        with ui.timeline(side='right', layout='comfortable').classes('w-full max-w-2xl mx-auto mb-8'):
            ui.timeline_entry('Started at Company A', title='2020', subtitle='Junior Developer', icon='work', color='green')
            ui.timeline_entry('Graduated with B.Sc. in CS', title='2022', subtitle='University XYZ', icon='school', color='blue')
            ui.timeline_entry('Joined Data Science Bootcamp', title='2023', subtitle='Bootcamp Institute', icon='school', color='purple')
        ui.separator().classes('my-8')
        ui.label('Resume Document').classes('text-2xl mb-4')
        url = 'https://ontheline.trincoll.edu/images/bookdown/sample-local-pdf.pdf'
        create_pdf_viewer(url)
        ui.button('Download Resume - PDF', on_click=lambda: ui.download.from_url(url)).classes('mt-4')