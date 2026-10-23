"""The résumé PDF: where it lives and how an admin replaces it."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESUME_PDF = REPO_ROOT / "static" / "resume.pdf"
MAX_PDF_BYTES = 5 * 1024 * 1024


class ResumePdfError(ValueError):
    pass


def resume_pdf_path() -> Path:
    """RESUME_PDF_PATH (the Railway volume in production) or the ignored local copy."""
    configured = os.getenv("RESUME_PDF_PATH")
    path = Path(configured) if configured else DEFAULT_RESUME_PDF
    return path if path.is_absolute() else REPO_ROOT / path


def resume_pdf_version() -> str:
    """Changes whenever the file is replaced, so browsers and Cloudflare fetch the new one."""
    try:
        return str(int(resume_pdf_path().stat().st_mtime))
    except OSError:
        return "0"


def validate_pdf(data: bytes) -> None:
    if not data:
        raise ResumePdfError("The file is empty")
    if len(data) > MAX_PDF_BYTES:
        raise ResumePdfError("The PDF must be 5 MB or smaller")
    if not data.startswith(b"%PDF-") or b"%%EOF" not in data[-2048:]:
        raise ResumePdfError("That file is not a PDF")


def replace_resume_pdf(data: bytes) -> Path:
    """Write the new PDF beside the old one, then swap it in, so readers never see half a file."""
    validate_pdf(data)
    target = resume_pdf_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=target.parent, prefix=".resume-", suffix=".pdf")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return target
