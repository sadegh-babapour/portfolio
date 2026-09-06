from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Literal

from .contracts import DocumentSnapshot, FilingMetadata


PEER_OUTLIER_REVIEW_VERSION = "payments-outlier-review-2026-09-06.1"
GateStatus = Literal["blocked", "direction_only", "cleared"]
FindingEffect = Literal[
    "operating",
    "acquisition",
    "divestiture",
    "presentation",
    "denominator",
    "timing",
    "one_time",
]


@dataclass(frozen=True, slots=True)
class FilingEvidenceRule:
    evidence_id: str
    category: FindingEffect
    statement: str
    pattern: str


@dataclass(frozen=True, slots=True)
class MetricGateSpec:
    metric: str
    status: GateStatus
    reason: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PeerOutlierSpec:
    cik: str
    ticker: str
    accession_number: str
    report_period_end: str
    rules: tuple[FilingEvidenceRule, ...]
    gates: tuple[MetricGateSpec, ...]


@dataclass(frozen=True, slots=True)
class FilingEvidenceFinding:
    evidence_id: str
    category: FindingEffect
    statement: str
    excerpt: str
    source_url: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class MetricComparisonGate:
    metric: str
    status: GateStatus
    reason: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PeerOutlierReview:
    cik: str
    ticker: str
    accession_number: str
    report_period_end: str
    model_version: str
    review_status: Literal["complete", "incomplete"]
    missing_evidence_ids: tuple[str, ...]
    findings: tuple[FilingEvidenceFinding, ...]
    gates: tuple[MetricComparisonGate, ...]
    publication_allowed: bool = False


