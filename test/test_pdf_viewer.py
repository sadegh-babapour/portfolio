"""The only HTML sanitization exception is an escaped same-origin PDF template."""
import unittest
from unittest.mock import patch

from app.components.pdf_viewer import create_pdf_viewer


class PdfViewerTests(unittest.TestCase):
    def test_template_preserves_iframe_and_escapes_attributes(self):
        with patch('app.components.pdf_viewer.ui.html') as html:
            create_pdf_viewer('/resume/document.pdf?v="<unsafe>&')
        markup = html.call_args.args[0]
        self.assertFalse(html.call_args.kwargs['sanitize'])
        self.assertIn('<iframe src="/calgary-transit-live/pdf-viewer.html?file=', markup)
        self.assertIn('v=&quot;&lt;unsafe&gt;&amp;', markup)
        self.assertNotIn('<unsafe>', markup)
        self.assertIn('download=true', markup)

    def test_external_and_unsafe_urls_are_refused_before_rendering(self):
        for url in ('https://example.com/a.pdf', '//example.com/a.pdf', 'javascript:alert(1)',
                    '/\\example.com/a.pdf', '/a\n.pdf'):
            with self.subTest(url=url), patch('app.components.pdf_viewer.ui.html') as html:
                with self.assertRaises(ValueError):
                    create_pdf_viewer(url)
                html.assert_not_called()
