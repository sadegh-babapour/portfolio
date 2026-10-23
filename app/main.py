# Entry point (and the NiceGUI reload worker): resolve the runtime before any app
# import or configuration read. A refusal exits before serving or connecting. No
# dotenv discovery: development settings come only from the strict root profile.
# Imported without this block (tests, a bare ASGI import), database access raises
# runtime_not_bootstrapped.
if __name__ in {"__main__", "__mp_main__"}:
    from app.runtime_state import bootstrap_entry_point

    bootstrap_entry_point("web")

from fastapi import HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from nicegui import app as fastapi_app
from nicegui import ui
import logging
import os
from pathlib import Path

import app.contact.api  # noqa: F401,E402
import app.auth.api  # noqa: F401,E402
import app.admin.api  # noqa: F401,E402
import app.blog.api  # noqa: F401,E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

# ── static mounts ─────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / 'static'
TRANSIT_FRONTEND_DIR = REPO_ROOT / 'frontend' / 'dist'
DEFAULT_RESUME_PDF = REPO_ROOT / 'static' / 'resume.pdf'

fastapi_app.mount('/static', StaticFiles(directory=STATIC_DIR), name='static')
if TRANSIT_FRONTEND_DIR.is_dir():
    fastapi_app.mount(
        '/calgary-transit-live',
        StaticFiles(directory=TRANSIT_FRONTEND_DIR, html=True),
        name='calgary-transit-live',
    )
else:
    logging.getLogger(__name__).warning(
        'React transit build not found at %s; run npm run build in frontend/',
        TRANSIT_FRONTEND_DIR,
    )


@fastapi_app.get('/resume/document.pdf', include_in_schema=False)
async def resume_document(download: bool = False):
    configured_path = os.getenv('RESUME_PDF_PATH')
    pdf_path = Path(configured_path) if configured_path else DEFAULT_RESUME_PDF
    if not pdf_path.is_absolute():
        pdf_path = REPO_ROOT / pdf_path

    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail='Resume PDF is not available')

    disposition = 'attachment' if download else 'inline'
    return FileResponse(
        pdf_path,
        media_type='application/pdf',
        headers={
            'Content-Disposition': f'{disposition}; filename="resume.pdf"',
            'Cache-Control': 'public, max-age=3600',
        },
    )

# Financial Research was retired on 2026-10-21; old links and search results land on
# the projects page instead of a 404.
@fastapi_app.get('/research/financials', include_in_schema=False)
@fastapi_app.get('/research/financials/{rest:path}', include_in_schema=False)
async def retired_financial_research(rest: str = ''):
    return RedirectResponse('/projects', status_code=301)

# About was folded into the home page on 2026-10-23.
@fastapi_app.get('/about', include_in_schema=False)
async def retired_about():
    return RedirectResponse('/', status_code=301)

# ── pages ─────────────────────────────────────────────────────────
def _import_pages():
    import app.pages.contact  # noqa: F401
    import app.pages.dashboard  # noqa: F401
    import app.pages.markets  # noqa: F401
    import app.pages.home  # noqa: F401
    import app.pages.projects  # noqa: F401
    import app.pages.resume  # noqa: F401
    import app.pages.legal  # noqa: F401
    import app.pages.account  # noqa: F401
    import app.pages.admin  # noqa: F401
    import app.pages.blog  # noqa: F401
    import app.pages.admin_blog  # noqa: F401
    import app.pages.admin_resume  # noqa: F401


# ── run ───────────────────────────────────────────────────────────
if __name__ in {"__main__", "__mp_main__"}:
    _import_pages()
    ui.run(
        title='Bizqlab',
        favicon=str(STATIC_DIR / 'bizqlab_logo.png'),
        port=int(os.getenv("PORT", default=8086)),
        host='0.0.0.0',
        dark=False,
    )
