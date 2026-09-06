from __future__ import annotations

import unittest
import uuid
from datetime import date, datetime, timezone
from unittest.mock import Mock

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from financial_research.contracts import DocumentSnapshot, FilingDocument, FilingMetadata
from financial_research.documents import (
    FilingResearchBundle,
    build_paypal_bnpl_claims,
    extract_entity_roles,
    extract_filing_sections,
    extract_change_explanation_claims,
    extract_instance_facts,
    html_to_text,
    parse_filing_index,
)
from financial_research.document_store import persist_filing_research
from financial_research.edgar import EdgarClient, EdgarResponseError
from financial_research.models import (
    ResearchClaim,
    ResearchDocument,
    ResearchDocumentEntityRole,
    ResearchEntity,
    ResearchFiler,
    ResearchFiling,
    ResearchIngestionRun,
    ResearchOpenQuestion,
    ResearchTextEvidence,
)
from financial_research.queries import (
    entity_role_history,
    filing_text_evidence,
    open_research_questions,
)


ACCESSION = "0001633917-26-000082"
CIK = "0001633917"
INDEX_HTML = """
<table class="tableFile" summary="Document Format Files">
<tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>
<tr><td>1</td><td>10-Q</td><td><a href="/ix?doc=/Archives/edgar/data/1633917/000163391726000082/pypl-20260630.htm">file</a></td><td>10-Q</td><td>2922466</td></tr>
<tr><td>2</td><td>EX-10.02</td><td><a href="/Archives/edgar/data/1633917/000163391726000082/award.htm">award</a></td><td>EX-10.02</td><td>85955</td></tr>
</table>
<table class="tableFile" summary="Data Files">
<tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>
<tr><td>128</td><td>EXTRACTED XBRL INSTANCE DOCUMENT</td><td><a href="/Archives/edgar/data/1633917/000163391726000082/pypl-20260630_htm.xml">instance</a></td><td>XML</td><td>3741441</td></tr>
</table>
"""


def filing() -> FilingMetadata:
    return FilingMetadata(
        cik=CIK,
        accession_number=ACCESSION,
        form="10-Q",
        filed_on=date(2026, 7, 28),
        report_period_end=date(2026, 6, 30),
        accepted_at=datetime(2026, 7, 28, 17, 3, 36, tzinfo=timezone.utc),
        primary_document="pypl-20260630.htm",
        primary_document_description="10-Q",
        is_amendment=False,
        is_inline_xbrl=True,
        sec_index_url="https://www.sec.gov/filing-index",
    )


