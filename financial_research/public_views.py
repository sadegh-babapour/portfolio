from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .analysis import AnalysisValue, analyze_company_quarter
from .contracts import FactObservation
from .metrics import CANONICAL_METRIC_VERSION
from .models import (
    ResearchFactMetricMapping,
    ResearchFactObservation,
    ResearchFiling,
)
from .peer_reviews import PEER_OUTLIER_SPECS
from .documents import filing_archive_url
from .peers import (
    OPERATING_PATTERN_MODEL_VERSION,
    PAYMENTS_PEER_MODEL_VERSION,
    REQUIRED_CLASSIFICATION_KEYS,
    assess_payment_cohort,
    classify_operating_pattern,
)
from .sector_reviews import SECTOR_FILING_REVIEW_VERSION, SECTOR_FILING_SPECS
from .universe import CORE_INDUSTRY_CONTRACTS, CORE_RESEARCH_UNIVERSE


PUBLIC_DIRECTORY_VERSION = "sec-public-directory-2026-09-08.1"
PAYMENTS_COMPARISON_VERSION = "payments-public-comparison-2026-09-08.1"
SECTOR_SCREEN_VERSION = "sector-public-screen-2026-09-08.1"
REVIEWED_PAYMENTS_PERIOD = date(2026, 6, 30)
PUBLIC_HISTORY_YEARS = 5


@dataclass(frozen=True, slots=True)
class ExactFilingIdentity:
    cik: str
    accession_number: str
    period_end: str


REVIEWED_PAYMENT_FILINGS = (
    ExactFilingIdentity(
        cik="0001633917",
        accession_number="0001633917-26-000082",
        period_end="2026-06-30",
    ),
    *(
        ExactFilingIdentity(spec.cik, spec.accession_number, spec.report_period_end)
        for spec in PEER_OUTLIER_SPECS
    ),
)


def _require_sec_archive_url(url: str) -> str:
    if not url.startswith("https://www.sec.gov/Archives/edgar/data/"):
        raise ValueError("Public filing links must use the SEC Archives host")
    return url


def _latest_filings(
    database: Session,
    ciks: Iterable[str],
) -> dict[str, ResearchFiling]:
    cik_tuple = tuple(ciks)
    rows = database.scalars(
        select(ResearchFiling)
        .where(
            ResearchFiling.filer_cik.in_(cik_tuple),
            ResearchFiling.base_form.in_(("10-Q", "10-K")),
            ResearchFiling.report_period_end.is_not(None),
            ResearchFiling.is_amendment.is_(False),
        )
        .order_by(
            ResearchFiling.filer_cik,
            ResearchFiling.report_period_end.desc(),
            ResearchFiling.accepted_at.desc(),
            ResearchFiling.accession_number.desc(),
        )
    ).all()
    latest: dict[str, ResearchFiling] = {}
    for filing in rows:
        latest.setdefault(filing.filer_cik, filing)
    return latest


def _latest_core_filings(database: Session) -> dict[str, ResearchFiling]:
    return _latest_filings(
        database,
        (company.cik for company in CORE_RESEARCH_UNIVERSE),
    )


def _mapped_observations(
    database: Session,
    ciks: Iterable[str],
    minimum_period: date,
) -> tuple[ResearchFactObservation, ...]:
    """Load only facts eligible for the current analytical metric contract."""
    return tuple(
        database.scalars(
            select(ResearchFactObservation)
            .join(
                ResearchFactMetricMapping,
                ResearchFactMetricMapping.fact_id == ResearchFactObservation.id,
            )
            .where(
                ResearchFactObservation.filer_cik.in_(tuple(ciks)),
                ResearchFactObservation.period_end >= minimum_period,
                ResearchFactMetricMapping.metric_version
                == CANONICAL_METRIC_VERSION,
            )
        ).all()
    )


