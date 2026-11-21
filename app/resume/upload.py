"""Read NiceGUI 3 uploads with a server-side bound before atomic PDF replacement."""
from collections.abc import Callable
from pathlib import Path

from nicegui.elements.upload_files import FileUpload

from app.resume.document import MAX_PDF_BYTES, ResumePdfError, replace_resume_pdf


async def save_uploaded_pdf(file: FileUpload, check_admin: Callable[[], None]) -> Path:
    # Re-check the session on every upload, before accessing any file metadata or bytes.
    check_admin()
    if file.size() > MAX_PDF_BYTES:
        raise ResumePdfError("The PDF must be 5 MB or smaller")
    data = bytearray()
    async for chunk in file.iterate(chunk_size=64 * 1024):
        # Do not trust a reported size: count actual bytes before adding each chunk.
        if len(data) + len(chunk) > MAX_PDF_BYTES:
            raise ResumePdfError("The PDF must be 5 MB or smaller")
        data.extend(chunk)
    check_admin()  # The session may have expired while the asynchronous stream was read.
    return replace_resume_pdf(bytes(data))
