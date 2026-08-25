import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.admin.config import AnalyticsSettings
from app.admin.models import PageViewEvent
from app.admin.service import (
    TRACKED_PAGE_PATHS,
    classify_transit_health,
    require_admin,
    tracked_page_path,
)


class AnonymousAnalyticsBoundaryTests(unittest.TestCase):
    def test_event_contains_only_route_time_and_database_identifier(self):
        self.assertEqual(
            set(PageViewEvent.__table__.columns.keys()),
            {"id", "path", "created_at"},
        )
        self.assertEqual(PageViewEvent.__table__.schema, "portfolio")

    def test_only_exact_deliberate_html_paths_are_tracked(self):
        self.assertEqual(tracked_page_path("/projects"), "/projects")
        self.assertEqual(
            tracked_page_path("/calgary-transit-live/"),
            "/calgary-transit-live/",
        )
        for rejected in (
            "/admin",
            "/api/auth/session",
            "/static/bizqlab_logo.png",
            "/projects?campaign=private",
            "/unknown",
        ):
            self.assertIsNone(tracked_page_path(rejected))
        self.assertNotIn("/admin", TRACKED_PAGE_PATHS)

    def test_retention_is_bounded_and_invalid_values_use_default(self):
        with patch.dict(os.environ, {"ANALYTICS_RETENTION_DAYS": "30"}):
            self.assertEqual(AnalyticsSettings.from_env().retention_days, 30)
        for invalid in ("0", "366", "not-a-number"):
            with self.subTest(invalid=invalid), patch.dict(
                os.environ, {"ANALYTICS_RETENTION_DAYS": invalid}
            ):
                self.assertEqual(AnalyticsSettings.from_env().retention_days, 90)


class AdminAuthorizationTests(unittest.TestCase):
    def test_guest_and_registered_user_are_rejected(self):
        with patch("app.admin.service.current_session", return_value=None):
            with self.assertRaises(HTTPException) as guest_error:
                require_admin(None)
        self.assertEqual(guest_error.exception.status_code, 403)

        registered = SimpleNamespace(roles=frozenset({"registered"}))
        with patch("app.admin.service.current_session", return_value=registered):
            with self.assertRaises(HTTPException) as member_error:
                require_admin("session")
        self.assertEqual(member_error.exception.status_code, 403)

    def test_admin_is_accepted(self):
        owner = SimpleNamespace(roles=frozenset({"registered", "admin"}))
        with patch("app.admin.service.current_session", return_value=owner):
            self.assertIs(require_admin("session"), owner)


class TransitHealthTests(unittest.TestCase):
    def test_health_uses_same_operating_window_freshness_boundary_as_api(self):
        self.assertEqual(classify_transit_health(False, 999, 0), "outside_operating_hours")
        self.assertEqual(classify_transit_health(True, 180, 1), "healthy")
        self.assertEqual(classify_transit_health(True, 181, 1), "degraded")
        self.assertEqual(classify_transit_health(True, 10, 0), "degraded")
        self.assertEqual(classify_transit_health(True, None, 5), "degraded")
