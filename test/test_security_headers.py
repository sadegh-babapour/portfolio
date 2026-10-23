"""Security headers on every response, and replacing the résumé PDF safely."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import security_headers
from app.resume import document
from app.resume.document import ResumePdfError, replace_resume_pdf, validate_pdf


PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


class SecurityHeaderTests(unittest.TestCase):
    def test_every_response_gets_the_headers(self):
        api = FastAPI()
        api.middleware("http")(security_headers.add_security_headers)
        api.get("/x")(lambda: {"ok": True})
        response = TestClient(api).get("/x")
        for name, value in security_headers.SECURITY_HEADERS.items():
            self.assertEqual(response.headers[name], value)

    def test_the_transit_map_keeps_geolocation_and_the_site_can_frame_itself(self):
        headers = security_headers.SECURITY_HEADERS
        self.assertIn("geolocation=(self)", headers["Permissions-Policy"])
        self.assertEqual(headers["X-Frame-Options"], "SAMEORIGIN")


class ResumePdfTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.target = Path(self.directory.name) / "data" / "resume.pdf"
        patcher = patch.dict(os.environ, {"RESUME_PDF_PATH": str(self.target)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_pdf_replaces_the_file_and_leaves_no_temporary_files(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(b"%PDF-old\n%%EOF")
        replace_resume_pdf(PDF)
        self.assertEqual(self.target.read_bytes(), PDF)
        self.assertEqual([p.name for p in self.target.parent.iterdir()], ["resume.pdf"])

    def test_non_pdfs_empty_and_oversized_files_are_refused(self):
        for data, message in (
            (b"", "empty"),
            (b"<html>%%EOF", "not a PDF"),
            (b"%PDF-1.7 no end marker", "not a PDF"),
            (b"%PDF-" + b"0" * document.MAX_PDF_BYTES + b"%%EOF", "5 MB"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ResumePdfError, message):
                validate_pdf(data)
        self.assertFalse(self.target.exists())

    def test_the_version_changes_when_the_file_is_replaced(self):
        self.assertEqual(document.resume_pdf_version(), "0")
        replace_resume_pdf(PDF)
        os.utime(self.target, (1_700_000_000, 1_700_000_000))
        self.assertEqual(document.resume_pdf_version(), "1700000000")


if __name__ == "__main__":
    unittest.main()