class FilingDocumentTests(unittest.TestCase):
    def test_index_inventory_unwraps_ix_and_classifies_documents(self):
        documents = parse_filing_index(INDEX_HTML, cik=CIK, accession_number=ACCESSION)

        self.assertEqual(len(documents), 3)
        self.assertEqual(documents[0].document_name, "pypl-20260630.htm")
        self.assertEqual(documents[0].category, "primary")
        self.assertEqual(documents[1].category, "exhibit")
        self.assertEqual(documents[2].document_type, "XML")
        self.assertEqual(documents[2].size_bytes, 3_741_441)

    def test_document_client_is_sec_only_bounded_and_cached(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.headers = {"Content-Type": "text/html", "Content-Length": "5"}
        response.iter_content.return_value = (b"he", b"llo")
        request_get = Mock(return_value=response)
        client = EdgarClient(
            "Bizqlab owner@example.test",
            request_get=request_get,
            monotonic=Mock(return_value=1.0),
            document_max_bytes=5,
        )
        url = "https://www.sec.gov/Archives/edgar/data/1633917/file.htm"

        self.assertEqual(client.filing_document(url)[0], b"hello")
        self.assertEqual(client.filing_document(url)[0], b"hello")
        self.assertEqual(request_get.call_count, 1)
        self.assertTrue(request_get.call_args.kwargs["stream"])
        with self.assertRaises(ValueError):
            client.filing_document("https://example.com/file.htm")

        response.headers["Content-Length"] = "6"
        with self.assertRaisesRegex(EdgarResponseError, "exceeds byte limit"):
            client.filing_document(
                "https://www.sec.gov/Archives/edgar/data/1633917/other.htm"
            )

    def test_instance_facts_keep_only_non_dimensional_numeric_contexts(self):
        instance = b"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
 xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
 xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
 xmlns:us-gaap="http://fasb.org/us-gaap/2026"
 xmlns:dei="http://xbrl.sec.gov/dei/2026">
 <xbrli:context id="q2"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:context id="segment"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier><xbrli:segment><xbrldi:explicitMember dimension="x">y</xbrldi:explicitMember></xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>2026-04-01</xbrli:startDate><xbrli:endDate>2026-06-30</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
 <dei:DocumentFiscalYearFocus contextRef="q2">2026</dei:DocumentFiscalYearFocus>
 <dei:DocumentFiscalPeriodFocus contextRef="q2">Q2</dei:DocumentFiscalPeriodFocus>
 <us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax contextRef="q2" unitRef="usd">8682000000</us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax>
 <us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax contextRef="segment" unitRef="usd">1</us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax>
</xbrli:xbrl>"""
        facts = extract_instance_facts(
            instance,
            filing=filing(),
            source_url="https://www.sec.gov/Archives/edgar/data/1633917/instance.xml",
        )

        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].value, 8_682_000_000)
        self.assertEqual(facts[0].fiscal_period, "Q2")
        self.assertEqual(facts[0].taxonomy, "us-gaap")
        self.assertEqual(facts[0].unit, "USD")

    def test_sections_roles_claims_and_questions_keep_evidence(self):
        source = """
        <html><body><h1>ITEM 2: MANAGEMENT'S DISCUSSION AND ANALYSIS</h1>
        <p>The increase in revenue was driven by TPV growth.</p>
        <h1>ITEM 3: QUANTITATIVE AND QUALITATIVE DISCLOSURES</h1>
        <p>Market risk text.</p><h1>ITEM 4: CONTROLS</h1></body></html>
        """
        document = FilingDocument(
            CIK,
            ACCESSION,
            1,
            "10-Q",
            "filing.htm",
            "10-Q",
            100,
            "primary",
            "https://www.sec.gov/Archives/edgar/data/1633917/filing.htm",
        )
        snapshot = DocumentSnapshot(
            document,
            "text/html",
            "a" * 64,
            len(source),
            html_to_text(source),
        )
        sections = extract_filing_sections(snapshot)
        self.assertEqual(sections[0].category, "management_discussion")
        self.assertNotIn("Market risk text", sections[0].excerpt)
        change_claims = extract_change_explanation_claims((snapshot,))
        self.assertTrue(any("increase in revenue" in claim.statement for claim in change_claims))

        relationship_text = """PayPal and KKR agreed to purchase up to €40 billion of BNPL receivables.
Freshfields Bruckhaus Deringer LLP acted as legal advisors to PayPal.
ALPS PARTNERS S.À R.L.
as Purchaser
PAYPAL (EUROPE) S.À R.L.
as Seller"""
        relationship = DocumentSnapshot(
            document,
            "text/html",
            "b" * 64,
            len(relationship_text),
            relationship_text,
        )
        roles = extract_entity_roles((relationship,))
        claims, questions = build_paypal_bnpl_claims((relationship,))
        self.assertTrue(any("Freshfields" in role.entity_name for role in roles))
        self.assertTrue(any(claim.claim_kind == "adviser_role" for claim in claims))
        self.assertEqual(len(questions), 3)

    def test_bnpl_questions_are_not_added_to_unrelated_filing(self):
        document = FilingDocument(
            CIK,
            ACCESSION,
            1,
            "10-Q",
            "filing.htm",
            "10-Q",
            100,
            "primary",
            "https://www.sec.gov/Archives/edgar/data/1633917/filing.htm",
        )
        snapshot = DocumentSnapshot(document, "text/html", "d" * 64, 20, "Ordinary filing text")
        claims, questions = build_paypal_bnpl_claims((snapshot,))
        self.assertEqual(claims, ())
        self.assertEqual(questions, ())


class FilingDocumentPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        self.connection = self.engine.connect()
        self.connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS portfolio")
        ResearchFiler.metadata.create_all(self.connection)
        self.database = Session(bind=self.connection, expire_on_commit=False)
        run_id = uuid.uuid4()
        now = datetime(2026, 7, 28, 17, 3, 36, tzinfo=timezone.utc)
        self.database.add(
            ResearchFiler(
                cik=CIK,
                name="PayPal Holdings, Inc.",
                sic="7389",
                sic_description="Services",
                former_names=[],
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        self.database.add(
            ResearchIngestionRun(
                id=run_id,
                filer_cik=CIK,
                status="completed",
                period_start=date(2022, 1, 1),
                extraction_version="fixture",
                submissions_sha256="a" * 64,
                companyfacts_sha256="b" * 64,
                counts={},
                error_summary=None,
                started_at=now,
                completed_at=now,
            )
        )
        source_filing = filing()
        self.database.add(
            ResearchFiling(
                accession_number=source_filing.accession_number,
                filer_cik=CIK,
                form="10-Q",
                base_form="10-Q",
                filed_on=source_filing.filed_on,
                report_period_end=source_filing.report_period_end,
                accepted_at=source_filing.accepted_at,
                primary_document=source_filing.primary_document,
                primary_document_description="10-Q",
                is_amendment=False,
                is_inline_xbrl=True,
                sec_index_url=source_filing.sec_index_url,
                metadata_source="submissions",
                first_seen_run_id=run_id,
                last_seen_run_id=run_id,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
        self.database.flush()

    def tearDown(self):
        self.database.close()
        self.connection.close()
        self.engine.dispose()

    def test_document_research_persistence_is_replay_safe_and_linked(self):
        document = FilingDocument(
            CIK,
            ACCESSION,
            1,
            "10-Q",
            "filing.htm",
            "10-Q",
            100,
            "primary",
            "https://www.sec.gov/Archives/edgar/data/1633917/filing.htm",
        )
        text = """ITEM 2: MANAGEMENT'S DISCUSSION AND ANALYSIS
PayPal and KKR agreed to purchase up to €40 billion of BNPL receivables.
Freshfields Bruckhaus Deringer LLP acted as legal advisors to PayPal.
ITEM 3: QUANTITATIVE AND QUALITATIVE DISCLOSURES"""
        snapshot = DocumentSnapshot(document, "text/html", "c" * 64, 200, text)
        roles = extract_entity_roles((snapshot,))
        claims, questions = build_paypal_bnpl_claims((snapshot,))
        bundle = FilingResearchBundle(
            filing=filing(),
            documents=(document,),
            snapshots=(snapshot,),
            evidence=extract_filing_sections(snapshot),
            entity_roles=roles,
            claims=claims,
            questions=questions,
        )

        first = persist_filing_research(self.database, bundle)
        second = persist_filing_research(self.database, bundle)
        self.database.commit()

        self.assertEqual(first.documents_inserted, 1)
        self.assertGreater(first.evidence_inserted, 0)
        self.assertGreater(first.entities_inserted, 0)
        self.assertGreater(first.claims_inserted, 0)
        self.assertEqual(second.documents_inserted, 0)
        self.assertEqual(second.evidence_inserted, 0)
        self.assertEqual(second.entities_inserted, 0)
        self.assertEqual(second.roles_inserted, 0)
        self.assertEqual(second.claims_inserted, 0)
        self.assertEqual(second.questions_inserted, 0)
        for model in (
            ResearchDocument,
            ResearchTextEvidence,
            ResearchEntity,
            ResearchDocumentEntityRole,
            ResearchClaim,
            ResearchOpenQuestion,
        ):
            self.assertGreater(self.database.scalar(select(func.count(model.id))), 0)
        self.assertGreater(
            len(filing_text_evidence(self.database, accession_number=ACCESSION)),
            0,
        )
        self.assertGreater(
            len(
                entity_role_history(
                    self.database,
                    normalized_entity_name="freshfields bruckhaus deringer llp",
                )
            ),
            0,
        )
        self.assertEqual(len(open_research_questions(self.database, filer_cik=CIK)), 3)

    def test_stage_four_migration_advances_single_chain(self):
        from importlib import import_module

        migration = import_module(
            "migrations.versions.20260906_08_financial_documents"
        )
        self.assertEqual(migration.revision, "20260906_08")
        self.assertEqual(migration.down_revision, "20260906_07")


if __name__ == "__main__":
    unittest.main()
