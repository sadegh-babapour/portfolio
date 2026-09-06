from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Statement = Literal["income", "balance", "cash_flow"]
ContextKind = Literal["instant", "duration"]

CANONICAL_METRIC_VERSION = "2026-09-05.1"


@dataclass(frozen=True, slots=True)
class ConceptCandidate:
    taxonomy: str
    concept: str
    priority: int = 100
    filer_cik: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalMetric:
    key: str
    label: str
    statement: Statement
    context_kind: ContextKind
    expected_units: tuple[str, ...]
    candidates: tuple[ConceptCandidate, ...]
    description: str


def _candidate(concept: str, priority: int = 100) -> ConceptCandidate:
    return ConceptCandidate("us-gaap", concept, priority)


CANONICAL_METRICS: tuple[CanonicalMetric, ...] = (
    CanonicalMetric(
        "revenue",
        "Revenue",
        "income",
        "duration",
        ("USD",),
        (
            _candidate("RevenueFromContractWithCustomerExcludingAssessedTax", 10),
            _candidate("Revenues", 20),
        ),
        "Top-line revenue recognized for the reporting period.",
    ),
    CanonicalMetric(
        "operating_income",
        "Operating income",
        "income",
        "duration",
        ("USD",),
        (_candidate("OperatingIncomeLoss", 10),),
        "Income or loss from operations before non-operating items.",
    ),
    CanonicalMetric(
        "net_income",
        "Net income",
        "income",
        "duration",
        ("USD",),
        (_candidate("NetIncomeLoss", 10), _candidate("ProfitLoss", 20)),
        "Consolidated net income or loss for the reporting period.",
    ),
    CanonicalMetric(
        "diluted_eps",
        "Diluted earnings per share",
        "income",
        "duration",
        ("USD/shares",),
        (_candidate("EarningsPerShareDiluted", 10),),
        "Net income attributable per diluted weighted-average share.",
    ),
    CanonicalMetric(
        "diluted_weighted_average_shares",
        "Diluted weighted-average shares",
        "income",
        "duration",
        ("shares",),
        (_candidate("WeightedAverageNumberOfDilutedSharesOutstanding", 10),),
        "Diluted weighted-average shares used in EPS.",
    ),
    CanonicalMetric(
        "cash_and_equivalents",
        "Cash and cash equivalents",
        "balance",
        "instant",
        ("USD",),
        (_candidate("CashAndCashEquivalentsAtCarryingValue", 10),),
        "Cash and cash-equivalent balance at period end.",
    ),
    CanonicalMetric(
        "short_term_investments",
        "Short-term investments",
        "balance",
        "instant",
        ("USD",),
        (
            _candidate("ShortTermInvestments", 10),
            _candidate("MarketableSecuritiesCurrent", 20),
        ),
        "Current investment securities available for liquidity analysis.",
    ),
    CanonicalMetric(
        "current_assets",
        "Current assets",
        "balance",
        "instant",
        ("USD",),
        (_candidate("AssetsCurrent", 10),),
        "Assets expected to be realized within the operating cycle.",
    ),
    CanonicalMetric(
        "current_liabilities",
        "Current liabilities",
        "balance",
        "instant",
        ("USD",),
        (_candidate("LiabilitiesCurrent", 10),),
        "Obligations due within the operating cycle.",
    ),
    CanonicalMetric(
        "total_assets",
        "Total assets",
        "balance",
        "instant",
        ("USD",),
        (_candidate("Assets", 10),),
        "Total consolidated assets at period end.",
    ),
    CanonicalMetric(
        "total_liabilities",
        "Total liabilities",
        "balance",
        "instant",
        ("USD",),
        (_candidate("Liabilities", 10),),
        "Total consolidated liabilities at period end.",
    ),
    CanonicalMetric(
        "stockholders_equity",
        "Stockholders' equity",
        "balance",
        "instant",
        ("USD",),
        (_candidate("StockholdersEquity", 10),),
        "Equity attributable to stockholders at period end.",
    ),
    CanonicalMetric(
        "short_term_debt",
        "Short-term debt",
        "balance",
        "instant",
        ("USD",),
        (
            _candidate("ShortTermBorrowings", 10),
            _candidate("LongTermDebtCurrent", 20),
        ),
        "Borrowings and current maturities due within one year.",
    ),
    CanonicalMetric(
        "long_term_debt",
        "Long-term debt",
        "balance",
        "instant",
        ("USD",),
        (_candidate("LongTermDebtNoncurrent", 10),),
        "Borrowings classified as non-current.",
    ),
    CanonicalMetric(
        "operating_cash_flow",
        "Operating cash flow",
        "cash_flow",
        "duration",
        ("USD",),
        (_candidate("NetCashProvidedByUsedInOperatingActivities", 10),),
        "Net cash provided by or used in operating activities.",
    ),
    CanonicalMetric(
        "capital_expenditure",
        "Capital expenditure",
        "cash_flow",
        "duration",
        ("USD",),
        (_candidate("PaymentsToAcquirePropertyPlantAndEquipment", 10),),
        "Cash paid to acquire property, plant, and equipment.",
    ),
    CanonicalMetric(
        "share_repurchases",
        "Share repurchases",
        "cash_flow",
        "duration",
        ("USD",),
        (_candidate("PaymentsForRepurchaseOfCommonStock", 10),),
        "Cash paid to repurchase common shares.",
    ),
    CanonicalMetric(
        "share_based_compensation",
        "Share-based compensation",
        "cash_flow",
        "duration",
        ("USD",),
        (_candidate("ShareBasedCompensation", 10),),
        "Non-cash share-based compensation recognized in the cash-flow reconciliation.",
    ),
    CanonicalMetric(
        "depreciation_and_amortization",
        "Depreciation and amortization",
        "cash_flow",
        "duration",
        ("USD",),
        (
            _candidate("DepreciationDepletionAndAmortization", 10),
            _candidate("DepreciationDepletionAndAmortizationPropertyPlantAndEquipment", 20),
        ),
        "Non-cash depreciation and amortization in the operating cash-flow reconciliation.",
    ),
)


METRICS_BY_KEY = {metric.key: metric for metric in CANONICAL_METRICS}


def metric_for_fact(
    *,
    cik: str,
    taxonomy: str,
    concept: str,
    unit: str,
    context_kind: str,
) -> tuple[CanonicalMetric, ConceptCandidate] | None:
    """Resolve an exact raw tag; labels and fuzzy matching are deliberately excluded."""
    matches: list[tuple[CanonicalMetric, ConceptCandidate]] = []
    for metric in CANONICAL_METRICS:
        if unit not in metric.expected_units or context_kind != metric.context_kind:
            continue
        for candidate in metric.candidates:
            if candidate.taxonomy != taxonomy or candidate.concept != concept:
                continue
            if candidate.filer_cik is not None and candidate.filer_cik != cik:
                continue
            matches.append((metric, candidate))
    scoped_matches = [match for match in matches if match[1].filer_cik == cik]
    candidates = scoped_matches or matches
    if len({metric.key for metric, _ in candidates}) > 1:
        raise ValueError(f"Ambiguous canonical mapping for {taxonomy}:{concept} [{unit}]")
    return min(candidates, key=lambda match: match[1].priority) if candidates else None
