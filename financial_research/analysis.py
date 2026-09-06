from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import date
from typing import Callable, Iterable, Literal

from .contracts import FactObservation
from .metrics import CANONICAL_METRIC_VERSION, metric_for_fact
from .provenance import fact_fingerprint
from .selection import (
    FactSelection,
    PeriodKind,
    RankedFact,
    RevisionPolicy,
    classify_period,
    select_canonical_fact,
)


ANALYSIS_VERSION = "paypal-analysis-2026-09-06.1"
ANALYSIS_SPECIFICATION = {
    "version": ANALYSIS_VERSION,
    "quarter_normalization": {
        "additive_flows": "compatible cumulative period less prior cumulative period",
        "weighted_averages": "direct quarter, else duration-day-weighted derivation",
        "instant_balances": "reported at period end",
        "conflicts": "block as ambiguous",
    },
    "revision_policy": ("originally_reported", "latest_corrected"),
    "measures": (
        "revenue_change_yoy",
        "revenue_growth_yoy",
        "operating_margin",
        "operating_margin_change_yoy",
        "net_margin",
        "cash_conversion",
        "simplified_free_cash_flow",
        "net_liquidity",
        "working_capital",
        "working_capital_change_yoy",
        "diluted_share_change_yoy",
    ),
}
ValueState = Literal[
    "reported",
    "reconciled",
    "derived",
    "missing",
    "ambiguous",
    "unexpected_period",
    "invalid_numeric",
    "division_by_zero",
]
Confidence = Literal["high", "medium", "blocked"]
Aggregation = Literal["additive", "weighted_average"]


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    role: str
    metric_key: str
    value: int | float | str
    unit: str
    period_start: date | None
    period_end: date
    period_kind: str
    taxonomy: str
    concept: str
    accession_number: str
    form: str
    accepted_at: str | None
    sec_url: str
    source_fingerprint: str


@dataclass(frozen=True, slots=True)
class AnalysisValue:
    key: str
    label: str
    value: int | float | None
    unit: str
    period_end: date
    period_kind: str
    formula: str
    version: str
    state: ValueState
    confidence: Confidence
    evidence: tuple[EvidenceReference, ...]
    note: str

    @property
    def usable(self) -> bool:
        return self.value is not None and self.state in {
            "reported",
            "reconciled",
            "derived",
        }


@dataclass(frozen=True, slots=True)
class CompanyAnalysis:
    cik: str
    company_name: str
    period_end: date
    fiscal_quarter: int
    revision_policy: RevisionPolicy
    normalized_facts: tuple[AnalysisValue, ...]
    derived_measures: tuple[AnalysisValue, ...]
    unavailable_operating_metrics: tuple[str, ...]

    def prompt_context(self) -> dict:
        return {
            "company": {"cik": self.cik, "name": self.company_name},
            "analysis_version": ANALYSIS_VERSION,
            "canonical_metric_version": CANONICAL_METRIC_VERSION,
            "period_end": self.period_end.isoformat(),
            "fiscal_quarter": self.fiscal_quarter,
            "revision_policy": self.revision_policy,
            "normalized_facts": [_value_context(item) for item in self.normalized_facts],
            "derived_measures": [_value_context(item) for item in self.derived_measures],
            "unavailable_operating_metrics": list(self.unavailable_operating_metrics),
            "instruction": (
                "Treat reported evidence, derived formulas, and missing/ambiguous states "
                "separately. Request filing text before explaining causes."
            ),
        }


def _value_context(value: AnalysisValue) -> dict:
    result = asdict(value)
    result["period_end"] = value.period_end.isoformat()
    for evidence in result["evidence"]:
        evidence["period_start"] = (
            evidence["period_start"].isoformat()
            if evidence["period_start"] is not None
            else None
        )
        evidence["period_end"] = evidence["period_end"].isoformat()
    return result


