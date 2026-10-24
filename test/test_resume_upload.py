"""Exercise NiceGUI 3 file objects without a database or real résumé file."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from nicegui.elements.upload_files import LargeFileUpload, SmallFileUpload

from app.resume.document import MAX_PDF_BYTES, ResumePdfError
from app.resume.upload import save_uploaded_pdf

PDF = b'%PDF-1.7\nsynthetic\n%%EOF\n'


class UploadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.target = Path(self.directory.name) / 'resume.pdf'
        self.target.write_bytes(PDF)
        self.path_patch = patch('app.resume.document.resume_pdf_path', return_value=self.target)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.authorize = Mock()

    def file(self, data):
        return SmallFileUpload('../../untrusted.pdf', 'application/pdf', data)

    async def test_real_new_style_file_replaces_fixed_destination(self):
        replacement = PDF.replace(b'synthetic', b'new synthetic')
        self.assertEqual(await save_uploaded_pdf(self.file(replacement), self.authorize), self.target)
        self.assertEqual(self.target.read_bytes(), replacement)
        self.assertEqual(self.authorize.call_count, 2)
        self.assertEqual(list(self.target.parent.iterdir()), [self.target])

    async def test_real_spooled_file_at_exact_limit_is_accepted(self):
        source = self.target.parent / 'spooled-upload.pdf'
        payload = b'%PDF-1.7\n' + b' ' * (MAX_PDF_BYTES - 15) + b'%%EOF\n'
        self.assertEqual(len(payload), MAX_PDF_BYTES)
        source.write_bytes(payload)
        file = LargeFileUpload('synthetic.pdf', 'application/pdf', source)
        await save_uploaded_pdf(file, self.authorize)
        self.assertEqual(self.target.read_bytes(), payload)

    async def test_unauthorized_does_not_access_file(self):
        file = Mock()
        self.authorize.side_effect = PermissionError('not admin')
        with self.assertRaises(PermissionError):
            await save_uploaded_pdf(file, self.authorize)
        self.assertEqual(file.mock_calls, [])
        self.assertEqual(self.target.read_bytes(), PDF)

    async def test_expired_session_after_read_does_not_write(self):
        self.authorize.side_effect = [None, PermissionError('expired')]
        with self.assertRaises(PermissionError):
            await save_uploaded_pdf(self.file(PDF + b'changed'), self.authorize)
        self.assertEqual(self.target.read_bytes(), PDF)

    async def test_empty_invalid_and_oversized_preserve_existing_file(self):
        for data in (b'', b'not a PDF', b'%PDF-no end', b'x' * (MAX_PDF_BYTES + 1)):
            with self.subTest(size=len(data)), self.assertRaises(ResumePdfError):
                await save_uploaded_pdf(self.file(data), self.authorize)
            self.assertEqual(self.target.read_bytes(), PDF)

    async def test_reported_oversize_is_rejected_before_iteration(self):
        file = Mock()
        file.size.return_value = MAX_PDF_BYTES + 1
        with self.assertRaises(ResumePdfError):
            await save_uploaded_pdf(file, self.authorize)
        file.iterate.assert_not_called()

    async def test_stream_cannot_bypass_reported_size(self):
        file = Mock()
        file.size.return_value = 1
        async def chunks(**kwargs):
            self.assertEqual(kwargs['chunk_size'], 64 * 1024)
            yield b'x' * MAX_PDF_BYTES
            yield b'x'
            self.fail('must stop reading after crossing limit')
        file.iterate.side_effect = chunks
        with self.assertRaises(ResumePdfError):
            await save_uploaded_pdf(file, self.authorize)
        self.assertEqual(self.target.read_bytes(), PDF)

    async def test_stream_failure_preserves_existing_file(self):
        file = Mock()
        file.size.return_value = len(PDF)
        async def chunks(**_):
            yield PDF[:4]
            raise OSError('synthetic read failure')
        file.iterate.side_effect = chunks
        with self.assertRaises(OSError):
            await save_uploaded_pdf(file, self.authorize)
        self.assertEqual(self.target.read_bytes(), PDF)

    async def test_atomic_replace_failure_cleans_temporary_file(self):
        with patch('app.resume.document.os.replace', side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(OSError):
                await save_uploaded_pdf(self.file(PDF), self.authorize)
        self.assertEqual(self.target.read_bytes(), PDF)
        self.assertEqual(list(self.target.parent.iterdir()), [self.target])
