import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from nicegui import app as nicegui_app

import app.main as web_main
from app.financial_research.service import (
    SNAPSHOT_PATH,
    find_company_research,
    load_public_research,
    prepare_reviewed_publication_candidate,
)
from financial_research.automation import CompanyRefresh, RefreshAttempt, RefreshReport


class FinancialResearchPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        web_main._import_pages()

    def test_reviewed_paypal_snapshot_passes_publication_contract(self):
        research = load_public_research()

        self.assertTrue(research["available"])
        self.assertEqual(research["schema_version"], "financial-publication-2026-09-06.2")
        self.assertEqual(len(research["companies"]), 1)
        paypal = research["companies"][0]
        self.assertEqual(paypal["slug"], "paypal")
        self.assertEqual(paypal["period_end"], "2026-06-30")
        self.assertEqual(paypal["accession_number"], "0001633917-26-000082")
        self.assertEqual(len(paypal["metrics"]), 6)
        self.assertEqual(len(paypal["quarter_history"]), 18)
        self.assertEqual(paypal["quarter_history"][0]["period_end"], "2022-03-31")
        self.assertEqual(paypal["quarter_history"][-1]["period_end"], "2026-06-30")
        self.assertEqual(
            paypal["quarter_history"][5]["simplified_free_cash_flow_billions"],
            -0.350,
        )
        self.assertEqual(
            {item["key"] for item in paypal["metrics"]},
            {
                "revenue",
                "operating_margin",
                "net_income",
                "simplified_free_cash_flow",
                "working_capital",
                "diluted_shares",
            },
        )
        self.assertEqual(find_company_research("paypal"), paypal)
        self.assertIsNone(find_company_research("not-published"))

    def test_every_published_evidence_link_is_an_sec_archive_url(self):
        paypal = load_public_research()["companies"][0]
        urls = [paypal["filing_index_url"], paypal["primary_document_url"]]
        urls.extend(item["source_url"] for item in paypal["metrics"])
        urls.extend(item["source_url"] for item in paypal["supporting_evidence"])
        urls.extend(item["source_url"] for item in paypal["contrary_evidence"])
        urls.extend(item["source_url"] for item in paypal["quarter_history"])
        for event in paypal["historical_events"]:
            urls.append(event["source_url"])
            urls.extend(item["source_url"] for item in event["relationships"])

        self.assertTrue(urls)
        self.assertTrue(
            all(url.startswith("https://www.sec.gov/Archives/edgar/data/") for url in urls)
        )

    def test_invalid_or_missing_snapshot_degrades_without_partial_data(self):
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        with handle:
            json.dump(
                {
                    "schema_version": "test",
                    "generated_at": "2026-09-06T00:00:00Z",
                    "companies": [
                        {
                            "slug": "unsafe",
                            "company_name": "Unsafe",
                            "ticker": "BAD",
                            "cik": "1",
                            "form": "10-Q",
                            "period_end": "2026-06-30",
                            "filed_on": "2026-07-01",
                            "headline": "Unsafe source",
                            "summary": "This must not be published.",
                            "filing_index_url": "https://example.com/not-sec",
                            "primary_document_url": "https://example.com/not-sec",
                            "metrics": [],
                            "charts": {},
                            "supporting_evidence": [],
                            "contrary_evidence": [],
                            "unknowns": [],
                            "relationships": [],
                            "quality_notes": [],
                        }
                    ],
                },
                handle,
            )
        path = Path(handle.name)
        self.addCleanup(path.unlink)

        invalid = load_public_research(path)
        missing = load_public_research(path.with_name("does-not-exist.json"))

        self.assertFalse(invalid["available"])
        self.assertEqual(invalid["companies"], [])
        self.assertFalse(missing["available"])
        self.assertEqual(missing["companies"], [])

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
        self.assertIn("All 18 normalized quarters", page_source)
        self.assertIn("Quarterly revenue", page_source)
        self.assertIn("Profitability range", page_source)
        self.assertIn("Cash generation history", page_source)
        self.assertIn("Financial position and share count", page_source)
        self.assertIn("View all 18 quarterly values", page_source)
        self.assertIn("Supporting evidence", page_source)
        self.assertIn("Contrary evidence", page_source)
        self.assertIn("What remains unknown about the latest quarter", page_source)
        self.assertIn("Historical filings and material structures", page_source)
        self.assertIn("temporarily unavailable", page_source)
        self.assertIn("Coverage indicates mapped SEC concepts", page_source)
        self.assertIn("Blocked magnitudes are hidden", page_source)
        self.assertIn("No rankings or cohorts", page_source)

    def test_historical_legal_roles_are_not_presented_as_current_quarter_causes(self):
        paypal = load_public_research()["companies"][0]
        current_evidence = json.dumps(
            paypal["supporting_evidence"] + paypal["contrary_evidence"]
        )
        historical = paypal["historical_events"][0]

        self.assertNotIn("Freshfields", current_evidence)
        self.assertEqual(historical["date"], "2023-06-20")
        self.assertIn("does not establish", historical["current_relevance"])
        self.assertTrue(
            any(
                relationship["entity"] == "Freshfields Bruckhaus Deringer LLP"
                and relationship["role"] == "Legal adviser to PayPal"
                for relationship in historical["relationships"]
            )
        )

    def test_snapshot_is_a_deliberate_data_asset(self):
        self.assertTrue(SNAPSHOT_PATH.is_file())
        self.assertEqual(SNAPSHOT_PATH.name, "paypal_research_sheet.json")

    def test_completed_refresh_prepares_only_the_explicitly_approved_payload(self):
        now = datetime(2026, 9, 6, tzinfo=timezone.utc)
        attempt = RefreshAttempt(
            cik="0001633917",
            ticker="PYPL",
            attempt_number=1,
            status="completed",
            reason_code=None,
            retryable=False,
            ingestion_run_id=None,
            fact_count=1,
            filing_count=1,
            started_at=now,
            completed_at=now,
        )
        refresh = RefreshReport(
            cohort_key="test",
            trigger_kind="scheduled",
            status="completed",
            period_start=date(2022, 1, 1),
            started_at=now,
            completed_at=now,
            companies=(
                CompanyRefresh(
                    cik="0001633917",
                    ticker="PYPL",
                    status="completed",
                    attempts=(attempt,),
                ),
            ),
        )
        document = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))

        candidate = prepare_reviewed_publication_candidate(document, refresh)

        self.assertTrue(candidate.gate.ready_for_owner_approval)
        self.assertFalse(candidate.gate.publication_performed)
        self.assertEqual(candidate.gate.approved_ciks, ("0001633917",))

        document["companies"][0]["cik"] = "0001512673"
        blocked = prepare_reviewed_publication_candidate(document, refresh)
        self.assertFalse(blocked.gate.ready_for_owner_approval)
        self.assertFalse(blocked.gate.publication_performed)


if __name__ == "__main__":
    unittest.main()
