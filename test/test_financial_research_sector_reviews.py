from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import date

from financial_research.contracts import DocumentSnapshot, FilingDocument, FilingMetadata
from financial_research.sector_reviews import (
    SECTOR_FILING_SPECS,
    SectorEvidenceRule,
    SectorFilingReviewSpec,
    SectorMetricGateSpec,
    review_sector_filing,
)


class SectorFilingReviewTests(unittest.TestCase):
    def test_review_contract_covers_five_exact_filings_per_nonpayment_sector(self):
        self.assertEqual(len(SECTOR_FILING_SPECS), 25)
        self.assertEqual(len({spec.cik for spec in SECTOR_FILING_SPECS}), 25)
        self.assertEqual(len({spec.accession_number for spec in SECTOR_FILING_SPECS}), 25)
        sectors = {spec.industry_key for spec in SECTOR_FILING_SPECS}
        self.assertEqual(
            sectors,
            {"digital_advertising", "airlines", "energy", "connectivity", "brokerage"},
        )
        for sector in sectors:
            self.assertEqual(
                len([spec for spec in SECTOR_FILING_SPECS if spec.industry_key == sector]),
                5,
            )
        self.assertTrue(all(spec.report_period_end == "2026-06-30" for spec in SECTOR_FILING_SPECS))
        self.assertTrue(all(len(spec.source_sha256) == 64 for spec in SECTOR_FILING_SPECS))
        self.assertTrue(all(spec.rules for spec in SECTOR_FILING_SPECS))
        for spec in SECTOR_FILING_SPECS:
            evidence_ids = {rule.evidence_id for rule in spec.rules}
            self.assertTrue(
                all(set(gate.evidence_ids) <= evidence_ids for gate in spec.gates)
            )

    def test_complete_review_binds_identity_hash_evidence_and_gate(self):
        spec = SectorFilingReviewSpec(
            industry_key="test",
            cik="0000000001",
            ticker="TEST",
            accession_number="0000000001-26-000001",
            report_period_end="2026-06-30",
            primary_document="test.htm",
            source_sha256="a" * 64,
            rules=(
                SectorEvidenceRule(
                    "event", "acquisition", "An acquisition changed the base.", r"acquired Example"
                ),
            ),
            gates=(
                SectorMetricGateSpec(
                    "revenue_growth_yoy", "direction_only", "Keep direction only.", ("event",)
                ),
            ),
        )
        filing = FilingMetadata(
            cik=spec.cik,
            accession_number=spec.accession_number,
            form="10-Q",
            filed_on=date(2026, 8, 1),
            report_period_end=date(2026, 6, 30),
            accepted_at=None,
            primary_document=spec.primary_document,
            primary_document_description="10-Q",
            is_amendment=False,
            is_inline_xbrl=True,
            sec_index_url="https://www.sec.gov/Archives/edgar/data/1/index.htm",
        )
        document = FilingDocument(
            spec.cik,
            spec.accession_number,
            1,
            "10-Q",
            spec.primary_document,
            "10-Q",
            None,
            "primary",
            "https://www.sec.gov/Archives/edgar/data/1/test.htm",
        )
        snapshot = DocumentSnapshot(document, "text/html", "a" * 64, 30, "We acquired Example this quarter.")

        review = review_sector_filing(filing, (snapshot,), spec=spec)

        self.assertEqual(review.review_status, "complete")
        self.assertEqual(review.findings[0].evidence_id, "event")
        self.assertEqual(review.gates[0].status, "direction_only")
        self.assertTrue(review.publication_allowed)

        failed = review_sector_filing(
            replace(filing, accession_number="changed"), (snapshot,), spec=spec
        )
        self.assertEqual(failed.review_status, "incomplete")
        self.assertIn("filing_identity", failed.missing_evidence_ids)
        self.assertEqual(failed.gates[0].status, "blocked")
        self.assertFalse(failed.publication_allowed)


if __name__ == "__main__":
    unittest.main()