def load_public_filing_directory(database: Session) -> dict:
    """Build an all-or-nothing public directory from exact persisted SEC filings."""
    latest = _latest_core_filings(database)
    expected_ciks = {company.cik for company in CORE_RESEARCH_UNIVERSE}
    if set(latest) != expected_ciks:
        missing = sorted(expected_ciks - set(latest))
        raise ValueError("Core filing directory is incomplete: " + ", ".join(missing))
    industries = []
    for contract in CORE_INDUSTRY_CONTRACTS:
        companies = []
        for company in contract.companies:
            filing = latest[company.cik]
            companies.append(
                {
                    "cik": company.cik,
                    "ticker": company.ticker,
                    "slug": company.ticker.lower(),
                    "company_name": company.company_name,
                    "business_model": company.business_model,
                    "comparison_subgroup": company.comparison_subgroup,
                    "form": filing.base_form,
                    "period_end": filing.report_period_end.isoformat(),
                    "filed_on": filing.filed_on.isoformat(),
                    "accession_number": filing.accession_number,
                    "filing_index_url": _require_sec_archive_url(filing.sec_index_url),
                    "publication_state": (
                        "reviewed_sheet"
                        if company.publication_status == "published"
                        else "filing_profile"
                    ),
                }
            )
        industries.append(
            {
                "key": contract.key,
                "label": contract.label,
                "comparison_notes": list(contract.comparison_notes),
                "companies": companies,
            }
        )
    return {
        "available": True,
        "version": PUBLIC_DIRECTORY_VERSION,
        "company_count": len(CORE_RESEARCH_UNIVERSE),
        "industries": industries,
    }


def load_public_filing_profile(database: Session, ticker: str) -> dict | None:
    company = next(
        (
            item
            for item in CORE_RESEARCH_UNIVERSE
            if item.ticker.lower() == ticker.lower()
        ),
        None,
    )
    if company is None:
        return None
    filings = tuple(
        database.scalars(
            select(ResearchFiling)
            .where(
                ResearchFiling.filer_cik == company.cik,
                ResearchFiling.base_form.in_(("10-Q", "10-K")),
                ResearchFiling.report_period_end.is_not(None),
                ResearchFiling.is_amendment.is_(False),
            )
            .order_by(
                ResearchFiling.report_period_end.desc(),
                ResearchFiling.accepted_at.desc(),
            )
            .limit(16)
        ).all()
    )
    if not filings:
        raise ValueError("No exact SEC filings are available for this company")
    filing_rows = []
    for filing in filings:
        filing_rows.append(
            {
                "form": filing.base_form,
                "period_end": filing.report_period_end.isoformat(),
                "filed_on": filing.filed_on.isoformat(),
                "accession_number": filing.accession_number,
                "filing_index_url": _require_sec_archive_url(filing.sec_index_url),
            }
        )
    minimum_period = filings[-1].report_period_end - timedelta(days=370)
    fact_rows = _mapped_observations(database, (company.cik,), minimum_period)
    fact_contracts = tuple(_fact_contract(row) for row in fact_rows)
    analyses = []
    for filing in filings:
        fiscal_quarter = _fiscal_quarter(filing, fact_rows)
        if fiscal_quarter not in {1, 2, 3, 4}:
            continue
        try:
            report = analyze_company_quarter(
                fact_contracts,
                company_name=company.company_name,
                period_end=filing.report_period_end,
                fiscal_quarter=fiscal_quarter,
            )
        except (ValueError, TypeError, ArithmeticError):
            continue
        analyses.append(_analysis_payload(report, filing))
    return {
        "available": True,
        "version": PUBLIC_DIRECTORY_VERSION,
        "cik": company.cik,
        "ticker": company.ticker,
        "company_name": company.company_name,
        "business_model": company.business_model,
        "industry_key": company.industry_key,
        "comparison_subgroup": company.comparison_subgroup,
        "publication_state": company.publication_status,
        "filings": filing_rows,
        "analyses": analyses,
        "analysis_scope": "screening_only",
    }


