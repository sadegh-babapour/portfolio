"""The site's 404 page replaces NiceGUI's default, but API and file routes keep JSON 404s."""
import asyncio
import json
import unittest
from pathlib import Path

from fastapi import HTTPException
from nicegui import app
from starlette.requests import Request

from app.pages import not_found


def request(**scope) -> Request:
    return Request({"type": "http", "method": "GET", "path": "/x", "headers": [], **scope})


def an_endpoint():
    return None


class NotFoundRoutingTests(unittest.TestCase):
    def test_it_replaces_nicegui_s_default_404_handler(self):
        self.assertIs(app.exception_handlers[404], not_found.handle_not_found)

    def test_an_unknown_path_gets_the_page(self):
        # No route matched, so Starlette never set an endpoint.
        self.assertFalse(not_found.is_api_or_file_route(request(), HTTPException(404)))

    def test_a_nicegui_page_or_the_mounted_app_gets_the_page(self):
        page = request(endpoint=an_endpoint, nicegui_page_path="/resume")
        self.assertFalse(not_found.is_api_or_file_route(page, HTTPException(404)))
        self.assertFalse(not_found.is_api_or_file_route(request(endpoint=app), HTTPException(404)))

    def test_an_api_or_file_route_that_raises_404_keeps_its_json_answer(self):
        api = request(endpoint=an_endpoint)
        exception = HTTPException(404, detail="Resume PDF is not available")
        self.assertTrue(not_found.is_api_or_file_route(api, exception))
        response = asyncio.run(not_found.handle_not_found(api, exception))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(json.loads(response.body), {"detail": "Resume PDF is not available"})

    def test_the_page_never_echoes_the_exception_or_the_path(self):
        source = Path(not_found.__file__).read_text(encoding="utf-8")
        body = source.split("def not_found_content", 1)[1].split("def is_api_or_file_route", 1)[0]
        self.assertNotIn("exception", body)
        self.assertNotIn("request", body)


if __name__ == "__main__":
    unittest.main()
