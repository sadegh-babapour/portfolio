import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from nicegui import app as nicegui_app

import app.main as web_main
from app.content import ContentValidationError, load_projects, load_resume_timeline
from poller import poll_calgary_gtfs_rt_current as current_poller


class WebBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        web_main._import_pages()

    def test_public_portfolio_and_react_mounts_are_registered(self):
        route_paths = {getattr(route, "path", None) for route in nicegui_app.routes}

        self.assertTrue(
            {
                "/",
                "/about",
                "/resume",
                "/projects",
                "/contact",
                "/dashboard",
                "/blog",
                "/blog/{slug}",
                "/account",
                "/privacy",
                "/terms",
                "/admin",
                "/admin/blog",
            }
            <= route_paths
        )
        self.assertIn("/resume/document.pdf", route_paths)
        self.assertIn("/calgary-transit-live", route_paths)
        self.assertTrue(
            {
                "/api/auth/google/login",
                "/api/auth/google/callback",
                "/api/auth/session",
                "/api/auth/logout",
                "/api/auth/account",
                "/api/auth/favorite-stops",
                "/api/auth/favorite-stops/{stop_id}",
                "/api/admin/summary",
                "/api/admin/blog/posts",
                "/api/admin/blog/posts/{post_id}",
                "/api/admin/blog/preview",
                "/sitemap.xml",
                "/robots.txt",
            }
            <= route_paths
        )

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

    def test_contact_turnstile_executes_only_after_submit(self):
        source = (
            Path(__file__).resolve().parents[1] / "app" / "pages" / "contact.py"
        ).read_text(encoding="utf-8")

        self.assertIn("execution: 'execute'", source)
        self.assertIn("appearance: 'interaction-only'", source)
        self.assertIn("window.turnstile.execute(widgetId)", source)
        self.assertNotIn("window.turnstile.getResponse", source)

    def test_account_page_uses_reviewed_deletion_requests(self):
        account_source = (
            Path(__file__).resolve().parents[1] / "app" / "pages" / "account.py"
        ).read_text(encoding="utf-8")
        api_source = (
            Path(__file__).resolve().parents[1] / "app" / "auth" / "api.py"
        ).read_text(encoding="utf-8")

        self.assertIn("/contact?topic=account-deletion", account_source)
        self.assertNotIn("portfolio-delete-account", account_source)
        self.assertIn("status_code=409", api_source)
        self.assertNotIn("delete_account(user)", api_source)


class CurrentPollerBoundaryTests(unittest.TestCase):
    def test_run_once_updates_and_commits_each_feed_independently(self):
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
        self.assertEqual(connection.commit.call_count, 3)
        connection.rollback.assert_not_called()

    def test_run_once_keeps_other_feeds_when_one_feed_fails(self):
        with (
            patch.object(
                current_poller,
                "upsert_vehicle_positions",
                side_effect=ValueError("invalid protobuf"),
            ),
            patch.object(current_poller, "upsert_trip_updates"),
            patch.object(current_poller, "upsert_alerts"),
        ):
            connection = Mock()
            current_poller.run_once(connection)

        connection.rollback.assert_called_once_with()
        self.assertEqual(connection.commit.call_count, 2)

    def test_boolean_environment_flags_use_explicit_truthy_values(self):
        with patch.dict(os.environ, {"TEST_FLAG": "yes"}):
            self.assertTrue(current_poller.env_bool("TEST_FLAG", False))
        with patch.dict(os.environ, {"TEST_FLAG": "off"}):
            self.assertFalse(current_poller.env_bool("TEST_FLAG", True))
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(current_poller.env_bool("TEST_FLAG", True))


class PortfolioContentTests(unittest.TestCase):
    def test_committed_timeline_and_projects_pass_validation(self):
        timeline = load_resume_timeline()
        projects = load_projects()

        self.assertGreaterEqual(len(timeline.entries), 1)
        self.assertEqual(len({entry.id for entry in timeline.entries}), len(timeline.entries))
        self.assertGreaterEqual(len(projects.projects), 2)
        self.assertTrue(any(project.data_mode == "live_database" for project in projects.projects))
        self.assertTrue(any(project.data_mode == "static_snapshot" for project in projects.projects))
        self.assertTrue(any(project.lab is not None for project in projects.projects))

    def test_public_branding_and_project_disclosure_are_deliberate(self):
        root = Path(__file__).resolve().parents[1]
        home_source = (root / "app" / "pages" / "home.py").read_text(encoding="utf-8")
        navbar_source = (root / "app" / "components" / "navbar.py").read_text(
            encoding="utf-8"
        )
        projects_source = (root / "app" / "pages" / "projects.py").read_text(
            encoding="utf-8"
        )
        collection = load_projects()
        lab = next(project.lab for project in collection.projects if project.lab is not None)

        self.assertIn("What Bizqlab does", home_source)
        self.assertIn("How account data is used", home_source)
        self.assertIn("https://www.bizqlab.com/", home_source)
        self.assertIn("/static/bizqlab_logo.png", home_source)
        self.assertIn('"logo": "https://www.bizqlab.com/static/bizqlab_logo.png"', home_source)
        self.assertIn("[*NAV_LINKS, ACCOUNT_LINK]", navbar_source)
        self.assertIn("[ACCOUNT_LINK, *NAV_LINKS]", navbar_source)
        self.assertIn("portfolio-development-note", projects_source)
        self.assertEqual(
            lab.working_method,
            "Codex was used as an AI-assisted development tool. The portfolio owner "
            "reviewed and validated the resulting work.",
        )

    def test_duplicate_timeline_ids_are_rejected(self):
        document = {
            "schema_version": 1,
            "heading": "Timeline",
            "intro": "Test timeline",
            "entries": [self._timeline_entry("duplicate"), self._timeline_entry("duplicate")],
        }
        path = self._temporary_json(document)
        self.addCleanup(path.unlink)

        with self.assertRaisesRegex(ContentValidationError, "duplicate ids"):
            load_resume_timeline(path)

    def test_unsafe_project_links_are_rejected(self):
        document = json.loads(
            (Path(__file__).resolve().parents[1] / "content" / "projects.json").read_text(
                encoding="utf-8"
            )
        )
        document["projects"][0]["links"][0]["url"] = "javascript:alert(1)"
        path = self._temporary_json(document)
        self.addCleanup(path.unlink)

        with self.assertRaisesRegex(ContentValidationError, "root-relative or HTTPS"):
            load_projects(path)

    @staticmethod
    def _timeline_entry(entry_id):
        return {
            "id": entry_id,
            "period": "2026",
            "title": "Role",
            "organization": "Organization",
            "kind": "work",
            "summary": "Summary",
            "highlights": [],
            "skills": [],
            "icon": "work",
            "color": "blue",
        }

    @staticmethod
    def _temporary_json(document):
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        with handle:
            json.dump(document, handle)
        return Path(handle.name)


if __name__ == "__main__":
    unittest.main()
