from fastapi.staticfiles import StaticFiles
from nicegui import ui
from nicegui import app as fastapi_app
import os
from dotenv import load_dotenv

# Mount static
fastapi_app.mount('/static', StaticFiles(directory='static'), name='static')

# Import components
# from app.components.navbar import drawer, with_layout
from app.components.footer import footer

# Register pages (each uses @with_layout)
def _import_pages():
    import app.pages.home
    import app.pages.about
    import app.pages.resume
    import app.pages.projects
    import app.pages.contact
    import app.pages.dashboard




# if __name__ == "__main__":
if __name__ in {"__main__", "__mp_main__"}:
    _import_pages()
    # Start server
    port = int(os.environ.get('PORT', 8080))
    ui.run(title='My Portfolio SPA',port=port, host='0.0.0.0', dark=False)