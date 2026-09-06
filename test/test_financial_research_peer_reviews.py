from __future__ import annotations

import unittest
from datetime import date

from financial_research.contracts import DocumentSnapshot, FilingDocument, FilingMetadata
from financial_research.peer_reviews import outlier_spec, review_peer_outlier_filing


def filing(cik: str, accession: str) -> FilingMetadata:
    return FilingMetadata(
        cik=cik,
        accession_number=accession,
        form="10-Q",
        filed_on=date(2026, 8, 5),
        report_period_end=date(2026, 6, 30),
        accepted_at=None,
        primary_document="filing.htm",
        primary_document_description="10-Q",
        is_amendment=False,
        is_inline_xbrl=True,
        sec_index_url="https://www.sec.gov/filing-index",
    )


def snapshot(metadata: FilingMetadata, text: str) -> DocumentSnapshot:
    document = FilingDocument(
        cik=metadata.cik,
        accession_number=metadata.accession_number,
        sequence=1,
        description="10-Q",
        document_name="filing.htm",
        document_type="10-Q",
        size_bytes=len(text),
        category="primary",
        sec_url="https://www.sec.gov/Archives/edgar/data/example/filing.htm",
    )
    return DocumentSnapshot(document, "text/html", "a" * 64, len(text), text)


class PeerOutlierReviewTests(unittest.TestCase):
    def test_complete_review_preserves_metric_specific_gate(self):
        spec = outlier_spec("0001794669")
        metadata = filing(spec.cik, spec.accession_number)
        text = """
        Gross revenue increased by $329 million, or 34%. The increase in volume of
        $11 billion, or 22%, was supported by our recent acquisitions.
        TFS revenue increased by $117 million. TFS revenue is the result of the
        acquisition of Global Blue. Gross revenue less network fees increased by
        $211 million, or 51%, primarily due to the impact of recent acquisitions.
        """

        review = review_peer_outlier_filing(metadata, (snapshot(metadata, text),), spec=spec)

        self.assertEqual(review.review_status, "complete")
        self.assertEqual(review.gates[0].metric, "revenue_growth_yoy")
        self.assertEqual(review.gates[0].status, "direction_only")
        self.assertFalse(review.publication_allowed)
        self.assertTrue(all(item.source_url.startswith("https://www.sec.gov/") for item in review.findings))

    def test_missing_evidence_blocks_gate_and_clears_evidence_links(self):
        spec = outlier_spec("0001512673")
        metadata = filing(spec.cik, spec.accession_number)

        review = review_peer_outlier_filing(
            metadata,
            (snapshot(metadata, "No matching disclosure."),),
            spec=spec,
        )

        self.assertEqual(review.review_status, "incomplete")
        self.assertTrue(review.missing_evidence_ids)
        self.assertTrue(all(gate.status == "blocked" for gate in review.gates))
        self.assertTrue(all(not gate.evidence_ids for gate in review.gates))

    def test_wrong_accession_never_completes_even_when_text_matches(self):
        spec = outlier_spec("0001794669")
        metadata = filing(spec.cik, "0000000000-26-000001")
        text = """
        Gross revenue increased by $329 million, or 34%. The increase in volume of
        $11 billion, or 22%, included recent acquisitions. TFS revenue increased by
        $117 million and was the result of the acquisition of Global Blue. Gross
        revenue less network fees increased by $211 million, or 51%, due to the
        impact of recent acquisitions.
        """

        review = review_peer_outlier_filing(metadata, (snapshot(metadata, text),), spec=spec)

        self.assertEqual(review.review_status, "incomplete")
        self.assertIn("filing_identity", review.missing_evidence_ids)
        self.assertFalse(review.publication_allowed)


if __name__ == "__main__":
    unittest.main()
