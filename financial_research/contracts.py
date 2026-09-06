from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import TypeAlias


FactValue: TypeAlias = int | float | str


@dataclass(frozen=True, slots=True)
class SecurityIdentifier:
    ticker: str
    exchange: str | None


@dataclass(frozen=True, slots=True)
class FilingMetadata:
    cik: str
    accession_number: str
    form: str
    filed_on: date
    report_period_end: date | None
    accepted_at: datetime | None
    primary_document: str | None
    primary_document_description: str | None
    is_amendment: bool
    is_inline_xbrl: bool | None
    sec_index_url: str
    metadata_source: str = "submissions"


@dataclass(frozen=True, slots=True)
class ExtractionIssue:
    stage: str
    source_locator: str | None
    reason_code: str
    detail: str
    bounded_context: dict[str, str]


@dataclass(frozen=True, slots=True)
class CompanyProfile:
    cik: str
    name: str
    sic: str | None
    sic_description: str | None
    securities: tuple[SecurityIdentifier, ...]
    former_names: tuple[str, ...]
    filings: tuple[FilingMetadata, ...]


@dataclass(frozen=True, slots=True)
class FactObservation:
    cik: str
    taxonomy: str
    concept: str
    label: str
    description: str
    unit: str
    value: FactValue
    period_start: date | None
    period_end: date
    filed_on: date
    accepted_at: datetime | None
    fiscal_year: int | None
    fiscal_period: str | None
    form: str
    accession_number: str
    frame: str | None
    context_kind: str
    is_amendment: bool
    sec_index_url: str


@dataclass(frozen=True, slots=True)
class FilingDocument:
    cik: str
    accession_number: str
    sequence: int | None
    description: str
    document_name: str
    document_type: str
    size_bytes: int | None
    category: str
    sec_url: str


@dataclass(frozen=True, slots=True)
class DocumentSnapshot:
    document: FilingDocument
    content_type: str
    content_sha256: str
    byte_count: int
    text: str


@dataclass(frozen=True, slots=True)
class TextEvidence:
    category: str
    heading: str
    excerpt: str
    start_offset: int
    end_offset: int
    extraction_method: str
    extraction_version: str
    confidence: str
    source_url: str
    source_sha256: str


@dataclass(frozen=True, slots=True)
class EntityRole:
    entity_name: str
    entity_type: str
    role: str
    evidence_excerpt: str
    source_url: str
    confidence: str


@dataclass(frozen=True, slots=True)
class EvidenceClaim:
    claim_kind: str
    statement: str
    status: str
    confidence: str
    source_urls: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResearchQuestion:
    category: str
    question: str
    reason: str
    status: str = "open"
