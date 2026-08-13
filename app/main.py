from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from nicegui import app as fastapi_app
from nicegui import ui
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import app.contact.api  # noqa: F401,E402
import app.auth.api  # noqa: F401,E402

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

# ── pages ─────────────────────────────────────────────────────────
def _import_pages():
    import app.pages.about  # noqa: F401
    import app.pages.contact  # noqa: F401
    import app.pages.dashboard  # noqa: F401
    import app.pages.home  # noqa: F401
    import app.pages.projects  # noqa: F401
    import app.pages.resume  # noqa: F401
    import app.pages.legal  # noqa: F401
    import app.pages.account  # noqa: F401


# ── run ───────────────────────────────────────────────────────────
if __name__ in {"__main__", "__mp_main__"}:
    _import_pages()
    ui.run(
        title='Bizqlab',
        port=int(os.getenv("PORT", default=8086)),
        host='0.0.0.0',
        dark=False,
    )
