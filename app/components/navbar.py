from nicegui import ui
from functools import wraps
from .footer import footer

NAV_LINKS = [
    ('Home', '/'),
    ('About', '/about'),
    ('Resume', '/resume'),
    ('Projects', '/projects'),
    ('Contact', '/contact'),
    ('Dashboard', '/dashboard')
]

HEADER_PROPS = dict(
    fixed=True,
    bordered=False,
    elevated=True,
    wrap=True,
    add_scroll_padding=True,
)

def navbar():
    # create a per-page left drawer and populate it
    with ui.left_drawer(bordered=True).props('width=250') as drawer:
        for label, path in NAV_LINKS:
            ui.link(label, path).props('dense')

    # header uses the drawer for menu toggling
    with ui.header(**HEADER_PROPS).classes('bg-primary text-white shadow'):
        with ui.row().classes('items-center justify-between max-w-screen-xl mx-auto p-4'):
            # hamburger button on small screens
            ui.button(icon='menu', on_click=drawer.toggle).classes('lg:hidden').props('flat color=white')
            # brand/logo
            ui.label('My Portfolio').classes('text-2xl font-bold')
            # desktop navigation links
            with ui.row().classes('hidden lg:flex gap-6'):
                for label, path in NAV_LINKS:
                    ui.link(label, path).classes('text-white hover:underline')

def with_layout(page_func):
    @wraps(page_func)
    def wrapper(*args, **kwargs):
        navbar()
        result = page_func(*args, **kwargs)
        footer()
        return result
    return wrapper