def ranked_facts_by_metric(
    facts: Iterable[FactObservation],
) -> dict[str, tuple[RankedFact, ...]]:
    grouped: dict[str, list[RankedFact]] = {}
    for fact in facts:
        resolved = metric_for_fact(
            cik=fact.cik,
            taxonomy=fact.taxonomy,
            concept=fact.concept,
            unit=fact.unit,
            context_kind=fact.context_kind,
        )
        if resolved is None:
            continue
        metric, candidate = resolved
        grouped.setdefault(metric.key, []).append(
            RankedFact(fact=fact, mapping_priority=candidate.priority)
        )
    return {key: tuple(values) for key, values in grouped.items()}


def _evidence(role: str, metric_key: str, fact: FactObservation) -> EvidenceReference:
    return EvidenceReference(
        role=role,
        metric_key=metric_key,
        value=fact.value,
        unit=fact.unit,
        period_start=fact.period_start,
        period_end=fact.period_end,
        period_kind=classify_period(fact),
        taxonomy=fact.taxonomy,
        concept=fact.concept,
        accession_number=fact.accession_number,
        form=fact.form,
        accepted_at=fact.accepted_at.isoformat() if fact.accepted_at else None,
        sec_url=fact.sec_index_url,
        source_fingerprint=fact_fingerprint(fact),
    )


def _number(value: int | float | str) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _from_selection(
    key: str,
    label: str,
    unit: str,
    period_end: date,
    period_kind: str,
    selection: FactSelection,
) -> AnalysisValue:
    if selection.fact is None:
        state: ValueState = (
            selection.state
            if selection.state in {"missing", "ambiguous", "unexpected_period"}
            else "missing"
        )
        return AnalysisValue(
            key=key,
            label=label,
            value=None,
            unit=unit,
            period_end=period_end,
            period_kind=period_kind,
            formula="reported",
            version=ANALYSIS_VERSION,
            state=state,
            confidence="blocked",
            evidence=tuple(
                _evidence("candidate", key, fact) for fact in selection.candidates
            ),
            note=selection.reason,
        )
    numeric = _number(selection.fact.value)
    if numeric is None:
        return AnalysisValue(
            key=key,
            label=label,
            value=None,
            unit=unit,
            period_end=period_end,
            period_kind=period_kind,
            formula="reported",
            version=ANALYSIS_VERSION,
            state="invalid_numeric",
            confidence="blocked",
            evidence=(_evidence("reported", key, selection.fact),),
            note="The selected SEC value is not a finite number.",
        )
    return AnalysisValue(
        key=key,
        label=label,
        value=numeric,
        unit=selection.fact.unit,
        period_end=period_end,
        period_kind=period_kind,
        formula="reported",
        version=ANALYSIS_VERSION,
        state="reported",
        confidence="high",
        evidence=(_evidence("reported", key, selection.fact),),
        note=selection.reason,
    )


def select_reported_value(
    key: str,
    label: str,
    candidates: Iterable[RankedFact],
    *,
    period_end: date,
    period_kind: PeriodKind,
    unit: str,
    revision_policy: RevisionPolicy,
) -> AnalysisValue:
    selection = select_canonical_fact(
        candidates,
        period_end=period_end,
        period_kind=period_kind,
        revision_policy=revision_policy,
    )
    return _from_selection(key, label, unit, period_end, period_kind, selection)