def _fact_contract(row: ResearchFactObservation) -> FactObservation:
    return FactObservation(
        cik=row.filer_cik,
        taxonomy=row.taxonomy,
        concept=row.concept,
        label=row.label,
        description=row.description,
        unit=row.unit,
        value=row.value_json,
        period_start=row.period_start,
        period_end=row.period_end,
        filed_on=row.filed_on,
        accepted_at=row.accepted_at,
        fiscal_year=row.fiscal_year,
        fiscal_period=row.fiscal_period,
        form=row.form,
        accession_number=row.accession_number,
        frame=row.frame,
        context_kind=row.context_kind,
        is_amendment=row.is_amendment,
        sec_index_url=row.sec_index_url,
    )


def _format_lens(value: float | None, unit: str) -> str:
    if value is None:
        return "Unavailable"
    if unit == "percent":
        return f"{value:+.2f}%"
    if unit == "percentage_points":
        return f"{value:+.2f}pp"
    if unit == "ratio":
        return f"{value:.2f}x"
    return f"{value:.2f}"


def _format_analysis_value(value: AnalysisValue) -> str:
    if not value.usable or value.value is None:
        return "Unavailable"
    numeric = float(value.value)
    if value.unit == "USD":
        return f"${numeric / 1_000_000_000:.3f}B"
    if value.unit == "shares":
        return f"{numeric / 1_000_000:.1f}M"
    if value.unit == "USD/shares":
        return f"${numeric:.2f}"
    return _format_lens(numeric, value.unit)


def _fiscal_quarter(
    filing: ResearchFiling,
    facts: Iterable[ResearchFactObservation],
) -> int:
    if filing.base_form == "10-K":
        return 4
    counts = {quarter: 0 for quarter in (1, 2, 3)}
    for fact in facts:
        if (
            fact.accession_number == filing.accession_number
            and fact.period_end == filing.report_period_end
            and fact.fiscal_period in {"Q1", "Q2", "Q3"}
        ):
            counts[int(fact.fiscal_period[1])] += 1
    if any(counts.values()):
        return max(counts, key=counts.get)
    return {3: 1, 6: 2, 9: 3}.get(filing.report_period_end.month, 0)


def _analysis_payload(report, filing: ResearchFiling) -> dict:
    values = {
        value.key: value for value in (*report.normalized_facts, *report.derived_measures)
    }
    keys = (
        "revenue",
        "revenue_growth_yoy",
        "operating_income",
        "operating_margin",
        "operating_margin_change_yoy",
        "net_income",
        "net_margin",
        "operating_cash_flow",
        "cash_conversion",
        "simplified_free_cash_flow",
        "working_capital",
        "diluted_weighted_average_shares",
        "diluted_share_change_yoy",
    )
    metrics = []
    for key in keys:
        value = values[key]
        source_url = (
            value.evidence[0].sec_url
            if value.evidence
            else _require_sec_archive_url(filing.sec_index_url)
        )
        metrics.append(
            {
                "key": key,
                "label": value.label,
                "display_value": _format_analysis_value(value),
                "value": float(value.value) if value.usable else None,
                "unit": value.unit,
                "state": value.state,
                "confidence": value.confidence,
                "formula": value.formula,
                "note": value.note,
                "source_url": _require_sec_archive_url(source_url),
            }
        )
    return {
        "period_end": report.period_end.isoformat(),
        "fiscal_quarter": report.fiscal_quarter,
        "accession_number": filing.accession_number,
        "filing_index_url": _require_sec_archive_url(filing.sec_index_url),
        "metrics": metrics,
    }


