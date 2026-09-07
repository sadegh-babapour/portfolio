from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .contracts import DocumentSnapshot, FilingMetadata
from .peer_reviews import GateStatus, MetricComparisonGate


SECTOR_FILING_REVIEW_VERSION = "sector-filing-review-2026-09-07.1"
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
class SectorEvidenceRule:
    evidence_id: str
    category: FindingEffect
    statement: str
    pattern: str


@dataclass(frozen=True, slots=True)
class SectorMetricGateSpec:
    metric: str
    status: GateStatus
    reason: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SectorFilingReviewSpec:
    industry_key: str
    cik: str
    ticker: str
    accession_number: str
    report_period_end: str
    primary_document: str
    source_sha256: str
    rules: tuple[SectorEvidenceRule, ...]
    gates: tuple[SectorMetricGateSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class SectorEvidenceFinding:
    evidence_id: str
    category: FindingEffect
    statement: str
    excerpt: str
    source_url: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class SectorFilingReview:
    industry_key: str
    cik: str
    ticker: str
    accession_number: str
    report_period_end: str
    model_version: str
    review_status: Literal["complete", "incomplete"]
    missing_evidence_ids: tuple[str, ...]
    findings: tuple[SectorEvidenceFinding, ...]
    gates: tuple[MetricComparisonGate, ...]
    publication_allowed: bool


def _rule(
    evidence_id: str,
    category: FindingEffect,
    statement: str,
    pattern: str,
) -> SectorEvidenceRule:
    return SectorEvidenceRule(evidence_id, category, statement, pattern)


def _gate(
    metric: str,
    status: GateStatus,
    reason: str,
    *evidence_ids: str,
) -> SectorMetricGateSpec:
    return SectorMetricGateSpec(metric, status, reason, tuple(evidence_ids))


SECTOR_FILING_SPECS: tuple[SectorFilingReviewSpec, ...] = (
    SectorFilingReviewSpec(
        "digital_advertising", "0001652044", "GOOGL", "0001652044-26-000071",
        "2026-06-30", "goog-20260630.htm",
        "fecfbc2683f630380b17937278ce3745eca150eb90e21a945fd6b78fe19728c7",
        (_rule("googl_infrastructure", "operating", "Data-center investment and obligations materially expanded the infrastructure base behind current growth.", r"Accrued purchases of property and equipment.{0,160}16,196"),),
    ),
    SectorFilingReviewSpec(
        "digital_advertising", "0001326801", "META", "0001628280-26-050705",
        "2026-06-30", "meta-20260630.htm",
        "b294c4f08edb78d0700cb82c86a0141a2cef38e4f1c2bb02b16ff1ce564a8492",
        (
            _rule("meta_restructuring", "one_time", "Second-quarter costs include severance for the May 2026 reduction of about 8,000 employees.", r"\$1\.18 billion of severance expenses.{0,100}May 2026 headcount reduction.{0,100}8,000 employees"),
            _rule("meta_data_center_venture", "presentation", "A 20%-owned data-center venture carries large funding and future lease commitments outside simple capital-expenditure comparisons.", r"co-develop a data center campus in Louisiana.{0,600}20% membership interest.{0,900}\$27 billion"),
        ),
        (_gate("operating_margin_change_yoy", "direction_only", "Severance and infrastructure scaling alter the current cost base; retain direction only.", "meta_restructuring", "meta_data_center_venture"),),
    ),
    SectorFilingReviewSpec(
        "digital_advertising", "0001564408", "SNAP", "0001564408-26-000052",
        "2026-06-30", "snap-20260630.htm",
        "90678ffadcfcd4c29a0ae0ab15f57b4a290e93ce35eebb72de951fe7bab7547a",
        (_rule("snap_operating_improvement", "operating", "Revenue increased while the reported operating loss narrowed year over year.", r"Revenue.{0,100}1,598,993.{0,100}1,344,930.{0,500}Operating loss.{0,100}\(170,721\).{0,100}\(259,676\)"),),
        (_gate("cash_conversion", "blocked", "A cash-conversion ratio with a net-loss denominator is not economically comparable.", "snap_operating_improvement"),),
    ),
    SectorFilingReviewSpec(
        "digital_advertising", "0001506293", "PINS", "0001506293-26-000104",
        "2026-06-30", "pins-20260630.htm",
        "4563177b862ccf2112ef6a3172a0677e3f5ec66143380f28a6242af5f4f31768",
        (
            _rule("pins_repurchase", "denominator", "A new $3.5 billion repurchase authorization followed cancellation of the prior program.", r"authorized a new stock repurchase program of up to \$3,500\.0 million.{0,180}March 2026 program.{0,180}canceled the November 2024 program"),
            _rule("pins_presentation", "presentation", "Prior-period amounts were reclassified to conform with the current presentation.", r"reclassified certain amounts in prior periods to conform with current presentation"),
        ),
        (_gate("cash_conversion", "blocked", "The negative net-income denominator makes the cash-conversion magnitude unsuitable for comparison.", "pins_repurchase"),),
    ),
    SectorFilingReviewSpec(
        "digital_advertising", "0001713445", "RDDT", "0001713445-26-000100",
        "2026-06-30", "rddt-20260630.htm",
        "00ee5071b9ee6cdb65bad04c3e41d0e60b3afc47224dfe8f40b15444e8c88f48",
        (_rule("rddt_metric_definition", "operating", "Reddit defines DAUq from identifiable daily visits and discloses methodology risk rather than treating all traffic as equivalent.", r"define a daily active unique.{0,220}visited a page on the Reddit website.{0,180}24-hour period"),),
    ),
    SectorFilingReviewSpec(
        "airlines", "0000027904", "DAL", "0000027904-26-000031", "2026-06-30",
        "dal-20260630.htm", "74cdc4e02784a0c1cffb55b87cae88f319f92ef283a075c1268db523f9fc9fe6",
        (_rule("dal_fuel_capacity", "operating", "Higher fuel consumption accompanied increased capacity, while fuel prices reduced cash-flow comparability.", r"Fuel consumption was higher.{0,180}increase in capacity.{0,220}elevated jet fuel costs"),),
    ),
    SectorFilingReviewSpec(
        "airlines", "0000100517", "UAL", "0000100517-26-000139", "2026-06-30",
        "ual-20260630.htm", "04dcb87990451c625da5c99ff2cb89c491fa8a1d291c30b5551347ead7770c83",
        (_rule("ual_fuel_and_flying", "operating", "Fuel expense rose primarily from higher price per gallon and increased flight activity.", r"Aircraft fuel expense increased \$2\.3 billion, or 84\.1%.{0,180}higher average price per gallon.{0,100}increased flight activity"),),
    ),
    SectorFilingReviewSpec(
        "airlines", "0000006201", "AAL", "0000006201-26-000052", "2026-06-30",
        "aal-20260630.htm", "e9e9f0c885958da6c767f0af5616879f4e6a7df748d626ffaf6dc35ed633b07e",
        (_rule("aal_small_profit", "denominator", "Quarterly net income was small relative to operating cash flow, making the cash-conversion ratio unstable.", r"Income \(loss\) before income taxes 107 838 \(369\) 189.{0,180}Net income \(loss\) \$ 71 \$ 599"),),
        (_gate("cash_conversion", "blocked", "The 6.63x magnitude is dominated by a small $71 million quarterly net-income denominator.", "aal_small_profit"),),
    ),
    SectorFilingReviewSpec(
        "airlines", "0000092380", "LUV", "0000092380-26-000077", "2026-06-30",
        "luv-20260630.htm", "6175c676bbabce1be2ee18fe5a73db35ff2308006225533287db27bc8180cd54",
        (_rule("luv_fleet_timing", "timing", "Boeing certification and delivery delays repeatedly changed Southwest's capacity plans.", r"Boeing.s delivery delays.{0,140}replanned its capacity and delivery expectations multiple times"),),
    ),
    SectorFilingReviewSpec(
        "airlines", "0000766421", "ALK", "0000766421-26-000041", "2026-06-30",
        "alk-20260630.htm", "ec82ace551f0f07a585fd9999727083624602c33ecae3ba3204131e64151bdca",
        (
            _rule("alk_hawaiian_integration", "acquisition", "Special items were primarily Hawaiian Airlines integration costs.", r"primarily associated with the integration of Hawaiian Airlines.{0,220}employee-related costs.{0,120}technology costs"),
            _rule("alk_fuel_and_operations", "operating", "The margin decline also reflects higher fuel, labor, and operating costs alongside revenue growth.", r"Revenue increased 9\.7%.{0,500}CASMex increased 6\.5%"),
        ),
        (
            _gate("operating_margin_change_yoy", "direction_only", "Underlying cost pressure overlaps Hawaiian integration and one-time costs; retain deterioration direction only.", "alk_hawaiian_integration", "alk_fuel_and_operations"),
            _gate("cash_conversion", "blocked", "The net-loss denominator makes the negative cash-conversion ratio unsuitable for ranking.", "alk_hawaiian_integration"),
        ),
    ),
    SectorFilingReviewSpec(
        "energy", "0000034088", "XOM", "0000034088-26-000093", "2026-06-30",
        "xom-20260630.htm", "a258b9e876acf7c68dd26a64d1cc51dbe9b6aae76fd1b6ad5b37c83e5721de13",
        (_rule("xom_price_and_trading", "presentation", "Commodity trading is net-presented in revenue and produced a large swing in realized and unrealized results.", r"Commodity contracts held for trading purposes are presented.{0,160}net basis.{0,220}losses of \$2\.3 billion and gains of \$534 million"),),
        (_gate("revenue_growth_yoy", "direction_only", "Commodity prices and net-presented trading swings dominate the consolidated revenue-growth magnitude.", "xom_price_and_trading"),),
    ),
    SectorFilingReviewSpec(
        "energy", "0000093410", "CVX", "0000093410-26-000167", "2026-06-30",
        "cvx-20260630.htm", "c27660320ba182227f1262ec6ad31af9a2e30d11fec6253bcc3a8be63d5f0133",
        (_rule("cvx_hess", "acquisition", "The filing identifies realization of benefits from the Hess acquisition as a material comparability factor.", r"anticipated benefits from the acquisition of Hess Corporation"),),
        (_gate("revenue_growth_yoy", "direction_only", "Hess changed the production and revenue base; retain growth direction but not the consolidated magnitude.", "cvx_hess"),),
    ),
    SectorFilingReviewSpec(
        "energy", "0001163165", "COP", "0001163165-26-000032", "2026-06-30",
        "cop-20260630.htm", "4b9d0c090676f327c97943d9b629b33846a88bfe5fb615478b7c5d9c2482ed83",
        (_rule("cop_realized_prices", "operating", "Higher crude realized prices, lower gas prices, and unhedged exposure explain why consolidated growth is price-sensitive.", r"Average Realized Prices.{0,220}Crude.{0,120}99\.40.{0,120}64\.23.{0,260}Gas.{0,120}2\.58.{0,120}4\.16"),),
        (_gate("revenue_growth_yoy", "direction_only", "The magnitude primarily reflects commodity-price changes rather than a like-for-like operating-volume comparison.", "cop_realized_prices"),),
    ),
    SectorFilingReviewSpec(
        "energy", "0000797468", "OXY", "0001628280-26-053388", "2026-06-30",
        "oxy-20260630.htm", "b16b1e489c310ad80fb8559a3aa6b1a69dab2d0c1f75f7ebb8f7e9f614b9e08f",
        (
            _rule("oxy_discontinued", "divestiture", "Discontinued operations contributed materially to six-month net income and changed the denominator base.", r"Discontinued operations, net of tax.{0,100}3,119.{0,100}245"),
            _rule("oxy_derivatives", "timing", "Marketing derivative cash settlements run through operating cash flow while fair-value changes run through earnings.", r"Changes in fair value will impact.{0,180}earnings through mark-to-market.{0,300}Cash settlements related to marketing derivatives are presented in operating cash flows"),
        ),
        (_gate("cash_conversion", "blocked", "Discontinued-operation income and derivative settlement timing make the consolidated cash-conversion magnitude non-comparable.", "oxy_discontinued", "oxy_derivatives"),),
    ),
    SectorFilingReviewSpec(
        "energy", "0000821189", "EOG", "0000821189-26-000149", "2026-06-30",
        "eog-20260630.htm", "831050a6a6a7ffd9524f5261ef1ad38c26b2710a65cbef3b6f8fa222669ec570",
        (_rule("eog_encino", "acquisition", "The August 2025 Encino acquisition changed EOG's production and revenue base.", r"On August 1, 2025, EOG acquired.{0,180}Encino.{0,220}\$4,471 million"),),
        (_gate("revenue_growth_yoy", "direction_only", "Encino and commodity prices overlap organic production growth; retain direction only.", "eog_encino"),),
    ),
    SectorFilingReviewSpec(
        "connectivity", "0000732712", "VZ", "0000732712-26-000046", "2026-06-30",
        "vz-20260630.htm", "bef955f7946430f4463a1bc5ab383faeff8d9fec39880d628621885dfd611eb7",
        (_rule("vz_frontier", "acquisition", "Fiber growth includes Frontier while postpaid revenue includes acquisition-related discounts and outage credits.", r"fiber broadband revenue.{0,140}inclusion of Frontier results.{0,300}postpaid revenue.{0,180}acquisition related discounts"),),
        (_gate("revenue_growth_yoy", "direction_only", "Frontier changed the consolidated revenue base and customer credits affected the quarter; retain direction only.", "vz_frontier"),),
    ),
    SectorFilingReviewSpec(
        "connectivity", "0000732717", "T", "0000732717-26-000297", "2026-06-30",
        "t-20260630.htm", "863666dc564189add1f0eda2ccf30652bacd7f87ff59307ea783dac680d77254",
        (_rule("t_lumen", "acquisition", "AT&T acquired Lumen's mass-markets fiber business during the comparison period.", r"On February 2, 2026, we acquired substantially all of Lumen.s Mass Markets fiber business"),),
        (_gate("revenue_growth_yoy", "direction_only", "The Lumen fiber acquisition changed the comparison base; retain direction only.", "t_lumen"),),
    ),
    SectorFilingReviewSpec(
        "connectivity", "0001283699", "TMUS", "0001283699-26-000101", "2026-06-30",
        "tmus-20260630.htm", "31e2eb999ef55b6a7fa59292dd457a089bd3084a6c1feeeffea3c046f480cde2",
        (_rule("tmus_uscellular", "acquisition", "UScellular integration is expected to require $2.6 billion of costs while delivering future synergies.", r"total costs to achieve.{0,100}\$2\.6 billion.{0,180}\$1\.5 billion of UScellular merger-related costs"),),
        (
            _gate("revenue_growth_yoy", "direction_only", "UScellular changed the service and equipment revenue base; retain growth direction only.", "tmus_uscellular"),
            _gate("operating_margin_change_yoy", "direction_only", "Merger and restructuring costs overlap the operating-margin movement.", "tmus_uscellular"),
        ),
    ),
    SectorFilingReviewSpec(
        "connectivity", "0001091667", "CHTR", "0001091667-26-000052", "2026-06-30",
        "chtr-20260630.htm", "c70eeee38a905bf68ea3056faddf6827b69fd54120cfe0a0cc6d3fcbbcd51fa4",
        (_rule("chtr_merger_costs", "one_time", "Cox transaction costs were separately identified and modest relative to operating expenses.", r"Merger and acquisition costs.{0,180}Cox Transactions.{0,160}advisory, legal and accounting fees"),),
    ),
    SectorFilingReviewSpec(
        "connectivity", "0001166691", "CMCSA", "0001628280-26-049360", "2026-06-30",
        "cmcsa-20260630.htm", "c390b896c81b540cb5525846ed6c258fdd757fa2035858511739b4e91229a479",
        (_rule("cmcsa_versant", "divestiture", "The January 2026 Versant separation changed the consolidated base but was not presented as discontinued operations.", r"January 2, 2026.{0,500}Versant Separation.{0,900}did not meet the criteria to be presented as a discontinued operation"),),
        (
            _gate("revenue_growth_yoy", "blocked", "The Versant separation changed the consolidated revenue base without discontinued-operation recasting.", "cmcsa_versant"),
            _gate("operating_margin_change_yoy", "blocked", "The separated media cost and revenue base prevents a like-for-like consolidated margin comparison.", "cmcsa_versant"),
        ),
    ),
    SectorFilingReviewSpec(
        "brokerage", "0001783879", "HOOD", "0001783879-26-000114", "2026-06-30",
        "hood-20260630.htm", "454b499aaf20768afba029cc336539b37c3aa3b79aef20ab5cbced68769616fc",
        (_rule("hood_cash_reallocation", "presentation", "More than $6 billion moved from off-balance-sheet sweep balances into customer free-credit cash to fund margin lending.", r"over \$6 billion of Cash Sweep balances moving to Cash and Deposits.{0,120}customer free credit balances"),),
        (_gate("cash_conversion", "blocked", "Customer-cash reallocation and broker-dealer balance mechanics make the generic operating-cash ratio non-comparable.", "hood_cash_reallocation"),),
    ),
    SectorFilingReviewSpec(
        "brokerage", "0001679788", "COIN", "0001679788-26-000088", "2026-06-30",
        "coin-20260630.htm", "6f3db6aeb84e14d70e5376fc83e5ac6b57c10798ee8ec6fa1c9a3a249240060a",
        (_rule("coin_acquisition", "acquisition", "A $4.3 billion business combination added acquired operations and substantial stock consideration.", r"Total purchase consideration.{0,160}4,294,552.{0,900}business combination under the acquisition method"),),
        (
            _gate("revenue_growth_yoy", "direction_only", "Acquired operations and crypto activity mix affect the revenue comparison; retain decline direction only.", "coin_acquisition"),
            _gate("operating_margin_change_yoy", "direction_only", "Purchase accounting and crypto fair-value effects overlap the margin movement.", "coin_acquisition"),
        ),
    ),
    SectorFilingReviewSpec(
        "brokerage", "0001381197", "IBKR", "0001381197-26-000147", "2026-06-30",
        "ibkr-20260630.htm", "63e7983f969c51df92519a96355998f2e8a1020e7d747781125d7c9d3c9cd45a",
        (_rule("ibkr_interest_mix", "operating", "Net revenue combines commissions with net interest income, while principal transactions are net fair-value gains and losses.", r"Total net interest income.{0,100}1,057.{0,100}860.{0,180}Total net revenues"),),
    ),
    SectorFilingReviewSpec(
        "brokerage", "0000316709", "SCHW", "0000316709-26-000031", "2026-06-30",
        "schw-20260630.htm", "a14014a9c4b748097ac1bd52de634b4650407a9d6da1d2d8376bac3ef726f1f5",
        (_rule("schw_forge", "acquisition", "Schwab acquired Forge in March 2026 and includes its results from that date.", r"On March 2, 2026, Schwab completed its acquisition of Forge.{0,240}\$636 million.{0,700}results of operations for Forge beginning on March 2, 2026"),),
        (_gate("revenue_growth_yoy", "direction_only", "Forge and changing client-cash/net-interest economics overlap the consolidated revenue-growth magnitude.", "schw_forge"),),
    ),
    SectorFilingReviewSpec(
        "brokerage", "0001397911", "LPLA", "0001628280-26-051542", "2026-06-30",
        "lpla-20260630.htm", "c501769770841560ccc8e18ada0af1980ef70a6857e54abc05ffcdd982cb6ea5",
        (_rule("lpla_acquisitions", "acquisition", "The filing separately identifies acquisitions and fair-value purchase accounting in the current base.", r"Note 4 - Acquisitions.{0,120}Note 5 - Fair Value Measurements"),),
        (_gate("revenue_growth_yoy", "direction_only", "Acquired adviser/platform activity changes the revenue base; retain growth direction only.", "lpla_acquisitions"),),
    ),
)


def _excerpt(text: str, match: re.Match[str]) -> str:
    start = max(0, match.start() - 220)
    end = min(len(text), match.end() + 420)
    return text[start:end].strip()


def review_sector_filing(
    filing: FilingMetadata,
    snapshots: tuple[DocumentSnapshot, ...],
    *,
    spec: SectorFilingReviewSpec,
) -> SectorFilingReview:
    identity_matches = (
        filing.cik == spec.cik
        and filing.accession_number == spec.accession_number
        and filing.report_period_end is not None
        and filing.report_period_end.isoformat() == spec.report_period_end
    )
    primary = next(
        (
            snapshot
            for snapshot in snapshots
            if snapshot.document.document_name == spec.primary_document
        ),
        None,
    )
    missing: list[str] = []
    if not identity_matches:
        missing.append("filing_identity")
    if primary is None or primary.content_sha256 != spec.source_sha256:
        missing.append("primary_document_hash")
    findings: list[SectorEvidenceFinding] = []
    if primary is not None:
        normalized = " ".join(primary.text.split())
        for rule in spec.rules:
            match = re.search(rule.pattern, normalized, re.IGNORECASE | re.DOTALL)
            if match is None:
                missing.append(rule.evidence_id)
                continue
            findings.append(
                SectorEvidenceFinding(
                    evidence_id=rule.evidence_id,
                    category=rule.category,
                    statement=rule.statement,
                    excerpt=_excerpt(normalized, match),
                    source_url=primary.document.sec_url,
                    source_sha256=primary.content_sha256,
                )
            )
    else:
        missing.extend(rule.evidence_id for rule in spec.rules)
    complete = not missing
    gates = tuple(
        MetricComparisonGate(
            metric=gate.metric,
            status=gate.status if complete else "blocked",
            reason=(
                gate.reason
                if complete
                else "The exact filing review is incomplete; comparison remains blocked."
            ),
            evidence_ids=gate.evidence_ids if complete else (),
        )
        for gate in spec.gates
    )
    return SectorFilingReview(
        industry_key=spec.industry_key,
        cik=spec.cik,
        ticker=spec.ticker,
        accession_number=spec.accession_number,
        report_period_end=spec.report_period_end,
        model_version=SECTOR_FILING_REVIEW_VERSION,
        review_status="complete" if complete else "incomplete",
        missing_evidence_ids=tuple(missing),
        findings=tuple(findings),
        gates=gates,
        publication_allowed=complete,
    )


def sector_review_spec(cik: str) -> SectorFilingReviewSpec:
    return next(spec for spec in SECTOR_FILING_SPECS if spec.cik == cik)