def normalize_quarter_value(
    key: str,
    label: str,
    candidates: Iterable[RankedFact],
    *,
    period_end: date,
    fiscal_quarter: int,
    unit: str,
    revision_policy: RevisionPolicy,
    aggregation: Aggregation = "additive",
) -> AnalysisValue:
    candidate_tuple = tuple(candidates)
    direct = select_reported_value(
        key,
        label,
        candidate_tuple,
        period_end=period_end,
        period_kind="quarter",
        unit=unit,
        revision_policy=revision_policy,
    )
    if fiscal_quarter == 1:
        return direct
    if fiscal_quarter not in {2, 3, 4}:
        raise ValueError("Fiscal quarter must be between 1 and 4")
    if aggregation == "weighted_average" and direct.usable:
        return direct

    cumulative_kind: PeriodKind = {2: "half_year", 3: "nine_month", 4: "annual"}[
        fiscal_quarter
    ]
    previous_kind: PeriodKind = {2: "quarter", 3: "half_year", 4: "nine_month"}[
        fiscal_quarter
    ]
    cumulative = select_reported_value(
        key,
        label,
        candidate_tuple,
        period_end=period_end,
        period_kind=cumulative_kind,
        unit=unit,
        revision_policy=revision_policy,
    )
    prior_ends = {
        item.fact.period_end
        for item in candidate_tuple
        if item.fact.period_end < period_end
        and classify_period(item.fact) == previous_kind
        and cumulative.evidence
        and item.fact.period_start == cumulative.evidence[0].period_start
    }
    previous_end = max(prior_ends) if prior_ends else None
    previous = (
        select_reported_value(
            key,
            label,
            candidate_tuple,
            period_end=previous_end,
            period_kind=previous_kind,
            unit=unit,
            revision_policy=revision_policy,
        )
        if previous_end is not None
        else None
    )
    if aggregation == "weighted_average":
        derivation = _derive_weighted_average(
            key=key,
            label=label,
            period_end=period_end,
            unit=unit,
            cumulative=cumulative,
            previous=previous,
            formula=(
                f"weighted {cumulative_kind} less weighted {previous_kind}, "
                "using reported duration days"
            ),
        )
    else:
        derivation = _derive_difference(
            key=key,
            label=label,
            period_end=period_end,
            period_kind="quarter",
            unit=unit,
            minuend=cumulative,
            subtrahend=previous,
            formula=f"{cumulative_kind} YTD - {previous_kind} YTD",
        )

    if direct.usable and derivation.usable:
        if math.isclose(
            float(direct.value),
            float(derivation.value),
            rel_tol=1e-9,
            abs_tol=0.01,
        ):
            return AnalysisValue(
                **{
                    **asdict(direct),
                    "state": "reconciled",
                    "formula": "reported; reconciled to " + derivation.formula,
                    "evidence": direct.evidence + derivation.evidence,
                    "note": "Reported quarter equals the compatible YTD difference.",
                }
            )
        return AnalysisValue(
            key=key,
            label=label,
            value=None,
            unit=unit,
            period_end=period_end,
            period_kind="quarter",
            formula="reported compared with " + derivation.formula,
            version=ANALYSIS_VERSION,
            state="ambiguous",
            confidence="blocked",
            evidence=direct.evidence + derivation.evidence,
            note="Reported quarter conflicts with the compatible YTD difference.",
        )
    if direct.usable:
        return direct
    if derivation.usable:
        return derivation
    return direct if direct.state == "ambiguous" else derivation


def _derive_weighted_average(
    *,
    key: str,
    label: str,
    period_end: date,
    unit: str,
    cumulative: AnalysisValue,
    previous: AnalysisValue | None,
    formula: str,
) -> AnalysisValue:
    values = tuple(item for item in (cumulative, previous) if item is not None)
    evidence = tuple(reference for item in values for reference in item.evidence)
    if previous is None or not cumulative.usable or not previous.usable:
        return AnalysisValue(
            key=key,
            label=label,
            value=None,
            unit=unit,
            period_end=period_end,
            period_kind="quarter",
            formula=formula,
            version=ANALYSIS_VERSION,
            state=(
                "ambiguous"
                if any(item.state == "ambiguous" for item in values)
                else "missing"
            ),
            confidence="blocked",
            evidence=evidence,
            note="Compatible weighted-average source values are unavailable.",
        )
    cumulative_start = cumulative.evidence[0].period_start
    previous_start = previous.evidence[0].period_start
    if cumulative_start is None or previous_start != cumulative_start:
        return AnalysisValue(
            key=key,
            label=label,
            value=None,
            unit=unit,
            period_end=period_end,
            period_kind="quarter",
            formula=formula,
            version=ANALYSIS_VERSION,
            state="unexpected_period",
            confidence="blocked",
            evidence=evidence,
            note="Weighted-average inputs do not share one reporting-period start.",
        )
    cumulative_days = (cumulative.period_end - cumulative_start).days + 1
    previous_days = (previous.period_end - previous_start).days + 1
    quarter_days = cumulative_days - previous_days
    if quarter_days <= 0:
        return AnalysisValue(
            key=key,
            label=label,
            value=None,
            unit=unit,
            period_end=period_end,
            period_kind="quarter",
            formula=formula,
            version=ANALYSIS_VERSION,
            state="unexpected_period",
            confidence="blocked",
            evidence=evidence,
            note="Weighted-average source durations do not define a positive quarter.",
        )
    result = (
        float(cumulative.value) * cumulative_days
        - float(previous.value) * previous_days
    ) / quarter_days
    return AnalysisValue(
        key=key,
        label=label,
        value=result,
        unit=unit,
        period_end=period_end,
        period_kind="quarter",
        formula=formula,
        version=ANALYSIS_VERSION,
        state="derived",
        confidence="medium",
        evidence=evidence,
        note="Quarter weighted average derived from compatible cumulative averages.",
    )


