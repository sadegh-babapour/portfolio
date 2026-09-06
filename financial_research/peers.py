from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .analysis import AnalysisValue, CompanyAnalysis
from .universe import PAYMENTS, ResearchCompany


PAYMENTS_PEER_MODEL_VERSION = "payments-peer-2026-09-06.1"
PeerCohort = Literal[
    "improving_with_quality",
    "improving_but_fragile",
    "stable_resilient",
    "possible_turnaround",
    "deteriorating",
    "mixed_evidence",
    "not_comparable",
]


PeerCompany = ResearchCompany


@dataclass(frozen=True, slots=True)
class ComparisonLens:
    key: str
    label: str
    value: float | None
    unit: str
    state: str
    confidence: str
    interpretation: str


@dataclass(frozen=True, slots=True)
class PeerAssessment:
    cik: str
    company_name: str
    period_end: str
    fiscal_quarter: int
    model_version: str
    comparable: bool
    cohort: PeerCohort
    signal_pattern: PeerCohort | None
    reasons: tuple[str, ...]
    lenses: tuple[ComparisonLens, ...]


PAYMENTS_COHORT: tuple[PeerCompany, ...] = PAYMENTS.companies


COMPARISON_LENSES = (
    ("revenue_growth_yoy", "Revenue growth", "Growth direction, not company size"),
    (
        "operating_margin_change_yoy",
        "Operating-margin change",
        "Profit-quality direction; levels remain business-model sensitive",
    ),
    ("cash_conversion", "Cash conversion", "Operating cash flow relative to net income"),
    (
        "diluted_share_change_yoy",
        "Diluted-share change",
        "Per-share capital-allocation context, not proof of value creation",
    ),
)
REQUIRED_CLASSIFICATION_KEYS = frozenset(
    {"revenue_growth_yoy", "operating_margin_change_yoy", "cash_conversion"}
)
STRUCTURAL_REVIEW_THRESHOLDS = {
    "absolute_revenue_growth_percent": 30.0,
    "absolute_margin_change_points": 5.0,
    "cash_conversion_ratio": 5.0,
}


def _lens(value: AnalysisValue | None, key: str, label: str, note: str) -> ComparisonLens:
    if value is None:
        return ComparisonLens(
            key=key,
            label=label,
            value=None,
            unit="unknown",
            state="missing",
            confidence="blocked",
            interpretation=note,
        )
    return ComparisonLens(
        key=key,
        label=label,
        value=float(value.value) if value.usable else None,
        unit=value.unit,
        state=value.state,
        confidence=value.confidence,
        interpretation=note,
    )


def _classification(values: dict[str, float]) -> tuple[PeerCohort, tuple[str, ...]]:
    growth = values["revenue_growth_yoy"]
    margin_change = values["operating_margin_change_yoy"]
    cash_conversion = values["cash_conversion"]
    reasons = (
        f"Revenue growth was {growth:.2f}% year over year.",
        f"Operating margin changed {margin_change:.2f} percentage points.",
        f"Operating cash flow was {cash_conversion:.2f}x net income.",
    )
    if abs(growth) <= 2 and abs(margin_change) <= 0.5 and cash_conversion >= 1:
        return "stable_resilient", reasons
    if growth > 0 and margin_change >= 0 and cash_conversion >= 1:
        return "improving_with_quality", reasons
    if growth > 0 and (margin_change < 0 or cash_conversion < 1):
        return "improving_but_fragile", reasons
    if growth <= 0 and margin_change > 0 and cash_conversion >= 1:
        return "possible_turnaround", reasons
    if growth < 0 and margin_change < 0:
        return "deteriorating", reasons
    return "mixed_evidence", reasons


def assess_peer_quarter(
    report: CompanyAnalysis,
    *,
    candidate: PeerCompany | None = None,
) -> PeerAssessment:
    """Classify one quarter only after explicit evidence and quality gates pass."""
    measures = {measure.key: measure for measure in report.derived_measures}
    lenses = tuple(
        _lens(measures.get(key), key, label, note)
        for key, label, note in COMPARISON_LENSES
    )
    blocked = tuple(
        lens.key
        for lens in lenses
        if lens.key in REQUIRED_CLASSIFICATION_KEYS
        and (lens.value is None or lens.confidence == "blocked")
    )
    if blocked:
        return PeerAssessment(
            cik=report.cik,
            company_name=report.company_name,
            period_end=report.period_end.isoformat(),
            fiscal_quarter=report.fiscal_quarter,
            model_version=PAYMENTS_PEER_MODEL_VERSION,
            comparable=False,
            cohort="not_comparable",
            signal_pattern=None,
            reasons=("Missing or blocked required measures: " + ", ".join(blocked),),
            lenses=lenses,
        )
    values = {lens.key: lens.value for lens in lenses if lens.value is not None}
    signal_pattern, reasons = _classification(values)
    review_reasons = []
    if candidate is not None and candidate.comparison_status != "reviewed_with_metric_gates":
        review_reasons.append(
            "Candidate requires business-model and filing-event review before comparison."
        )
    if abs(values["revenue_growth_yoy"]) > STRUCTURAL_REVIEW_THRESHOLDS[
        "absolute_revenue_growth_percent"
    ]:
        review_reasons.append("Revenue growth exceeds the structural-change review threshold.")
    if abs(values["operating_margin_change_yoy"]) > STRUCTURAL_REVIEW_THRESHOLDS[
        "absolute_margin_change_points"
    ]:
        review_reasons.append("Margin change exceeds the structural-change review threshold.")
    if values["cash_conversion"] > STRUCTURAL_REVIEW_THRESHOLDS[
        "cash_conversion_ratio"
    ]:
        review_reasons.append("Cash conversion exceeds the structural-change review threshold.")
    if review_reasons:
        return PeerAssessment(
            cik=report.cik,
            company_name=report.company_name,
            period_end=report.period_end.isoformat(),
            fiscal_quarter=report.fiscal_quarter,
            model_version=PAYMENTS_PEER_MODEL_VERSION,
            comparable=False,
            cohort="not_comparable",
            signal_pattern=signal_pattern,
            reasons=tuple(review_reasons) + reasons,
            lenses=lenses,
        )
    return PeerAssessment(
        cik=report.cik,
        company_name=report.company_name,
        period_end=report.period_end.isoformat(),
        fiscal_quarter=report.fiscal_quarter,
        model_version=PAYMENTS_PEER_MODEL_VERSION,
        comparable=True,
        cohort=signal_pattern,
        signal_pattern=signal_pattern,
        reasons=reasons,
        lenses=lenses,
    )


def assess_payment_cohort(reports: tuple[CompanyAnalysis, ...]) -> tuple[PeerAssessment, ...]:
    """Require one period and fiscal quarter before producing a peer cohort."""
    if not reports:
        return ()
    periods = {(report.period_end, report.fiscal_quarter) for report in reports}
    candidates = {candidate.cik: candidate for candidate in PAYMENTS_COHORT}
    assessments = tuple(
        assess_peer_quarter(report, candidate=candidates.get(report.cik))
        for report in reports
    )
    if len(periods) == 1:
        return assessments
    reason = "Peer reports do not share the same period end and fiscal quarter."
    return tuple(
        PeerAssessment(
            cik=item.cik,
            company_name=item.company_name,
            period_end=item.period_end,
            fiscal_quarter=item.fiscal_quarter,
            model_version=item.model_version,
            comparable=False,
            cohort="not_comparable",
            signal_pattern=item.signal_pattern,
            reasons=(reason,),
            lenses=item.lenses,
        )
        for item in assessments
    )
