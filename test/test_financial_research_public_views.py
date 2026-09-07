from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from financial_research.public_views import (
    PUBLIC_DIRECTORY_VERSION,
    REVIEWED_PAYMENT_FILINGS,
    load_public_filing_directory,
    load_public_sector_screen,
)
from financial_research.sector_reviews import SECTOR_FILING_SPECS
from financial_research.universe import CORE_RESEARCH_UNIVERSE


class PublicResearchViewTests(unittest.TestCase):
    def _filings(self):
        return {
            company.cik: SimpleNamespace(
                filer_cik=company.cik,
                base_form="10-Q",
                report_period_end=date(2026, 6, 30),
                filed_on=date(2026, 8, 1),
                accession_number=f"{company.cik}-26-000001",
                sec_index_url=(
                    "https://www.sec.gov/Archives/edgar/data/"
                    f"{int(company.cik)}/{company.cik}-26-000001-index.html"
                ),
            )
            for company in CORE_RESEARCH_UNIVERSE
        }

    def test_directory_requires_and_groups_all_thirty_exact_filers(self):
        filings = self._filings()
        coverage = {
            filing.accession_number: {"revenue", "net_income"}
            for filing in filings.values()
        }
        with (
            patch(
                "financial_research.public_views._latest_core_filings",
                return_value=filings,
            ),
            patch(
                "financial_research.public_views._coverage_by_accession",
                return_value=coverage,
            ),
        ):
            result = load_public_filing_directory(MagicMock())

        self.assertEqual(result["version"], PUBLIC_DIRECTORY_VERSION)
        self.assertEqual(result["company_count"], 30)
        self.assertEqual(len(result["industries"]), 6)
        companies = [
            company
            for industry in result["industries"]
            for company in industry["companies"]
        ]
        self.assertEqual(len(companies), 30)
        self.assertTrue(all(company["metric_count"] == 2 for company in companies))
        self.assertTrue(
            all(
                company["filing_index_url"].startswith(
                    "https://www.sec.gov/Archives/edgar/data/"
                )
                for company in companies
            )
        )

    def test_directory_fails_closed_if_one_core_filer_is_missing(self):
        filings = self._filings()
        filings.pop(CORE_RESEARCH_UNIVERSE[-1].cik)
        with patch(
            "financial_research.public_views._latest_core_filings",
            return_value=filings,
        ):
            with self.assertRaisesRegex(ValueError, "incomplete"):
                load_public_filing_directory(MagicMock())

    def test_directory_rejects_a_non_sec_filing_link(self):
        filings = self._filings()
        filings[CORE_RESEARCH_UNIVERSE[0].cik].sec_index_url = "https://example.com/file"
        with (
            patch(
                "financial_research.public_views._latest_core_filings",
                return_value=filings,
            ),
            patch(
                "financial_research.public_views._coverage_by_accession",
                return_value={},
            ),
        ):
            with self.assertRaisesRegex(ValueError, "SEC Archives"):
                load_public_filing_directory(MagicMock())

    def test_payment_comparison_is_bound_to_five_unique_exact_q2_filings(self):
        self.assertEqual(len(REVIEWED_PAYMENT_FILINGS), 5)
        self.assertEqual(len({item.cik for item in REVIEWED_PAYMENT_FILINGS}), 5)
        self.assertEqual(
            {item.period_end for item in REVIEWED_PAYMENT_FILINGS},
            {"2026-06-30"},
        )
        self.assertTrue(
            all(item.accession_number.startswith("00") for item in REVIEWED_PAYMENT_FILINGS)
        )

    def test_sector_screen_applies_review_gates_without_ranking(self):
        specs = {
            spec.cik: spec
            for spec in SECTOR_FILING_SPECS
            if spec.industry_key == "brokerage"
        }
        filings = {
            company.cik: SimpleNamespace(
                filer_cik=company.cik,
                base_form="10-Q",
                report_period_end=date(2026, 6, 30),
                accession_number=specs[company.cik].accession_number,
                sec_index_url="https://www.sec.gov/Archives/edgar/data/1/index.htm",
            )
            for company in CORE_RESEARCH_UNIVERSE
            if company.industry_key == "brokerage"
        }

        def payload(_report, filing):
            metrics = [
                {
                    "key": key,
                    "label": key.replace("_", " ").title(),
                    "display_value": "+1.00%",
                    "value": 1.0,
                    "unit": "%",
                    "state": "derived",
                    "confidence": "high",
                    "source_url": "https://www.sec.gov/Archives/edgar/data/1/file.htm",
                }
                for key in (
                    "revenue_growth_yoy",
                    "operating_margin_change_yoy",
                    "cash_conversion",
                    "diluted_share_change_yoy",
                )
            ]
            return {
                "period_end": "2026-06-30",
                "accession_number": filing.accession_number,
                "filing_index_url": filing.sec_index_url,
                "metrics": metrics,
            }

        database = MagicMock()
        database.scalars.return_value.all.return_value = []
        with (
            patch(
                "financial_research.public_views._latest_filings",
                return_value=filings,
            ),
            patch("financial_research.public_views.analyze_company_quarter"),
            patch(
                "financial_research.public_views._analysis_payload",
                side_effect=payload,
            ),
        ):
            result = load_public_sector_screen(database, "brokerage")

        self.assertEqual(len(result["companies"]), 5)
        self.assertTrue(result["same_period"])
        self.assertFalse(result["ranking_performed"])
        self.assertTrue(result["cohorts_assigned"])
        self.assertTrue(
            all(
                lens["value"] is None
                for company in result["companies"]
                for lens in company["lenses"]
                if lens["gate_status"] != "cleared"
            )
        )
        by_ticker = {company["ticker"]: company for company in result["companies"]}
        self.assertEqual(by_ticker["IBKR"]["cohort"], "improving_with_quality")
        self.assertTrue(by_ticker["IBKR"]["comparable"])
        self.assertEqual(by_ticker["COIN"]["cohort"], "not_comparable")
        self.assertFalse(by_ticker["COIN"]["comparable"])
        self.assertEqual(
            by_ticker["COIN"]["lenses"][0]["display_value"], "Up"
        )
        self.assertTrue(
            all(company["findings"] for company in result["companies"])
        )
        self.assertTrue(
            all(
                company["comparison_state"] == "reviewed_with_metric_gates"
                for company in result["companies"]
            )
        )

    def test_sector_screen_fails_closed_when_latest_identity_is_not_reviewed(self):
        company = next(
            item for item in CORE_RESEARCH_UNIVERSE if item.industry_key == "brokerage"
        )
        filings = {
            item.cik: SimpleNamespace(
                filer_cik=item.cik,
                report_period_end=date(2026, 6, 30),
                accession_number="changed-accession" if item.cik == company.cik else next(
                    spec.accession_number
                    for spec in SECTOR_FILING_SPECS
                    if spec.cik == item.cik
                ),
            )
            for item in CORE_RESEARCH_UNIVERSE
            if item.industry_key == "brokerage"
        }
        with patch(
            "financial_research.public_views._latest_filings", return_value=filings
        ):
            with self.assertRaisesRegex(ValueError, "identity changed"):
                load_public_sector_screen(MagicMock(), "brokerage")

    def test_payments_do_not_fall_through_to_unreviewed_sector_screen(self):
        self.assertIsNone(load_public_sector_screen(MagicMock(), "payments"))


if __name__ == "__main__":
    unittest.main()
