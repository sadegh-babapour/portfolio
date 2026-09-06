from __future__ import annotations

import unittest
from importlib import import_module
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from financial_research.ingestion import (
    build_extraction_bundle,
    persist_extraction_bundle,
    prune_unreferenced_ingestion_runs,
)
from financial_research.edgar import EdgarResponseError
from financial_research.metrics import (
    CANONICAL_METRICS,
    CANONICAL_METRIC_VERSION,
    METRICS_BY_KEY,
    metric_for_fact,
)
from financial_research.models import (
    ResearchAutomationAttempt,
    ResearchAutomationRun,
    ResearchCanonicalMapping,
    ResearchDerivedMeasure,
    ResearchDerivedMeasureInput,
    ResearchFactMetricMapping,
    ResearchFactObservation,
    ResearchFiler,
    ResearchFiling,
    ResearchIngestionRun,
    ResearchReject,
    ResearchSecurity,
    ResearchTransformationVersion,
)
from financial_research.queries import canonical_fact_view, fact_revision_view
from financial_research.selection import RankedFact, classify_period, select_canonical_fact
from test_financial_research import COMPANY_FACTS, SUBMISSIONS


RESEARCH_TABLES = (
    ResearchFiler.__table__,
    ResearchIngestionRun.__table__,
    ResearchAutomationRun.__table__,
    ResearchAutomationAttempt.__table__,
    ResearchSecurity.__table__,
    ResearchFiling.__table__,
    ResearchFactObservation.__table__,
    ResearchCanonicalMapping.__table__,
    ResearchFactMetricMapping.__table__,
    ResearchTransformationVersion.__table__,
    ResearchReject.__table__,
    ResearchDerivedMeasure.__table__,
    ResearchDerivedMeasureInput.__table__,
)


class CanonicalMetricTests(unittest.TestCase):
    def test_catalog_keys_are_unique_and_rules_are_explicit(self):
        self.assertEqual(len(METRICS_BY_KEY), len(CANONICAL_METRICS))
        self.assertIn("revenue", METRICS_BY_KEY)
        self.assertIn("operating_cash_flow", METRICS_BY_KEY)
        for metric in CANONICAL_METRICS:
            self.assertTrue(metric.expected_units)
            self.assertTrue(metric.candidates)
            self.assertIn(metric.context_kind, {"instant", "duration"})

    def test_mapping_requires_exact_semantics(self):
        mapped = metric_for_fact(
            cik="0001633917",
            taxonomy="us-gaap",
            concept="RevenueFromContractWithCustomerExcludingAssessedTax",
            unit="USD",
            context_kind="duration",
        )
        wrong_unit = metric_for_fact(
            cik="0001633917",
            taxonomy="us-gaap",
            concept="RevenueFromContractWithCustomerExcludingAssessedTax",
            unit="shares",
            context_kind="duration",
        )

        self.assertEqual(mapped[0].key, "revenue")
        self.assertIsNone(wrong_unit)

    def test_period_and_revision_selection_are_explicit(self):
        bundle = build_extraction_bundle(SUBMISSIONS, COMPANY_FACTS)
        revenue = [
            fact
            for fact in bundle.facts
            if fact.concept == "RevenueFromContractWithCustomerExcludingAssessedTax"
            and fact.period_end == date(2025, 6, 30)
        ]
        ranked = [RankedFact(fact, 10) for fact in revenue]

        self.assertTrue(all(classify_period(fact) == "quarter" for fact in revenue))
        original = select_canonical_fact(
            ranked,
            period_end=date(2025, 6, 30),
            period_kind="quarter",
            revision_policy="originally_reported",
        )
        corrected = select_canonical_fact(
            ranked,
            period_end=date(2025, 6, 30),
            period_kind="quarter",
        )

        self.assertEqual(original.state, "selected")
        self.assertEqual(original.fact.value, 8_288_000_000)
        self.assertEqual(corrected.fact.value, 8_300_000_000)


