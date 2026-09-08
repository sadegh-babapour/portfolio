import unittest
from pathlib import Path

from nicegui import app as nicegui_app

import app.main as web_main


class FinancialResearchPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        web_main._import_pages()

    def test_routes_and_accessible_chart_fallbacks_are_present(self):
        route_paths = {getattr(route, "path", None) for route in nicegui_app.routes}
        self.assertIn("/research/financials", route_paths)
        self.assertIn("/research/financials/paypal", route_paths)
        self.assertIn("/research/financials/company/{ticker}", route_paths)
        self.assertIn("/research/financials/comparisons/payments", route_paths)
        self.assertIn("/research/financials/sectors/{industry_key}", route_paths)

        page_source = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "pages"
            / "financial_research.py"
        ).read_text(encoding="utf-8")
        self.assertIn("aria_label=", page_source)
        self.assertIn("Quarterly performance", page_source)
        self.assertIn("Revenue and operating margin", page_source)
        self.assertIn("Earnings and cash generation", page_source)
        self.assertIn("Diluted share-count trend", page_source)
        self.assertIn("Company spotlight · PayPal", page_source)
        self.assertIn("Compare the same fiscal quarter", page_source)
        self.assertIn("Q{quarter} across reporting years", page_source)
        self.assertIn("Quarter contribution by year", page_source)
        self.assertIn("Latest-quarter comparison", page_source)
        self.assertIn("Selected-cohort revenue mix", page_source)
        self.assertIn("Source filings", page_source)
        self.assertIn("temporarily unavailable", page_source)
        self.assertNotIn("Mapped concepts", page_source)
        self.assertNotIn("Recent filing coverage", page_source)
        self.assertNotIn("Supporting evidence", page_source)
        self.assertNotIn("Historical filings and material structures", page_source)
        self.assertNotIn("Reviewed comparison gates", page_source)
        self.assertNotIn("Comparison evidence map", page_source)

if __name__ == "__main__":
    unittest.main()
