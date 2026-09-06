import unittest
from dataclasses import replace
from datetime import date
from unittest.mock import MagicMock, patch

from financial_research.analysis import AnalysisValue, CompanyAnalysis
from financial_research.peers import (
    PAYMENTS_COHORT,
    PAYMENTS_PEER_MODEL_VERSION,
    assess_payment_cohort,
    assess_peer_quarter,
)
from scripts.inspect_sec_peer_cohort import inspect_peer_cohort, summary_lines


def measure(
    key: str,
    value: float | None,
    *,
    state: str = "derived",
    confidence: str = "high",
) -> AnalysisValue:
    return AnalysisValue(
        key=key,
        label=key.replace("_", " ").title(),
        value=value,
        unit="ratio" if key == "cash_conversion" else "percent",
        period_end=date(2026, 6, 30),
        period_kind="quarter",
        formula="test formula",
        version="test-analysis",
        state=state,
        confidence=confidence,
        evidence=(),
        note="Test measure",
    )


def report(
    *,
    growth: float | None = 5.0,
    margin_change: float | None = 1.0,
    cash_conversion: float | None = 1.2,
    period_end: date = date(2026, 6, 30),
) -> CompanyAnalysis:
    values = (
        measure(
            "revenue_growth_yoy",
            growth,
            state="missing" if growth is None else "derived",
            confidence="blocked" if growth is None else "high",
        ),
        measure(
            "operating_margin_change_yoy",
            margin_change,
            state="missing" if margin_change is None else "derived",
            confidence="blocked" if margin_change is None else "high",
        ),
        measure(
            "cash_conversion",
            cash_conversion,
            state="missing" if cash_conversion is None else "derived",
            confidence="blocked" if cash_conversion is None else "medium",
        ),
        measure("diluted_share_change_yoy", -4.0),
    )
    return CompanyAnalysis(
        cik="0001633917",
        company_name="PayPal Holdings, Inc.",
        period_end=period_end,
        fiscal_quarter=2,
        revision_policy="latest_corrected",
        normalized_facts=(),
        derived_measures=values,
        unavailable_operating_metrics=(),
    )


class PaymentPeerContractTests(unittest.TestCase):
    def test_payment_cohort_is_unique_and_public_eligible(self):
        self.assertEqual(len(PAYMENTS_COHORT), 5)
        self.assertEqual(len({company.cik for company in PAYMENTS_COHORT}), 5)
        self.assertTrue(all(len(company.cik) == 10 for company in PAYMENTS_COHORT))
        self.assertEqual(
            [company.ticker for company in PAYMENTS_COHORT if company.publication_status == "published"],
            ["PYPL"],
        )
        self.assertTrue(
            all(company.publication_status in {"published", "public_eligible"} for company in PAYMENTS_COHORT)
        )

    def test_explicit_rules_separate_quality_patterns(self):
        improving = assess_peer_quarter(report())
        fragile = assess_peer_quarter(report(margin_change=-1.5))
        deteriorating = assess_peer_quarter(report(growth=-3.0, margin_change=-1.0))

        self.assertEqual(improving.model_version, PAYMENTS_PEER_MODEL_VERSION)
        self.assertEqual(improving.cohort, "improving_with_quality")
        self.assertEqual(improving.signal_pattern, "improving_with_quality")
        self.assertEqual(fragile.cohort, "improving_but_fragile")
        self.assertEqual(deteriorating.cohort, "deteriorating")
        self.assertTrue(all(item.reasons for item in (improving, fragile, deteriorating)))

    def test_missing_required_measure_blocks_classification(self):
        assessment = assess_peer_quarter(report(cash_conversion=None))

        self.assertFalse(assessment.comparable)
        self.assertEqual(assessment.cohort, "not_comparable")
        self.assertIsNone(assessment.signal_pattern)
        self.assertIn("cash_conversion", assessment.reasons[0])

    def test_cohort_requires_matching_period_and_quarter(self):
        first = report()
        second = replace(
            report(period_end=date(2026, 3, 31)),
            cik="0001512673",
            company_name="Block, Inc.",
        )

        assessments = assess_payment_cohort((first, second))

        self.assertEqual(len(assessments), 2)
        self.assertTrue(all(not item.comparable for item in assessments))
        self.assertTrue(all(item.cohort == "not_comparable" for item in assessments))
        self.assertIn("same period end", assessments[0].reasons[0])

    def test_reviewed_candidate_outlier_signals_are_not_ranked(self):
        block_report = replace(
            report(cash_conversion=11.52),
            cik="0001512673",
            company_name="Block, Inc.",
        )

        assessment = assess_payment_cohort((block_report,))[0]

        self.assertFalse(assessment.comparable)
        self.assertEqual(assessment.cohort, "not_comparable")
        self.assertEqual(assessment.signal_pattern, "improving_with_quality")
        self.assertIn("Cash conversion", assessment.reasons[0])

    def test_multi_company_inspection_records_failure_and_withholds_partial_assessment(self):
        complete_inspection = {
            "configured": {"ticker": "PYPL"},
            "status": "complete",
            "sec_company_name": "PayPal Holdings, Inc.",
            "identity_matches": True,
            "quarter_count": 18,
            "latest_target": {"period_end": "2026-06-30", "quarter": 2},
            "canonical_metrics": ["revenue"],
        }
        with patch(
            "scripts.inspect_sec_peer_cohort._inspect_candidate",
            side_effect=[
                (complete_inspection, report()),
                ConnectionError("temporary network failure"),
            ],
        ):
            result = inspect_peer_cohort(
                MagicMock(),
                since=date(2022, 1, 1),
                candidates=PAYMENTS_COHORT[:2],
            )

        self.assertFalse(result["complete"])
        self.assertEqual(result["failure_count"], 1)
        self.assertEqual(result["inspections"][1]["status"], "failed")
        self.assertEqual(result["inspections"][1]["reason_code"], "ConnectionError")
        self.assertTrue(result["inspections"][1]["retryable"])
        self.assertEqual(result["assessments"], [])
        self.assertFalse(result["write_performed"])
        self.assertFalse(result["publication_performed"])

        lines = summary_lines(result)
        self.assertIn("PYPL: PayPal Holdings, Inc.", lines[0])
        self.assertIn("XYZ: failed", lines[1])
        self.assertEqual(lines[-1], "No database writes or public publication performed.")


if __name__ == "__main__":
    unittest.main()