PEER_OUTLIER_SPECS: tuple[PeerOutlierSpec, ...] = (
    PeerOutlierSpec(
        cik="0001512673",
        ticker="XYZ",
        accession_number="0001628280-26-053368",
        report_period_end="2026-06-30",
        rules=(
            FilingEvidenceRule(
                "xyz_cash_timing",
                "timing",
                "Operating cash flow included a material period-end working-capital benefit.",
                r"cash provided by operating activities was \$2\.0 billion.{0,1500}"
                r"Changes in other assets and liabilities.{0,180}\$617\.1 million"
                r".{0,180}timing of period end",
            ),
            FilingEvidenceRule(
                "xyz_cash_noncash",
                "denominator",
                "Operating cash flow was reconciled from a net loss using large non-cash adjustments.",
                r"cash provided by operating activities was \$2\.0 billion.{0,300}"
                r"net loss of \$221\.5 million.{0,300}non-cash expenses of \$2\.3 billion",
            ),
            FilingEvidenceRule(
                "xyz_bitcoin_remeasurement",
                "denominator",
                "Bitcoin fair-value remeasurement changed from a prior-year gain to a current-year loss, depressing the net-income denominator.",
                r"recognized losses of \$88\.5 million and \$261\.3 million.{0,300}"
                r"recognized gains of \$212\.2 million and \$118\.8 million",
            ),
            FilingEvidenceRule(
                "xyz_presentation_recast",
                "presentation",
                "Revenue-line reclassifications did not change total revenue, gross profit, operating income, or net income.",
                r"reclassifications related to the presentation of revenues and cost of revenues"
                r" had no impact on total revenues, gross profit, operating income, or net income",
            ),
        ),
        gates=(
            MetricGateSpec(
                "cash_conversion",
                "blocked",
                "Do not compare the 11.52x ratio: its numerator contains period-end timing benefits and its net-income denominator contains large non-cash bitcoin remeasurement effects.",
                ("xyz_cash_timing", "xyz_cash_noncash", "xyz_bitcoin_remeasurement"),
            ),
        ),
    ),
    PeerOutlierSpec(
        cik="0000798354",
        ticker="FISV",
        accession_number="0000798354-26-000031",
        report_period_end="2026-06-30",
        rules=(
            FilingEvidenceRule(
                "fisv_revenue_decline",
                "operating",
                "The revenue decline was attributed primarily to lower data-and-analytics sales and license revenue.",
                r"Total revenue decreased \$224 million, or 4%.{0,260}"
                r"primarily due to lower data and analytics sales and license revenue",
            ),
            FilingEvidenceRule(
                "fisv_margin_operations",
                "operating",
                "Lower high-margin sales and higher personnel and infrastructure costs materially reduced operating margin.",
                r"Total operating margin decreased to 19\.2%.{0,500}"
                r"decrease in high margin license revenue and data and analytics sales.{0,350}"
                r"personnel costs.{0,250}technology infrastructure expenses",
            ),
            FilingEvidenceRule(
                "fisv_transformation_costs",
                "one_time",
                "The quarter also included a material One Fiserv transformation-program cost overlay.",
                r"operating loss in the second quarter.{0,220}"
                r"One Fiserv transformation program of \$187 million",
            ),
            FilingEvidenceRule(
                "fisv_held_for_sale",
                "divestiture",
                "A student-loan servicing divestiture was classified as held for sale during the quarter.",
                r"pending divestiture met the criteria to be classified as held for sale",
            ),
        ),
        gates=(
            MetricGateSpec(
                "operating_margin_change_yoy",
                "direction_only",
                "Treat deterioration as real, but do not rank the 11.57-point magnitude until the One Fiserv transformation costs are separated from recurring operations.",
                ("fisv_margin_operations", "fisv_transformation_costs"),
            ),
        ),
    ),
    PeerOutlierSpec(
        cik="0001123360",
        ticker="GPN",
        accession_number="0001123360-26-000084",
        report_period_end="2026-06-30",
        rules=(
            FilingEvidenceRule(
                "gpn_worldpay_revenue",
                "acquisition",
                "The Worldpay acquisition was the primary cause of the reported revenue increase.",
                r"Consolidated revenues for the three months ended June 30, 2026 increased"
                r".{0,450}primarily due to additional revenues from the acquisition of the Worldpay business",
            ),
            FilingEvidenceRule(
                "gpn_worldpay_margin",
                "acquisition",
                "Acquired-intangible amortization and acquisition/integration expenses drove the operating-margin decline.",
                r"Consolidated operating income and operating margin.{0,220}decreased"
                r".{0,300}amortization expense related to acquired Worldpay intangible assets"
                r".{0,180}acquisition and integration expenses",
            ),
            FilingEvidenceRule(
                "gpn_issuer_discontinued",
                "divestiture",
                "Issuer Solutions was sold and recast as discontinued operations for every period presented.",
                r"completed the sale of our Issuer Solutions business.{0,500}"
                r"reflected as discontinued operations for all periods presented",
            ),
            FilingEvidenceRule(
                "gpn_cash_scope",
                "presentation",
                "The consolidated cash-flow statement includes both continuing and discontinued operations.",
                r"consolidated statements of cash flows include cash flows from discontinued operations for all periods presented",
            ),
            FilingEvidenceRule(
                "gpn_cash_transaction",
                "timing",
                "Operating cash flow included transaction payments and liabilities assumed with Worldpay.",
                r"Operating cash flows for the six months ended June 30, 2026 reflect the payment of costs"
                r".{0,260}acquisition of Worldpay and divestiture of our Issuer Solutions business"
                r".{0,180}liabilities assumed in the acquisition of Worldpay",
            ),
        ),
        gates=(
            MetricGateSpec(
                "revenue_growth_yoy",
                "blocked",
                "Exclude the 68.63% headline growth rate because Worldpay was added to the current-period base.",
                ("gpn_worldpay_revenue",),
            ),
            MetricGateSpec(
                "operating_margin_change_yoy",
                "blocked",
                "Exclude the 9.82-point decline from peer ranking because purchase-accounting amortization and acquisition/integration expenses materially changed the cost base.",
                ("gpn_worldpay_margin",),
            ),
            MetricGateSpec(
                "cash_conversion",
                "blocked",
                "Exclude the 51.08x ratio because cash flow includes discontinued operations and transaction-related payments and assumed liabilities.",
                ("gpn_cash_scope", "gpn_cash_transaction", "gpn_issuer_discontinued"),
            ),
        ),
    ),
    PeerOutlierSpec(
        cik="0001794669",
        ticker="FOUR",
        accession_number="0001794669-26-000045",
        report_period_end="2026-06-30",
        rules=(
            FilingEvidenceRule(
                "four_growth_mix",
                "acquisition",
                "Gross revenue growth combined genuine volume growth with recent acquisitions.",
                r"Gross revenue increased by \$329 million, or 34%.{0,500}"
                r"increase in volume of \$11 billion, or 22%.{0,180}recent acquisitions",
            ),
            FilingEvidenceRule(
                "four_global_blue",
                "acquisition",
                "Global Blue created the new tax-free-shopping revenue line in the comparison period.",
                r"TFS revenue increased by \$117 million.{0,120}result of the acquisition of Global Blue",
            ),
            FilingEvidenceRule(
                "four_net_revenue_lens",
                "presentation",
                "Shift4 separately emphasizes gross revenue less network fees, limiting comparability of raw revenue across processors.",
                r"Gross revenue less network fees increased by \$211 million, or 51%"
                r".{0,220}impact of recent acquisitions",
            ),
        ),
        gates=(
            MetricGateSpec(
                "revenue_growth_yoy",
                "direction_only",
                "Growth direction is supported by 22% volume growth, but do not rank the 34.06% headline rate because acquisitions and network-fee presentation affect the comparison.",
                ("four_growth_mix", "four_global_blue", "four_net_revenue_lens"),
            ),
        ),
    ),
)


