"""The site's 404 page: the normal header, footer and theme instead of NiceGUI's default.

NiceGUI 3 registers its own 404 handler, which prints the exception text
("HTTPException: 404: Not Found"). This one replaces it with the same routing rule:
a missing *page* gets this page with status 404; an API or file route that raises 404
itself (e.g. /resume/document.pdf, /api/...) still gets FastAPI's JSON answer.
Registered on import, before the server starts (app/main.py _import_pages).
"""
from __future__ import annotations

from fastapi import Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import Response
from nicegui import Client, app, ui
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.components.navbar import with_layout

# A bus stop with no route: decorative, theme-aware (currentColor), no external file.
STOP_SVG = """
<svg class="not-found-art" viewBox="0 0 160 120" role="img" aria-label="An empty bus stop"
     xmlns="http://www.w3.org/2000/svg" fill="none" stroke="currentColor" stroke-width="3"
     stroke-linecap="round" stroke-linejoin="round">
  <path d="M8 104 H152" opacity="0.35"/>
  <path d="M20 104 C46 104 46 80 72 80" stroke-dasharray="2 9" opacity="0.6"/>
  <path d="M104 104 V30"/>
  <rect x="86" y="10" width="36" height="28" rx="6"/>
  <path d="M95 24 H113" opacity="0.7"/>
  <circle cx="72" cy="80" r="4" fill="currentColor" stroke="none"/>
</svg>
"""

STYLE = """
<style>
  .not-found { text-align: center; }
  .not-found-art { width: 9rem; height: auto; color: var(--bq-blue); margin: 0 auto 1.5rem; }
  .not-found-code { color: var(--bq-muted); letter-spacing: 0.2em; font-weight: 600; }
</style>
"""


def not_found_content() -> None:
    ui.html(STYLE + STOP_SVG, sanitize=False).classes('w-full')
    with ui.column().classes('not-found w-full items-center gap-3'):
        ui.label('404').classes('not-found-code text-sm')
        ui.label('This stop isn’t on the map').classes('text-3xl sm:text-4xl font-bold')
        ui.label('The page you asked for doesn’t exist or has moved.').classes(
            'text-base text-grey-7'
        )
        with ui.row().classes('gap-3 pt-4 justify-center'):
            ui.button('Home', on_click=lambda: ui.navigate.to('/')).props('unelevated')
            ui.button('Projects', on_click=lambda: ui.navigate.to('/projects')).props('outline')


@with_layout
def not_found_page() -> None:
    with ui.column().classes('w-full max-w-3xl mx-auto px-4 py-16 sm:px-8 items-center'):
        not_found_content()


def is_api_or_file_route(request: Request, exception: Exception) -> bool:
    """The same test NiceGUI uses: a matched non-page endpoint that raised 404 itself."""
    endpoint = request.scope.get('endpoint')
    return (
        endpoint is not None
        and endpoint is not app
        and not request.scope.get('nicegui_page_path')
        and isinstance(exception, StarletteHTTPException)
    )


@app.exception_handler(404)
async def handle_not_found(request: Request, exception: Exception) -> Response:
    if is_api_or_file_route(request, exception):
        return await http_exception_handler(request, exception)
    with Client(ui.page(''), request=request) as client:
        not_found_page()
    return client.build_response(request, 404)