class ResearchPersistenceTests(unittest.TestCase):
    def test_models_and_migration_stay_in_portfolio_schema(self):
        self.assertTrue(all(table.schema == "portfolio" for table in RESEARCH_TABLES))
        migration = import_module(
            "migrations.versions.20260905_06_financial_research"
        )
        self.assertEqual(migration.revision, "20260905_06")
        self.assertEqual(migration.down_revision, "20260903_05")
        automation_migration = import_module(
            "migrations.versions.20260906_09_research_automation"
        )
        self.assertEqual(automation_migration.revision, "20260906_09")
        self.assertEqual(automation_migration.down_revision, "20260906_08")

    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        self.connection = self.engine.connect()
        self.connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS portfolio")
        ResearchFiler.metadata.create_all(self.connection, tables=RESEARCH_TABLES)
        self.database = Session(bind=self.connection, expire_on_commit=False)

    def tearDown(self):
        self.database.close()
        self.connection.close()
        self.engine.dispose()

    def test_bundle_keeps_source_form_classification_and_hashes(self):
        bundle = build_extraction_bundle(SUBMISSIONS, COMPANY_FACTS)
        filing = next(
            item
            for item in bundle.source_filings
            if item.accession_number == "0001633917-22-000027"
        )
        fact = next(
            item
            for item in bundle.facts
            if item.accession_number == "0001633917-22-000027"
        )

        self.assertEqual(filing.form, "8-K")
        self.assertEqual(fact.form, "10-K")
        self.assertEqual(filing.metadata_source, "submissions")
        self.assertEqual(len(bundle.submissions_sha256), 64)
        self.assertFalse(bundle.issues)

    def test_bundle_rejects_cross_company_source_mix(self):
        mismatched = {**COMPANY_FACTS, "cik": 320193}
        with self.assertRaisesRegex(EdgarResponseError, "does not match"):
            build_extraction_bundle(SUBMISSIONS, mismatched)

    def test_reingestion_is_idempotent_and_revision_views_remain_distinct(self):
        bundle = build_extraction_bundle(SUBMISSIONS, COMPANY_FACTS)
        first_seen = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        first = persist_extraction_bundle(
            self.database,
            bundle,
            observed_at=first_seen,
        )
        self.database.commit()
        second = persist_extraction_bundle(
            self.database,
            bundle,
            observed_at=first_seen + timedelta(days=1),
        )
        self.database.commit()

        self.assertEqual(first.facts_inserted, 4)
        self.assertEqual(first.facts_mapped, 3)
        self.assertEqual(second.facts_inserted, 0)
        self.assertEqual(second.facts_seen_again, 4)
        self.assertEqual(
            self.database.scalar(select(func.count(ResearchFactObservation.id))),
            4,
        )
        self.assertEqual(
            self.database.scalar(select(func.count(ResearchFactMetricMapping.id))),
            3,
        )
        self.assertEqual(
            self.database.scalar(select(func.count(ResearchIngestionRun.id))),
            2,
        )
        self.assertIsNotNone(
            self.database.scalar(
                select(ResearchTransformationVersion).where(
                    ResearchTransformationVersion.version == CANONICAL_METRIC_VERSION
                )
            )
        )

        query = {
            "filer_cik": "0001633917",
            "taxonomy": "us-gaap",
            "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
            "unit": "USD",
            "period_start": date(2025, 4, 1),
            "period_end": date(2025, 6, 30),
        }
        original = fact_revision_view(
            self.database,
            view="originally_reported",
            **query,
        )
        corrected = fact_revision_view(
            self.database,
            view="latest_corrected",
            **query,
        )
        history = fact_revision_view(self.database, view="history", **query)

        self.assertEqual(original.value_json, 8_288_000_000)
        self.assertEqual(corrected.value_json, 8_300_000_000)
        self.assertEqual(len(history), 2)
        self.assertEqual(original.first_seen_at.replace(tzinfo=timezone.utc), first_seen)
        self.assertEqual(
            original.last_seen_at.replace(tzinfo=timezone.utc),
            first_seen + timedelta(days=1),
        )

        canonical_original = canonical_fact_view(
            self.database,
            filer_cik="0001633917",
            metric_key="revenue",
            period_end=date(2025, 6, 30),
            period_kind="quarter",
            view="originally_reported",
        )
        canonical_latest = canonical_fact_view(
            self.database,
            filer_cik="0001633917",
            metric_key="revenue",
            period_end=date(2025, 6, 30),
            period_kind="quarter",
        )
        self.assertEqual(canonical_original.fact.value_json, 8_288_000_000)
        self.assertEqual(canonical_latest.fact.value_json, 8_300_000_000)

    def test_missing_submission_metadata_is_bounded_and_recorded(self):
        submissions = {
            **SUBMISSIONS,
            "filings": {
                "recent": {
                    key: values[:-1]
                    for key, values in SUBMISSIONS["filings"]["recent"].items()
                }
            },
        }
        bundle = build_extraction_bundle(submissions, COMPANY_FACTS)
        summary = persist_extraction_bundle(self.database, bundle)
        self.database.commit()

        fallback = self.database.get(ResearchFiling, "0001633917-22-000027")
        reject = self.database.scalar(select(ResearchReject))
        self.assertEqual(summary.rejects_recorded, 1)
        self.assertEqual(fallback.metadata_source, "companyfacts_fallback")
        self.assertEqual(reject.reason_code, "submission_metadata_missing")
        self.assertEqual(reject.bounded_context, {"fact_form": "10-K"})

    def test_retention_prunes_only_unreferenced_intermediate_runs(self):
        bundle = build_extraction_bundle(SUBMISSIONS, COMPANY_FACTS)
        start = datetime(2023, 1, 1, tzinfo=timezone.utc)
        persist_extraction_bundle(self.database, bundle, observed_at=start)
        persist_extraction_bundle(
            self.database,
            bundle,
            observed_at=start + timedelta(days=1),
        )
        persist_extraction_bundle(
            self.database,
            bundle,
            observed_at=start + timedelta(days=800),
        )
        self.database.commit()

        deleted = prune_unreferenced_ingestion_runs(
            self.database,
            now=start + timedelta(days=1_000),
        )
        self.database.commit()

        self.assertEqual(deleted, 1)
        self.assertEqual(
            self.database.scalar(select(func.count(ResearchIngestionRun.id))),
            2,
        )


if __name__ == "__main__":
    unittest.main()