def _evidence_excerpt(text: str, match: re.Match[str], *, limit: int = 1_600) -> str:
    start = max(0, match.start() - 180)
    end = min(len(text), match.end() + 180)
    return " ".join(text[start:end].split())[:limit]


def review_peer_outlier_filing(
    filing: FilingMetadata,
    snapshots: Iterable[DocumentSnapshot],
    *,
    spec: PeerOutlierSpec,
) -> PeerOutlierReview:
    """Resolve a filing-specific review only when every cited rule is evidenced."""
    identity_matches = (
        filing.cik == spec.cik
        and filing.accession_number == spec.accession_number
        and filing.report_period_end is not None
        and filing.report_period_end.isoformat() == spec.report_period_end
    )
    findings: list[FilingEvidenceFinding] = []
    missing: list[str] = []
    documents = tuple(snapshots)
    for rule in spec.rules:
        located: tuple[DocumentSnapshot, re.Match[str]] | None = None
        for snapshot in documents:
            search_text = " ".join(snapshot.text.split())
            match = re.search(rule.pattern, search_text, re.IGNORECASE | re.DOTALL)
            if match is not None:
                located = (snapshot, match)
                break
        if located is None:
            missing.append(rule.evidence_id)
            continue
        snapshot, match = located
        search_text = " ".join(snapshot.text.split())
        findings.append(
            FilingEvidenceFinding(
                evidence_id=rule.evidence_id,
                category=rule.category,
                statement=rule.statement,
                excerpt=_evidence_excerpt(search_text, match),
                source_url=snapshot.document.sec_url,
                source_sha256=snapshot.content_sha256,
            )
        )
    if not identity_matches:
        missing.insert(0, "filing_identity")

    complete = not missing
    gates = tuple(
        MetricComparisonGate(
            metric=gate.metric,
            status=gate.status if complete else "blocked",
            reason=(
                gate.reason
                if complete
                else "Structural review is incomplete; exact peer comparison remains blocked."
            ),
            evidence_ids=gate.evidence_ids if complete else (),
        )
        for gate in spec.gates
    )
    return PeerOutlierReview(
        cik=spec.cik,
        ticker=spec.ticker,
        accession_number=spec.accession_number,
        report_period_end=spec.report_period_end,
        model_version=PEER_OUTLIER_REVIEW_VERSION,
        review_status="complete" if complete else "incomplete",
        missing_evidence_ids=tuple(missing),
        findings=tuple(findings),
        gates=gates,
    )


def outlier_spec(cik: str) -> PeerOutlierSpec:
    return next(spec for spec in PEER_OUTLIER_SPECS if spec.cik == cik)
