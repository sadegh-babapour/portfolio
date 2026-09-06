from __future__ import annotations

from datetime import date

from .contracts import CompanyProfile, FactObservation
from .documents import extract_instance_facts, fetch_filing_inventory, fetch_snapshot
from .edgar import EdgarClient, base_form
from .ingestion import ExtractionBundle


def quarter_targets(
    profile: CompanyProfile,
    facts: tuple[FactObservation, ...],
) -> tuple[tuple[date, int], ...]:
    """Return reporting-period/quarter pairs supported by filing and fact metadata."""
    fiscal_periods_by_accession: dict[str, set[str]] = {}
    for fact in facts:
        if fact.fiscal_period:
            fiscal_periods_by_accession.setdefault(fact.accession_number, set()).add(
                fact.fiscal_period.upper()
            )

    targets: set[tuple[date, int]] = set()
    for filing in profile.filings:
        if filing.report_period_end is None:
            continue
        form = base_form(filing.form)
        periods = fiscal_periods_by_accession.get(filing.accession_number, set())
        if form == "10-K" and "FY" in periods:
            targets.add((filing.report_period_end, 4))
            continue
        for quarter in (1, 2, 3):
            if form == "10-Q" and f"Q{quarter}" in periods:
                targets.add((filing.report_period_end, quarter))
    return tuple(sorted(targets))


def supplement_lagging_company_facts(
    client: EdgarClient,
    bundle: ExtractionBundle,
) -> tuple[FactObservation, ...]:
    """Use a newer filing instance when aggregate Company Facts has not caught up."""
    facts = list(bundle.facts)
    known_accessions = {fact.accession_number for fact in facts}
    latest_period_end = max((fact.period_end for fact in facts), default=bundle.period_start)
    for filing in bundle.profile.filings:
        if (
            filing.accession_number in known_accessions
            or filing.report_period_end is None
            or filing.report_period_end <= latest_period_end
            or base_form(filing.form) not in {"10-Q", "10-K"}
        ):
            continue
        inventory = fetch_filing_inventory(client, filing)
        instance = next(
            (
                document
                for document in inventory
                if document.document_name.lower().endswith("_htm.xml")
                and "EXTRACTED XBRL INSTANCE" in document.description.upper()
            ),
            None,
        )
        if instance is None:
            continue
        snapshot = fetch_snapshot(client, instance)
        facts.extend(
            extract_instance_facts(
                snapshot.text.encode("utf-8"),
                filing=filing,
                source_url=instance.sec_url,
                period_start=bundle.period_start,
            )
        )
        known_accessions.add(filing.accession_number)
    return tuple(facts)

