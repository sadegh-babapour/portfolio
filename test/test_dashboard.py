import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.dashboard.service import build_live_transit_analysis, load_cached_analysis


class DashboardPresentationTests(unittest.TestCase):
    def test_chart_animation_waits_for_the_viewport(self):
        source = (
            Path(__file__).resolve().parents[1] / "app" / "components" / "charts.py"
        ).read_text(encoding="utf-8")

        self.assertIn('initial_options["animation"] = False', source)
        self.assertIn("IntersectionObserver", source)
        self.assertIn("prefers-reduced-motion", source)


class CachedDashboardTests(unittest.TestCase):
    def test_snapshot_contract_reports_rows_and_empty_tables(self):
        document = {
            "cache_date": "2026-08-24",
            "last_updated": "2026-08-24T12:00:00Z",
            "data": {
                "daily_stats": [{"date": "2026-08-24"}],
                "membership_summary": [{"period_date": "2026-08-24"}],
                "revenue_summary": [{"date": "2026-08-24"}],
                "member_visits": [],
            },
        }
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        with handle:
            json.dump(document, handle)
        path = Path(handle.name)
        self.addCleanup(path.unlink)

        snapshot = load_cached_analysis(path)

        self.assertFalse(snapshot["available"])
        self.assertEqual(snapshot["row_count"], 3)
        self.assertEqual(snapshot["quality"][-1]["status"], "empty")


class LiveTransitDashboardTests(unittest.TestCase):
    def test_live_analysis_is_aggregate_and_bounded(self):
        now = datetime(2026, 8, 24, 18, 0, tzinfo=timezone.utc)
        database = MagicMock()
        overview_result = MagicMock()
        overview_result.mappings.return_value.one.return_value = {
            "generated_at": now,
            "recent_vehicles": 10,
            "active_routes": 4,
            "route_matched_vehicles": 9,
            "latest_vehicle_timestamp": now,
            "latest_trip_update_timestamp": now,
            "latest_alert_timestamp": now,
            "retained_observations": 120,
        }
        mode_result = MagicMock()
        mode_result.all.return_value = [("bus", 8), ("brt", 2)]
        route_result = MagicMock()
        route_result.all.return_value = [("23", 3)]
        cadence_result = MagicMock()
        cadence_result.all.return_value = [(now, 10, 9)]
        database.execute.side_effect = [
            MagicMock(),
            overview_result,
            mode_result,
            route_result,
            cadence_result,
        ]
        context = MagicMock()
        context.__enter__.return_value = database
        context.__exit__.return_value = False

        with (
            patch("app.dashboard.service.session_scope", return_value=context),
            patch("app.dashboard.service._LIVE_CACHE_VALUE", None),
            patch("app.dashboard.service._LIVE_CACHE_EXPIRES_AT", 0.0),
        ):
            summary = build_live_transit_analysis()

        self.assertTrue(summary["available"])
        self.assertEqual(summary["route_match_percent"], 90.0)
        self.assertEqual(summary["top_routes"], [{"route": "23", "vehicles": 3}])
        self.assertNotIn("vehicle_id", json.dumps(summary, default=str))
        sql = "\n".join(str(call.args[0]) for call in database.execute.call_args_list)
        self.assertIn("interval '3 minutes'", sql)
        self.assertIn("interval '15 minutes'", sql)
        self.assertIn("limit 10", sql.lower())
        self.assertIn("statement_timeout", sql)


if __name__ == "__main__":
    unittest.main()
