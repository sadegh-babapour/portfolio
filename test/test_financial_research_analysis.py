from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from financial_research.analysis import (
    ANALYSIS_VERSION,
    analyze_company_quarter,
    analyze_paypal_quarter,
    normalize_quarter_value,
    ranked_facts_by_metric,
)
from financial_research.contracts import (
    CompanyProfile,
    FactObservation,
    FilingMetadata,
    SecurityIdentifier,
)
from financial_research.ingestion import ExtractionBundle, persist_extraction_bundle
from financial_research.measure_store import persist_company_analysis
from financial_research.models import (
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
from financial_research.queries import analysis_measure_view


CONCEPTS = {
    "revenue": "RevenueFromContractWithCustomerExcludingAssessedTax",
    "operating_income": "OperatingIncomeLoss",
    "net_income": "NetIncomeLoss",
    "diluted_weighted_average_shares": "WeightedAverageNumberOfDilutedSharesOutstanding",
    "operating_cash_flow": "NetCashProvidedByUsedInOperatingActivities",
    "capital_expenditure": "PaymentsToAcquirePropertyPlantAndEquipment",
    "cash_and_equivalents": "CashAndCashEquivalentsAtCarryingValue",
    "short_term_investments": "ShortTermInvestments",
    "long_term_debt": "LongTermDebtNoncurrent",
    "current_assets": "AssetsCurrent",
    "current_liabilities": "LiabilitiesCurrent",
}


def fact(
    metric_key: str,
    value: int,
    *,
    start: date | None,
    end: date,
    accepted_day: int = 1,
) -> FactObservation:
    unit = "shares" if metric_key == "diluted_weighted_average_shares" else "USD"
    accession = f"0001633917-{end.year % 100:02d}-{accepted_day:06d}"
    return FactObservation(
        cik="0001633917",
        taxonomy="us-gaap",
        concept=CONCEPTS[metric_key],
        label=metric_key.replace("_", " ").title(),
        description="Test observation",
        unit=unit,
        value=value,
        period_start=start,
        period_end=end,
        filed_on=end,
        accepted_at=datetime(end.year, end.month, min(accepted_day, 28), tzinfo=timezone.utc),
        fiscal_year=end.year,
        fiscal_period="Q2",
        form="10-Q",
        accession_number=accession,
        frame=None,
        context_kind="duration" if start else "instant",
        is_amendment=False,
        sec_index_url=f"https://www.sec.gov/{accession}",
    )


def paypal_analysis_facts() -> tuple[FactObservation, ...]:
    observations = [
        # Revenue has both direct quarters and compatible Q1/H1 cumulative facts.
        fact("revenue", 8_288, start=date(2025, 4, 1), end=date(2025, 6, 30), accepted_day=11),
        fact("revenue", 7_791, start=date(2025, 1, 1), end=date(2025, 3, 31), accepted_day=10),
        fact("revenue", 16_079, start=date(2025, 1, 1), end=date(2025, 6, 30), accepted_day=11),
        fact("revenue", 7_885, start=date(2024, 4, 1), end=date(2024, 6, 30), accepted_day=9),
        fact("revenue", 7_699, start=date(2024, 1, 1), end=date(2024, 3, 31), accepted_day=8),
        fact("revenue", 15_584, start=date(2024, 1, 1), end=date(2024, 6, 30), accepted_day=9),
        fact("operating_income", 1_504, start=date(2025, 4, 1), end=date(2025, 6, 30), accepted_day=11),
        fact("operating_income", 1_325, start=date(2024, 4, 1), end=date(2024, 6, 30), accepted_day=9),
        fact("net_income", 1_261, start=date(2025, 4, 1), end=date(2025, 6, 30), accepted_day=11),
        fact("net_income", 1_128, start=date(2024, 4, 1), end=date(2024, 6, 30), accepted_day=9),
        fact("diluted_weighted_average_shares", 977, start=date(2025, 4, 1), end=date(2025, 6, 30), accepted_day=11),
        fact("diluted_weighted_average_shares", 1_047, start=date(2024, 4, 1), end=date(2024, 6, 30), accepted_day=9),
        # Cash flow and capex deliberately require Q2 = H1 YTD - Q1 YTD.
        fact("operating_cash_flow", 1_000, start=date(2025, 1, 1), end=date(2025, 3, 31), accepted_day=10),
        fact("operating_cash_flow", 2_058, start=date(2025, 1, 1), end=date(2025, 6, 30), accepted_day=11),
        fact("operating_cash_flow", 1_200, start=date(2024, 1, 1), end=date(2024, 3, 31), accepted_day=8),
        fact("operating_cash_flow", 3_442, start=date(2024, 1, 1), end=date(2024, 6, 30), accepted_day=9),
        fact("capital_expenditure", 190, start=date(2025, 1, 1), end=date(2025, 3, 31), accepted_day=10),
        fact("capital_expenditure", 402, start=date(2025, 1, 1), end=date(2025, 6, 30), accepted_day=11),
        fact("capital_expenditure", 170, start=date(2024, 1, 1), end=date(2024, 3, 31), accepted_day=8),
        fact("capital_expenditure", 380, start=date(2024, 1, 1), end=date(2024, 6, 30), accepted_day=9),
    ]
    for year, cash, investments, debt, assets, liabilities, day in (
        (2025, 6_688, 4_400, 12_000, 20_000, 15_000, 11),
        (2024, 5_100, 5_000, 11_500, 19_000, 14_500, 9),
    ):
        end = date(year, 6, 30)
        observations.extend(
            (
                fact("cash_and_equivalents", cash, start=None, end=end, accepted_day=day),
                fact("short_term_investments", investments, start=None, end=end, accepted_day=day),
                fact("long_term_debt", debt, start=None, end=end, accepted_day=day),
                fact("current_assets", assets, start=None, end=end, accepted_day=day),
                fact("current_liabilities", liabilities, start=None, end=end, accepted_day=day),
            )
        )
    return tuple(observations)


class PayPalAnalysisTests(unittest.TestCase):
    def test_generic_analysis_entry_matches_paypal_compatibility_wrapper(self):
        kwargs = {
            "company_name": "PayPal Holdings, Inc.",
            "period_end": date(2025, 6, 30),
            "fiscal_quarter": 2,
        }
        generic = analyze_company_quarter(paypal_analysis_facts(), **kwargs)
        compatibility = analyze_paypal_quarter(paypal_analysis_facts(), **kwargs)

        self.assertEqual(generic, compatibility)

    def test_reported_quarter_reconciles_to_ytd_difference(self):
        grouped = ranked_facts_by_metric(paypal_analysis_facts())
        revenue = normalize_quarter_value(
            "revenue",
            "Revenue",
            grouped["revenue"],
            period_end=date(2025, 6, 30),
            fiscal_quarter=2,
            unit="USD",
            revision_policy="latest_corrected",
        )

        self.assertEqual(revenue.value, 8_288)
        self.assertEqual(revenue.state, "reconciled")
        self.assertEqual(len(revenue.evidence), 3)

    def test_weighted_average_uses_direct_quarter_and_day_weighted_q4(self):
        q2_facts = paypal_analysis_facts()
        grouped = ranked_facts_by_metric(q2_facts)
        q2_shares = normalize_quarter_value(
            "diluted_weighted_average_shares",
            "Diluted weighted-average shares",
            grouped["diluted_weighted_average_shares"],
            period_end=date(2025, 6, 30),
            fiscal_quarter=2,
            unit="shares",
            revision_policy="latest_corrected",
            aggregation="weighted_average",
        )
        self.assertEqual(q2_shares.value, 977)
        self.assertEqual(q2_shares.state, "reported")

        annual = fact(
            "diluted_weighted_average_shares",
            950,
            start=date(2025, 1, 1),
            end=date(2025, 12, 31),
            accepted_day=20,
        )
        nine_month = fact(
            "diluted_weighted_average_shares",
            960,
            start=date(2025, 1, 1),
            end=date(2025, 9, 30),
            accepted_day=19,
        )
        q4_shares = normalize_quarter_value(
            "diluted_weighted_average_shares",
            "Diluted weighted-average shares",
            ranked_facts_by_metric((annual, nine_month))[
                "diluted_weighted_average_shares"
            ],
            period_end=date(2025, 12, 31),
            fiscal_quarter=4,
            unit="shares",
            revision_policy="latest_corrected",
            aggregation="weighted_average",
        )
        expected = (950 * 365 - 960 * 273) / 92
        self.assertAlmostEqual(q4_shares.value, expected)
        self.assertEqual(q4_shares.state, "derived")

    def test_analysis_calculates_measures_and_blocks_incomplete_net_liquidity(self):
        report = analyze_paypal_quarter(
            paypal_analysis_facts(),
            company_name="PayPal Holdings, Inc.",
            period_end=date(2025, 6, 30),
            fiscal_quarter=2,
        )
        normalized = {item.key: item for item in report.normalized_facts}
        measures = {item.key: item for item in report.derived_measures}

        self.assertEqual(normalized["operating_cash_flow"].value, 1_058)
        self.assertEqual(normalized["operating_cash_flow"].state, "derived")
        self.assertAlmostEqual(measures["revenue_growth_yoy"].value, 5.11, places=2)
        self.assertAlmostEqual(measures["operating_margin"].value, 18.15, places=2)
        self.assertAlmostEqual(
            measures["operating_margin_change_yoy"].value,
            1.34,
            places=2,
        )
        self.assertEqual(measures["simplified_free_cash_flow"].value, 846)
        self.assertEqual(measures["working_capital"].value, 5_000)
        self.assertEqual(measures["working_capital_change_yoy"].value, 500)
        self.assertAlmostEqual(measures["diluted_share_change_yoy"].value, -6.69, places=2)
        self.assertIsNone(measures["net_liquidity"].value)
        self.assertEqual(measures["net_liquidity"].state, "missing")

    def test_prompt_context_is_json_serializable_and_preserves_evidence(self):
        report = analyze_paypal_quarter(
            paypal_analysis_facts(),
            company_name="PayPal Holdings, Inc.",
            period_end=date(2025, 6, 30),
            fiscal_quarter=2,
        )
        context = report.prompt_context()
        encoded = json.dumps(context)

        self.assertIn(ANALYSIS_VERSION, encoded)
        revenue = next(item for item in context["normalized_facts"] if item["key"] == "revenue")
        self.assertEqual(revenue["state"], "reconciled")
        self.assertEqual(len(revenue["evidence"]), 3)
        self.assertIn("Request filing text", context["instruction"])


ANALYSIS_TABLES = (
    ResearchFiler.__table__,
    ResearchIngestionRun.__table__,
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


class PayPalAnalysisPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        self.connection = self.engine.connect()
        self.connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS portfolio")
        ResearchFiler.metadata.create_all(self.connection, tables=ANALYSIS_TABLES)
        self.database = Session(bind=self.connection, expire_on_commit=False)

    def tearDown(self):
        self.database.close()
        self.connection.close()
        self.engine.dispose()

    def test_analysis_persistence_is_versioned_evidence_linked_and_replay_safe(self):
        facts = paypal_analysis_facts()
        filings = {}
        for observation in facts:
            filings.setdefault(
                observation.accession_number,
                FilingMetadata(
                    cik=observation.cik,
                    accession_number=observation.accession_number,
                    form=observation.form,
                    filed_on=observation.filed_on,
                    report_period_end=observation.period_end,
                    accepted_at=observation.accepted_at,
                    primary_document="fixture.htm",
                    primary_document_description="fixture",
                    is_amendment=False,
                    is_inline_xbrl=True,
                    sec_index_url=observation.sec_index_url,
                ),
            )
        bundle = ExtractionBundle(
            profile=CompanyProfile(
                cik="0001633917",
                name="PayPal Holdings, Inc.",
                sic="7389",
                sic_description="Services-Business Services, NEC",
                securities=(SecurityIdentifier("PYPL", "Nasdaq"),),
                former_names=(),
                filings=tuple(filings.values()),
            ),
            source_filings=tuple(filings.values()),
            facts=facts,
            issues=(),
            period_start=date(2022, 1, 1),
            submissions_sha256="a" * 64,
            companyfacts_sha256="b" * 64,
        )
        persist_extraction_bundle(self.database, bundle)
        report = analyze_paypal_quarter(
            facts,
            company_name="PayPal Holdings, Inc.",
            period_end=date(2025, 6, 30),
            fiscal_quarter=2,
        )

        inserted = persist_company_analysis(self.database, report)
        replayed = persist_company_analysis(self.database, report)
        self.database.commit()

        expected = len(report.normalized_facts) + len(report.derived_measures)
        self.assertEqual(inserted, expected)
        self.assertEqual(replayed, 0)
        self.assertEqual(
            self.database.scalar(select(func.count(ResearchDerivedMeasure.id))),
            expected,
        )
        self.assertGreater(
            self.database.scalar(select(func.count(ResearchDerivedMeasureInput.id))),
            0,
        )
        net_liquidity = self.database.scalar(
            select(ResearchDerivedMeasure).where(
                ResearchDerivedMeasure.measure_key == "net_liquidity"
            )
        )
        self.assertIsNone(net_liquidity.value_json)
        self.assertEqual(net_liquidity.quality_state, "missing")
        latest_revenue_growth = analysis_measure_view(
            self.database,
            view="latest_calculated",
            filer_cik="0001633917",
            measure_key="revenue_growth_yoy",
            period_end=date(2025, 6, 30),
        )
        self.assertAlmostEqual(latest_revenue_growth.value_json, 5.11, places=2)
        analysis_versions = self.database.scalars(
            select(ResearchTransformationVersion).where(
                ResearchTransformationVersion.kind == "financial_analysis"
            )
        ).all()
        self.assertEqual(len(analysis_versions), 1)

    def test_stage_three_migration_advances_single_chain(self):
        from importlib import import_module

        migration = import_module(
            "migrations.versions.20260906_07_financial_measures"
        )
        self.assertEqual(migration.revision, "20260906_07")
        self.assertEqual(migration.down_revision, "20260905_06")


if __name__ == "__main__":
    unittest.main()