def _derive_difference(
    *,
    key: str,
    label: str,
    period_end: date,
    period_kind: str,
    unit: str,
    minuend: AnalysisValue | None,
    subtrahend: AnalysisValue | None,
    formula: str,
) -> AnalysisValue:
    values = tuple(item for item in (minuend, subtrahend) if item is not None)
    evidence = tuple(reference for item in values for reference in item.evidence)
    if minuend is None or subtrahend is None or not minuend.usable or not subtrahend.usable:
        return AnalysisValue(
            key=key,
            label=label,
            value=None,
            unit=unit,
            period_end=period_end,
            period_kind=period_kind,
            formula=formula,
            version=ANALYSIS_VERSION,
            state="ambiguous" if any(item.state == "ambiguous" for item in values) else "missing",
            confidence="blocked",
            evidence=evidence,
            note="Compatible source values required by the formula are unavailable.",
        )
    return AnalysisValue(
        key=key,
        label=label,
        value=minuend.value - subtrahend.value,
        unit=unit,
        period_end=period_end,
        period_kind=period_kind,
        formula=formula,
        version=ANALYSIS_VERSION,
        state="derived",
        confidence="medium",
        evidence=evidence,
        note="Quarter-only value derived from compatible cumulative observations.",
    )


def _derive_measure(
    *,
    key: str,
    label: str,
    unit: str,
    period_end: date,
    formula: str,
    inputs: tuple[tuple[str, AnalysisValue], ...],
    calculate: Callable[[tuple[float, ...]], float],
) -> AnalysisValue:
    evidence = tuple(
        EvidenceReference(**{**asdict(reference), "role": role})
        for role, value in inputs
        for reference in value.evidence
    )
    if not all(value.usable for _, value in inputs):
        states = {value.state for _, value in inputs}
        return AnalysisValue(
            key=key,
            label=label,
            value=None,
            unit=unit,
            period_end=period_end,
            period_kind="quarter",
            formula=formula,
            version=ANALYSIS_VERSION,
            state="ambiguous" if "ambiguous" in states else "missing",
            confidence="blocked",
            evidence=evidence,
            note="One or more required inputs are unavailable or untrusted.",
        )
    numeric = tuple(float(value.value) for _, value in inputs)
    try:
        result = calculate(numeric)
    except ZeroDivisionError:
        return AnalysisValue(
            key=key,
            label=label,
            value=None,
            unit=unit,
            period_end=period_end,
            period_kind="quarter",
            formula=formula,
            version=ANALYSIS_VERSION,
            state="division_by_zero",
            confidence="blocked",
            evidence=evidence,
            note="The formula denominator is zero.",
        )
    confidence: Confidence = (
        "medium" if any(value.confidence == "medium" for _, value in inputs) else "high"
    )
    return AnalysisValue(
        key=key,
        label=label,
        value=result,
        unit=unit,
        period_end=period_end,
        period_kind="quarter",
        formula=formula,
        version=ANALYSIS_VERSION,
        state="derived",
        confidence=confidence,
        evidence=evidence,
        note="Calculated from the listed normalized inputs.",
    )


