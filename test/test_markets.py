"""Canada rates page data: shaped from the dbt mart, read-only, and safe when it is missing."""
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from app.markets import service


def row(day, policy, gov_2y=None, gov_5y=None, gov_10y=None, usd_cad=None, corra=None):
    spread = None if gov_2y is None or gov_10y is None else round((gov_10y - gov_2y) * 100)
    return {"obs_date": day, "policy_rate": policy, "corra": corra, "gov_2y": gov_2y, "gov_5y": gov_5y,
            "gov_10y": gov_10y, "usd_cad": usd_cad, "spread_10y_2y_bps": spread}


ROWS = [
    row(date(2025, 1, 2), 3.25, 3.0, 3.1, 3.2, 1.40),
    row(date(2025, 1, 3), 3.25),  # a weekend-style row: policy rate only
    row(date(2025, 6, 4), 2.75, 2.6, 2.8, 3.1, 1.36),
    row(date(2026, 1, 5), 2.50, 3.4, 3.5, 3.3, 1.47),
]


class SummarizeTests(unittest.TestCase):
    def test_policy_decisions_are_the_days_the_rate_changed(self):
        decisions = service.summarize(ROWS)["decisions"]
        self.assertEqual([(d["date"], d["change_bps"], d["rate"]) for d in decisions],
                         [(date(2025, 6, 4), -50, 2.75), (date(2026, 1, 5), -25, 2.50)])

    def test_changes_on_the_year_use_the_units_people_quote(self):
        latest = service.summarize(ROWS)["latest"]
        self.assertEqual(latest["policy_rate"]["change_1y"], -75)        # bps
        self.assertEqual(latest["gov_10y"]["change_1y"], 10)             # bps
        self.assertEqual(latest["spread_10y_2y_bps"]["change_1y"], -30)  # bps of bps
        self.assertEqual(latest["usd_cad"]["change_1y"], 5.0)            # percent

    def test_no_value_a_year_earlier_means_no_change(self):
        latest = service.summarize(ROWS[2:])["latest"]
        self.assertIsNone(latest["policy_rate"]["change_1y"])

    def test_an_inverted_curve_is_named_and_compared_with_a_year_earlier(self):
        data = service.summarize(ROWS)
        self.assertEqual(data["curve_shape"], "inverted")
        self.assertEqual([c["tenor"] for c in data["curve"]], ["Overnight", "2-year", "5-year", "10-year"])
        self.assertEqual(data["curve_dates"], {"now": date(2026, 1, 5), "year_ago": date(2025, 1, 2)})
        self.assertEqual(data["curve"][1], {"tenor": "2-year", "years": 2, "now": 3.4, "year_ago": 3.0})

    def test_sparklines_hold_only_the_last_year(self):
        spark = service.summarize(ROWS)["latest"]["policy_rate"]["spark"]
        self.assertEqual(spark[0][0], "2025-06-04")

    def test_no_rows_is_not_available(self):
        self.assertEqual(service.summarize([]), {"available": False})


class QueryTests(unittest.TestCase):
    def test_reads_in_a_read_only_transaction_and_never_commits(self):
        database = MagicMock()
        mappings = database.execute.return_value.mappings.return_value
        mappings.__iter__.return_value = iter([])
        mappings.first.return_value = None
        scope = MagicMock()
        scope.__enter__.return_value = database
        with patch.object(service, "session_scope", return_value=scope):
            service._query()
        first = str(database.execute.call_args_list[0].args[0])
        self.assertEqual(first, "set transaction read only")
        database.commit.assert_not_called()
        database.rollback.assert_called_once()

    def test_a_missing_mart_shows_as_unavailable(self):
        with patch.object(service, "session_scope", side_effect=RuntimeError("relation does not exist")):
            with self.assertLogs(service.log, "WARNING") as logs:
                self.assertEqual(service._query(), {"available": False})
        self.assertNotIn("relation", " ".join(logs.output))


if __name__ == "__main__":
    unittest.main()
