from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .automation import RefreshReport


PUBLICATION_GATE_VERSION = "financial-promotion-2026-09-06.1"


@dataclass(frozen=True, slots=True)
class PublicationApproval:
    cik: str
    accession_number: str
    period_end: str


@dataclass(frozen=True, slots=True)
class PublicationGate:
    ready_for_owner_approval: bool
    gate_version: str
    reasons: tuple[str, ...]
    approved_ciks: tuple[str, ...]
    publication_performed: bool = False


APPROVED_PUBLICATION_INPUTS: tuple[PublicationApproval, ...] = (
    PublicationApproval(
        cik="0001633917",
        accession_number="0001633917-26-000082",
        period_end="2026-06-30",
    ),
)


def gate_publication_candidate(
    document: Mapping[str, object],
    refresh: RefreshReport,
    *,
    approvals: tuple[PublicationApproval, ...] = APPROVED_PUBLICATION_INPUTS,
) -> PublicationGate:
    """Gate a validated candidate; this function never publishes it."""
    reasons: list[str] = []
    if refresh.status != "completed" or refresh.failed_count:
        reasons.append("The source refresh did not complete for every target.")
    if refresh.publication_performed or refresh.publication_status != "withheld":
        reasons.append("The refresh crossed the required publication-withheld boundary.")

    approved = {
        (item.cik, item.accession_number, item.period_end): item for item in approvals
    }
    companies = document.get("companies")
    if not isinstance(companies, list) or not companies:
        reasons.append("The candidate contains no validated company payloads.")
        companies = []
    seen_ciks: list[str] = []
    for company in companies:
        if not isinstance(company, Mapping):
            reasons.append("A company payload is not an object.")
            continue
        identity = (
            str(company.get("cik", "")),
            str(company.get("accession_number", "")),
            str(company.get("period_end", "")),
        )
        seen_ciks.append(identity[0])
        if identity not in approved:
            reasons.append(
                "Company input is not explicitly approved for this accession and period: "
                + identity[0]
            )

    refreshed_ciks = {company.cik for company in refresh.companies if company.status == "completed"}
    missing_refresh = sorted(set(seen_ciks) - refreshed_ciks)
    if missing_refresh:
        reasons.append(
            "Candidate companies were absent from the completed refresh: "
            + ", ".join(missing_refresh)
        )
    return PublicationGate(
        ready_for_owner_approval=not reasons,
        gate_version=PUBLICATION_GATE_VERSION,
        reasons=tuple(reasons),
        approved_ciks=tuple(sorted(set(seen_ciks))) if not reasons else (),
    )