def _load_company_histories(
    database: Session,
    companies,
    latest_filings: dict[str, ResearchFiling],
) -> dict[str, list[dict]]:
    """Return comparable quarterly series without exposing mapping diagnostics."""
    ciks = tuple(company.cik for company in companies)
    if not ciks:
        return {}
    earliest_latest = min(
        filing.report_period_end for filing in latest_filings.values()
    )
    filing_cutoff = earliest_latest - timedelta(days=PUBLIC_HISTORY_YEARS * 366)
    filings = tuple(
        database.scalars(
            select(ResearchFiling)
            .where(
                ResearchFiling.filer_cik.in_(ciks),
                ResearchFiling.base_form.in_(("10-Q", "10-K")),
                ResearchFiling.report_period_end.is_not(None),
                ResearchFiling.report_period_end >= filing_cutoff,
                ResearchFiling.is_amendment.is_(False),
            )
            .order_by(
                ResearchFiling.filer_cik,
                ResearchFiling.report_period_end.desc(),
                ResearchFiling.accepted_at.desc(),
            )
        ).all()
    )
    facts = _mapped_observations(
        database,
        ciks,
        filing_cutoff - timedelta(days=370),
    )
    facts_by_cik: dict[str, list[ResearchFactObservation]] = {cik: [] for cik in ciks}
    for fact in facts:
        facts_by_cik[fact.filer_cik].append(fact)
    filings_by_cik: dict[str, list[ResearchFiling]] = {cik: [] for cik in ciks}
    seen_periods: set[tuple[str, date]] = set()
    for filing in filings:
        identity = (filing.filer_cik, filing.report_period_end)
        if identity in seen_periods:
            continue
        seen_periods.add(identity)
        filings_by_cik[filing.filer_cik].append(filing)

    company_names = {company.cik: company.company_name for company in companies}
    histories: dict[str, list[dict]] = {cik: [] for cik in ciks}
    for cik in ciks:
        company_facts = facts_by_cik[cik]
        fact_contracts = tuple(_fact_contract(row) for row in company_facts)
        for filing in reversed(filings_by_cik[cik]):
            fiscal_quarter = _fiscal_quarter(filing, company_facts)
            if fiscal_quarter not in {1, 2, 3, 4}:
                continue
            try:
                report = analyze_company_quarter(
                    fact_contracts,
                    company_name=company_names[cik],
                    period_end=filing.report_period_end,
                    fiscal_quarter=fiscal_quarter,
                )
            except (ValueError, TypeError, ArithmeticError):
                continue
            histories[cik].append(_analysis_payload(report, filing))
    return histories


def load_public_payments_comparison(database: Session) -> dict:
    """Render only the exact Q2 payment cohort whose structural gates were reviewed."""
    exact_by_cik = {item.cik: item for item in REVIEWED_PAYMENT_FILINGS}
    filing_rows = tuple(
        database.scalars(
            select(ResearchFiling).where(
                ResearchFiling.accession_number.in_(
                    tuple(item.accession_number for item in REVIEWED_PAYMENT_FILINGS)
                )
            )
        ).all()
    )
    if len(filing_rows) != len(REVIEWED_PAYMENT_FILINGS):
        raise ValueError("The reviewed payment filing set is incomplete")
    filings = {row.filer_cik: row for row in filing_rows}
    for cik, identity in exact_by_cik.items():
        filing = filings.get(cik)
        if (
            filing is None
            or filing.accession_number != identity.accession_number
            or filing.report_period_end is None
            or filing.report_period_end.isoformat() != identity.period_end
        ):
            raise ValueError("A reviewed payment filing identity changed")

    facts = _mapped_observations(database, tuple(exact_by_cik), date(2025, 1, 1))
    by_cik: dict[str, list[FactObservation]] = {cik: [] for cik in exact_by_cik}
    for row in facts:
        by_cik[row.filer_cik].append(_fact_contract(row))

    payment_contract = CORE_INDUSTRY_CONTRACTS[0]
    reports = tuple(
        analyze_company_quarter(
            by_cik[company.cik],
            company_name=company.company_name,
            period_end=REVIEWED_PAYMENTS_PERIOD,
            fiscal_quarter=2,
        )
        for company in payment_contract.companies
    )
    histories = _load_company_histories(database, payment_contract.companies, filings)
    assessments = assess_payment_cohort(reports)
    gate_specs = {
        spec.cik: {gate.metric: gate for gate in spec.gates}
        for spec in PEER_OUTLIER_SPECS
    }
    companies = []
    for company, assessment in zip(payment_contract.companies, assessments, strict=True):
        gates = gate_specs.get(company.cik, {})
        lenses = []
        for lens in assessment.lenses:
            gate = gates.get(lens.key)
            if gate:
                gate_status = gate.status
            elif lens.value is None or lens.confidence == "blocked":
                gate_status = "blocked"
            else:
                gate_status = "cleared"
            if gate_status == "blocked":
                display_value = "Blocked"
            elif gate_status == "direction_only":
                display_value = "Up" if (lens.value or 0) > 0 else "Down"
            else:
                display_value = _format_lens(lens.value, lens.unit)
            lenses.append(
                {
                    "key": lens.key,
                    "label": lens.label,
                    "display_value": display_value,
                    "gate_status": gate_status,
                    "reason": (
                        gate.reason
                        if gate
                        else (
                            lens.interpretation
                            if gate_status == "cleared"
                            else "Required mapped inputs are unavailable; no value is inferred."
                        )
                    ),
                }
            )
        filing = filings[company.cik]
        companies.append(
            {
                "cik": company.cik,
                "ticker": company.ticker,
                "company_name": company.company_name,
                "subgroup": company.comparison_subgroup,
                "period_end": assessment.period_end,
                "accession_number": filing.accession_number,
                "filing_index_url": _require_sec_archive_url(filing.sec_index_url),
                "cohort": assessment.cohort,
                "signal_pattern": assessment.signal_pattern,
                "comparable": assessment.comparable and not gates,
                "lenses": lenses,
                "history": histories.get(company.cik, []),
            }
        )
    return {
        "available": True,
        "version": PAYMENTS_COMPARISON_VERSION,
        "model_version": PAYMENTS_PEER_MODEL_VERSION,
        "period_end": REVIEWED_PAYMENTS_PERIOD.isoformat(),
        "ranking_performed": False,
        "companies": companies,
        "comparison_notes": list(payment_contract.comparison_notes),
    }


