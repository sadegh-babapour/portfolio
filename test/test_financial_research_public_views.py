from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from financial_research.public_views import (
    PUBLIC_DIRECTORY_VERSION,
    REVIEWED_PAYMENT_FILINGS,
    load_public_filing_directory,
)
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


if __name__ == "__main__":
    unittest.main()
