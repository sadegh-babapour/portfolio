import os
import unittest
from unittest.mock import Mock, patch

from nicegui import app as nicegui_app

import app.main as web_main
from poller import poll_calgary_gtfs_rt_current as current_poller


class WebBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        web_main._import_pages()

    def test_public_portfolio_and_react_mounts_are_registered(self):
        route_paths = {getattr(route, "path", None) for route in nicegui_app.routes}

        self.assertTrue(
            {"/", "/about", "/resume", "/projects", "/contact", "/dashboard"}
            <= route_paths
        )
        self.assertIn("/resume/document.pdf", route_paths)
        self.assertIn("/calgary-transit-live", route_paths)

    def test_legacy_transit_routes_are_not_registered(self):
        route_paths = {getattr(route, "path", None) for route in nicegui_app.routes}

        self.assertNotIn("/transit", route_paths)
        self.assertFalse(any(path and path.startswith("/api/poller") for path in route_paths))
        self.assertFalse(any(path and path.startswith("/api/debug") for path in route_paths))
        self.assertFalse(any(path and path.startswith("/api/lrt") for path in route_paths))

    def test_resume_path_defaults_to_the_ignored_static_document(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(web_main.DEFAULT_RESUME_PDF.name, "resume.pdf")
            self.assertEqual(web_main.DEFAULT_RESUME_PDF.parent.name, "static")


class CurrentPollerBoundaryTests(unittest.TestCase):
    def test_run_once_updates_all_three_feeds_then_commits(self):
        calls = []

        with (
            patch.object(
                current_poller,
                "upsert_vehicle_positions",
                side_effect=lambda conn: calls.append(("vehicles", conn)),
            ),
            patch.object(
                current_poller,
                "upsert_trip_updates",
                side_effect=lambda conn: calls.append(("trips", conn)),
            ),
            patch.object(
                current_poller,
                "upsert_alerts",
                side_effect=lambda conn: calls.append(("alerts", conn)),
            ),
        ):
            connection = Mock()
            current_poller.run_once(connection)

        self.assertEqual(
            calls,
            [
                ("vehicles", connection),
                ("trips", connection),
                ("alerts", connection),
            ],
        )
        connection.commit.assert_called_once_with()

    def test_boolean_environment_flags_use_explicit_truthy_values(self):
        with patch.dict(os.environ, {"TEST_FLAG": "yes"}):
            self.assertTrue(current_poller.env_bool("TEST_FLAG", False))
        with patch.dict(os.environ, {"TEST_FLAG": "off"}):
            self.assertFalse(current_poller.env_bool("TEST_FLAG", True))
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(current_poller.env_bool("TEST_FLAG", True))


if __name__ == "__main__":
    unittest.main()