def load_public_sector_screen(database: Session, industry_key: str) -> dict | None:
    """Build a filing-reviewed, no-ranking sector comparison for one industry."""
    contract = next(
        (
            item
            for item in CORE_INDUSTRY_CONTRACTS
            if item.key == industry_key and item.key != "payments"
        ),
        None,
    )
    if contract is None:
        return None
    latest_filings = _latest_filings(
        database,
        (company.cik for company in contract.companies),
    )
    if len(latest_filings) != len(contract.companies):
        raise ValueError("Sector screen does not have an exact filing for every company")
    specs = {
        spec.cik: spec
        for spec in SECTOR_FILING_SPECS
        if spec.industry_key == industry_key
    }
    if set(specs) != {company.cik for company in contract.companies}:
        raise ValueError("Sector screen does not have a review spec for every company")
    for company in contract.companies:
        filing = latest_filings[company.cik]
        spec = specs[company.cik]
        if (
            filing.accession_number != spec.accession_number
            or filing.report_period_end is None
            or filing.report_period_end.isoformat() != spec.report_period_end
        ):
            raise ValueError(
                f"Reviewed sector filing identity changed for {company.ticker}"
            )
    minimum_period = min(
        filing.report_period_end for filing in latest_filings.values()
    ) - timedelta(days=370)
    fact_rows = _mapped_observations(database, tuple(latest_filings), minimum_period)
    facts_by_cik: dict[str, list[ResearchFactObservation]] = {
        company.cik: [] for company in contract.companies
    }
    for fact in fact_rows:
        facts_by_cik[fact.filer_cik].append(fact)

    histories = _load_company_histories(database, contract.companies, latest_filings)

    companies = []
    periods = set()
    lens_keys = (
        "revenue_growth_yoy",
        "operating_margin_change_yoy",
        "cash_conversion",
        "diluted_share_change_yoy",
    )
    for company in contract.companies:
        filing = latest_filings[company.cik]
        spec = specs[company.cik]
        company_fact_rows = facts_by_cik[company.cik]
        fiscal_quarter = _fiscal_quarter(filing, company_fact_rows)
        if fiscal_quarter not in {1, 2, 3, 4}:
            raise ValueError(f"Sector screen cannot resolve a quarter for {company.ticker}")
        report = analyze_company_quarter(
            (_fact_contract(row) for row in company_fact_rows),
            company_name=company.company_name,
            period_end=filing.report_period_end,
            fiscal_quarter=fiscal_quarter,
        )
        latest = _analysis_payload(report, filing)
        periods.add(latest["period_end"])
        by_key = {metric["key"]: metric for metric in latest["metrics"]}
        gate_specs = {gate.metric: gate for gate in spec.gates}
        lenses = []
        for key in lens_keys:
            metric = by_key[key]
            gate = gate_specs.get(key)
            usable = metric["value"] is not None and metric["confidence"] != "blocked"
            gate_status = gate.status if gate is not None and usable else (
                "cleared" if usable else "blocked"
            )
            if gate_status == "blocked":
                display_value = "Blocked"
            elif gate_status == "direction_only":
                display_value = (
                    "Up" if metric["value"] > 0
                    else "Down" if metric["value"] < 0
                    else "Flat"
                )
            else:
                display_value = metric["display_value"]
            lenses.append(
                {
                    "key": key,
                    "label": metric["label"],
                    "display_value": display_value,
                    "value": metric["value"] if gate_status == "cleared" else None,
                    "unit": metric["unit"],
                    "state": metric["state"],
                    "confidence": metric["confidence"],
                    "gate_status": gate_status,
                    "reason": (
                        gate.reason
                        if gate is not None and usable
                        else (
                            "Required mapped inputs are unavailable; no value is inferred."
                            if not usable
                            else "The exact filing evidence supports magnitude comparison."
                        )
                    ),
                    "source_url": metric["source_url"],
                }
            )
        lenses_by_key = {lens["key"]: lens for lens in lenses}
        classification_blockers = tuple(
            key
            for key in REQUIRED_CLASSIFICATION_KEYS
            if lenses_by_key[key]["gate_status"] != "cleared"
            or lenses_by_key[key]["value"] is None
        )
        if classification_blockers:
            cohort = "not_comparable"
            comparable = False
            reasons = (
                "Required comparison lenses are gated: "
                + ", ".join(classification_blockers),
            )
        else:
            cohort, reasons = classify_operating_pattern(
                {
                    key: lenses_by_key[key]["value"]
                    for key in REQUIRED_CLASSIFICATION_KEYS
                }
            )
            comparable = True
        primary_url = _require_sec_archive_url(
            filing_archive_url(
                company.cik, filing.accession_number, spec.primary_document
            )
        )
        companies.append(
            {
                "cik": company.cik,
                "ticker": company.ticker,
                "company_name": company.company_name,
                "subgroup": company.comparison_subgroup,
                "period_end": latest["period_end"],
                "accession_number": latest["accession_number"],
                "filing_index_url": latest["filing_index_url"],
                "comparison_state": "reviewed_with_metric_gates",
                "review_version": SECTOR_FILING_REVIEW_VERSION,
                "cohort": cohort,
                "signal_pattern": cohort if comparable else None,
                "comparable": comparable,
                "reasons": list(reasons),
                "lenses": lenses,
                "findings": [
                    {
                        "evidence_id": rule.evidence_id,
                        "category": rule.category,
                        "statement": rule.statement,
                        "source_url": primary_url,
                    }
                    for rule in spec.rules
                ],
                "history": histories.get(company.cik, []),
            }
        )
    return {
        "available": True,
        "version": SECTOR_SCREEN_VERSION,
        "industry_key": contract.key,
        "industry_label": contract.label,
        "same_period": len(periods) == 1,
        "ranking_performed": False,
        "cohorts_assigned": True,
        "model_version": OPERATING_PATTERN_MODEL_VERSION,
        "review_version": SECTOR_FILING_REVIEW_VERSION,
        "companies": companies,
        "comparison_notes": [
            *contract.comparison_notes,
            "Operating-pattern cohorts summarize three cleared filing signals; they are not investment recommendations or ranks.",
            "Direction-only and blocked magnitudes are excluded from charts and cohort assignment.",
        ],
        "metric_contract": [
            {
                "label": metric.label,
                "scope": metric.comparison_scope,
                "evidence_note": metric.evidence_note,
            }
            for metric in contract.metrics
        ],
    }
