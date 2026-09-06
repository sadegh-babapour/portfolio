"""Reusable financial-research domain code."""

from .contracts import (
    CompanyProfile,
    DocumentSnapshot,
    EntityRole,
    EvidenceClaim,
    ExtractionIssue,
    FactObservation,
    FilingMetadata,
    FilingDocument,
    ResearchQuestion,
    SecurityIdentifier,
    TextEvidence,
)
from .edgar import (
    EdgarClient,
    EdgarResponseError,
    extract_acceptance_times,
    extract_company_profile,
    extract_filing_metadata,
    extract_facts,
)

__all__ = [
    "CompanyProfile",
    "DocumentSnapshot",
    "EdgarClient",
    "EdgarResponseError",
    "EntityRole",
    "EvidenceClaim",
    "ExtractionIssue",
    "FactObservation",
    "FilingMetadata",
    "FilingDocument",
    "ResearchQuestion",
    "SecurityIdentifier",
    "TextEvidence",
    "extract_acceptance_times",
    "extract_company_profile",
    "extract_filing_metadata",
    "extract_facts",
]