def analyze_company_quarter(
    facts: Iterable[FactObservation],
    *,
    company_name: str,
    period_end: date,
    fiscal_quarter: int,
    revision_policy: RevisionPolicy = "latest_corrected",
) -> CompanyAnalysis:
    fact_tuple = tuple(facts)
    if not fact_tuple:
        raise ValueError("At least one fact is required")
    cik = fact_tuple[0].cik
    if any(fact.cik != cik for fact in fact_tuple):
        raise ValueError("Analysis cannot mix facts from multiple CIKs")
    grouped = ranked_facts_by_metric(fact_tuple)
    previous_end = period_end.replace(year=period_end.year - 1)

    flow_labels = {
        "revenue": "Revenue",
        "operating_income": "Operating income",
        "net_income": "Net income",
        "diluted_weighted_average_shares": "Diluted weighted-average shares",
        "operating_cash_flow": "Operating cash flow",
        "capital_expenditure": "Capital expenditure",
        "share_repurchases": "Share repurchases",
        "share_based_compensation": "Share-based compensation",
        "depreciation_and_amortization": "Depreciation and amortization",
    }
    current: dict[str, AnalysisValue] = {}
    prior: dict[str, AnalysisValue] = {}
    for key, label in flow_labels.items():
        unit = "shares" if key == "diluted_weighted_average_shares" else "USD"
        current[key] = normalize_quarter_value(
            key,
            label,
            grouped.get(key, ()),
            period_end=period_end,
            fiscal_quarter=fiscal_quarter,
            unit=unit,
            revision_policy=revision_policy,
            aggregation=(
                "weighted_average"
                if key == "diluted_weighted_average_shares"
                else "additive"
            ),
        )
        prior[key] = normalize_quarter_value(
            key,
            label,
            grouped.get(key, ()),
            period_end=previous_end,
            fiscal_quarter=fiscal_quarter,
            unit=unit,
            revision_policy=revision_policy,
            aggregation=(
                "weighted_average"
                if key == "diluted_weighted_average_shares"
                else "additive"
            ),
        )

    instant_labels = {
        "cash_and_equivalents": "Cash and cash equivalents",
        "short_term_investments": "Short-term investments",
        "short_term_debt": "Short-term debt",
        "long_term_debt": "Long-term debt",
        "current_assets": "Current assets",
        "current_liabilities": "Current liabilities",
    }
    for key, label in instant_labels.items():
        current[key] = select_reported_value(
            key,
            label,
            grouped.get(key, ()),
            period_end=period_end,
            period_kind="instant",
            unit="USD",
            revision_policy=revision_policy,
        )
        prior[key] = select_reported_value(
            key,
            label,
            grouped.get(key, ()),
            period_end=previous_end,
            period_kind="instant",
            unit="USD",
            revision_policy=revision_policy,
        )

    operating_margin = _derive_measure(
        key="operating_margin",
        label="Operating margin",
        unit="percent",
        period_end=period_end,
        formula="operating_income / revenue * 100",
        inputs=(
            ("operating_income", current["operating_income"]),
            ("revenue", current["revenue"]),
        ),
        calculate=lambda values: values[0] / values[1] * 100,
    )
    prior_operating_margin = _derive_measure(
        key="operating_margin",
        label="Prior-year operating margin",
        unit="percent",
        period_end=previous_end,
        formula="operating_income / revenue * 100",
        inputs=(
            ("prior_operating_income", prior["operating_income"]),
            ("prior_revenue", prior["revenue"]),
        ),
        calculate=lambda values: values[0] / values[1] * 100,
    )
    measures = (
        _derive_measure(
            key="revenue_change_yoy",
            label="Revenue change year over year",
            unit="USD",
            period_end=period_end,
            formula="revenue_current - revenue_prior_year",
            inputs=(("current_revenue", current["revenue"]), ("prior_revenue", prior["revenue"])),
            calculate=lambda values: values[0] - values[1],
        ),
        _derive_measure(
            key="revenue_growth_yoy",
            label="Revenue growth year over year",
            unit="percent",
            period_end=period_end,
            formula="(revenue_current / revenue_prior_year - 1) * 100",
            inputs=(("current_revenue", current["revenue"]), ("prior_revenue", prior["revenue"])),
            calculate=lambda values: (values[0] / values[1] - 1) * 100,
        ),
        operating_margin,
        _derive_measure(
            key="operating_margin_change_yoy",
            label="Operating-margin change year over year",
            unit="percentage_points",
            period_end=period_end,
            formula="operating_margin_current - operating_margin_prior_year",
            inputs=(
                ("current_operating_margin", operating_margin),
                ("prior_operating_margin", prior_operating_margin),
            ),
            calculate=lambda values: values[0] - values[1],
        ),
        _derive_measure(
            key="net_margin",
            label="Net margin",
            unit="percent",
            period_end=period_end,
            formula="net_income / revenue * 100",
            inputs=(("net_income", current["net_income"]), ("revenue", current["revenue"])),
            calculate=lambda values: values[0] / values[1] * 100,
        ),
        _derive_measure(
            key="cash_conversion",
            label="Operating cash flow to net income",
            unit="ratio",
            period_end=period_end,
            formula="operating_cash_flow / net_income",
            inputs=(("operating_cash_flow", current["operating_cash_flow"]), ("net_income", current["net_income"])),
            calculate=lambda values: values[0] / values[1],
        ),
        _derive_measure(
            key="simplified_free_cash_flow",
            label="Simplified free cash flow",
            unit="USD",
            period_end=period_end,
            formula="operating_cash_flow - capital_expenditure",
            inputs=(("operating_cash_flow", current["operating_cash_flow"]), ("capital_expenditure", current["capital_expenditure"])),
            calculate=lambda values: values[0] - values[1],
        ),
        _derive_measure(
            key="net_liquidity",
            label="Net liquidity",
            unit="USD",
            period_end=period_end,
            formula="cash + short_term_investments - short_term_debt - long_term_debt",
            inputs=(
                ("cash", current["cash_and_equivalents"]),
                ("short_term_investments", current["short_term_investments"]),
                ("short_term_debt", current["short_term_debt"]),
                ("long_term_debt", current["long_term_debt"]),
            ),
            calculate=lambda values: values[0] + values[1] - values[2] - values[3],
        ),
        _derive_measure(
            key="working_capital",
            label="Working capital",
            unit="USD",
            period_end=period_end,
            formula="current_assets - current_liabilities",
            inputs=(("current_assets", current["current_assets"]), ("current_liabilities", current["current_liabilities"])),
            calculate=lambda values: values[0] - values[1],
        ),
        _derive_measure(
            key="working_capital_change_yoy",
            label="Working-capital change year over year",
            unit="USD",
            period_end=period_end,
            formula="(current_assets - current_liabilities) - (prior_current_assets - prior_current_liabilities)",
            inputs=(
                ("current_assets", current["current_assets"]),
                ("current_liabilities", current["current_liabilities"]),
                ("prior_current_assets", prior["current_assets"]),
                ("prior_current_liabilities", prior["current_liabilities"]),
            ),
            calculate=lambda values: (values[0] - values[1]) - (values[2] - values[3]),
        ),
        _derive_measure(
            key="diluted_share_change_yoy",
            label="Diluted weighted-average share change",
            unit="percent",
            period_end=period_end,
            formula="(diluted_shares_current / diluted_shares_prior_year - 1) * 100",
            inputs=(
                ("current_diluted_shares", current["diluted_weighted_average_shares"]),
                ("prior_diluted_shares", prior["diluted_weighted_average_shares"]),
            ),
            calculate=lambda values: (values[0] / values[1] - 1) * 100,
        ),
    )
    normalized = tuple(current[key] for key in (*flow_labels, *instant_labels))
    return CompanyAnalysis(
        cik=cik,
        company_name=company_name,
        period_end=period_end,
        fiscal_quarter=fiscal_quarter,
        revision_policy=revision_policy,
        normalized_facts=normalized,
        derived_measures=measures,
        unavailable_operating_metrics=(
            "total_payment_volume",
            "active_accounts",
            "payment_transactions",
            "transactions_per_active_account",
            "transaction_loss_rate",
        ),
    )


def analyze_paypal_quarter(
    facts: Iterable[FactObservation],
    *,
    company_name: str,
    period_end: date,
    fiscal_quarter: int,
    revision_policy: RevisionPolicy = "latest_corrected",
) -> CompanyAnalysis:
    """Compatibility wrapper for the original PayPal Stage 3 entry point."""
    return analyze_company_quarter(
        facts,
        company_name=company_name,
        period_end=period_end,
        fiscal_quarter=fiscal_quarter,
        revision_policy=revision_policy,
    )
