from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.contact.models import Base


class ResearchFiler(Base):
    __tablename__ = "research_filers"

    cik: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(240))
    sic: Mapped[str | None] = mapped_column(String(8))
    sic_description: Mapped[str | None] = mapped_column(String(240))
    former_names: Mapped[list[str]] = mapped_column(JSON, default=list)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResearchSecurity(Base):
    __tablename__ = "research_securities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    filer_cik: Mapped[str] = mapped_column(
        String(10), ForeignKey("portfolio.research_filers.cik", ondelete="CASCADE")
    )
    ticker: Mapped[str] = mapped_column(String(32))
    exchange: Mapped[str] = mapped_column(String(80), default="")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("filer_cik", "ticker", "exchange", name="uq_research_security_identity"),
        Index("ix_research_securities_ticker", "ticker"),
    )


class ResearchIngestionRun(Base):
    __tablename__ = "research_ingestion_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    filer_cik: Mapped[str] = mapped_column(
        String(10), ForeignKey("portfolio.research_filers.cik", ondelete="CASCADE")
    )
    status: Mapped[str] = mapped_column(String(24), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    extraction_version: Mapped[str] = mapped_column(String(40))
    submissions_sha256: Mapped[str] = mapped_column(String(64))
    companyfacts_sha256: Mapped[str] = mapped_column(String(64))
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    error_summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'completed_with_issues', 'failed')",
            name="ck_research_ingestion_run_status",
        ),
        Index("ix_research_runs_filer_started", "filer_cik", "started_at"),
    )


class ResearchAutomationRun(Base):
    __tablename__ = "research_automation_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    trigger_kind: Mapped[str] = mapped_column(String(24))
    cohort_key: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(32), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    target_count: Mapped[int] = mapped_column(Integer)
    succeeded_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    publication_status: Mapped[str] = mapped_column(String(24), default="withheld")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "trigger_kind IN ('scheduled', 'admin')",
            name="ck_research_automation_trigger_kind",
        ),
        CheckConstraint(
            "status IN ('running', 'completed', 'completed_with_failures', 'failed')",
            name="ck_research_automation_status",
        ),
        CheckConstraint(
            "publication_status IN ('withheld', 'ready', 'published')",
            name="ck_research_automation_publication_status",
        ),
        Index("ix_research_automation_started", "started_at"),
    )


class ResearchAutomationAttempt(Base):
    __tablename__ = "research_automation_attempts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    automation_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("portfolio.research_automation_runs.id", ondelete="CASCADE"),
        index=True,
    )
    filer_cik: Mapped[str] = mapped_column(String(10), index=True)
    ticker: Mapped[str] = mapped_column(String(32))
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24))
    reason_code: Mapped[str | None] = mapped_column(String(80))
    retryable: Mapped[bool] = mapped_column(Boolean, default=False)
    ingestion_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("portfolio.research_ingestion_runs.id", ondelete="SET NULL"),
    )
    fact_count: Mapped[int | None] = mapped_column(Integer)
    filing_count: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('completed', 'failed')",
            name="ck_research_automation_attempt_status",
        ),
        UniqueConstraint(
            "automation_run_id",
            "filer_cik",
            "attempt_number",
            name="uq_research_automation_attempt",
        ),
    )


class ResearchFiling(Base):
    __tablename__ = "research_filings"

    accession_number: Mapped[str] = mapped_column(String(20), primary_key=True)
    filer_cik: Mapped[str] = mapped_column(
        String(10), ForeignKey("portfolio.research_filers.cik", ondelete="CASCADE"), index=True
    )
    form: Mapped[str] = mapped_column(String(16))
    base_form: Mapped[str] = mapped_column(String(16), index=True)
    filed_on: Mapped[date] = mapped_column(Date, index=True)
    report_period_end: Mapped[date | None] = mapped_column(Date, index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    primary_document: Mapped[str | None] = mapped_column(String(255))
    primary_document_description: Mapped[str | None] = mapped_column(String(255))
    is_amendment: Mapped[bool] = mapped_column(Boolean)
    is_inline_xbrl: Mapped[bool | None] = mapped_column(Boolean)
    sec_index_url: Mapped[str] = mapped_column(Text)
    metadata_source: Mapped[str] = mapped_column(String(32))
    first_seen_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("portfolio.research_ingestion_runs.id", ondelete="RESTRICT")
    )
    last_seen_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("portfolio.research_ingestion_runs.id", ondelete="RESTRICT")
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResearchFactObservation(Base):
    __tablename__ = "research_fact_observations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    filer_cik: Mapped[str] = mapped_column(
        String(10), ForeignKey("portfolio.research_filers.cik", ondelete="CASCADE")
    )
    accession_number: Mapped[str] = mapped_column(
        String(20), ForeignKey("portfolio.research_filings.accession_number", ondelete="CASCADE")
    )
    taxonomy: Mapped[str] = mapped_column(String(80))
    concept: Mapped[str] = mapped_column(String(255))
    label: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(80))
    value_json: Mapped[int | float | str] = mapped_column(JSON)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    filed_on: Mapped[date] = mapped_column(Date)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fiscal_year: Mapped[int | None] = mapped_column(Integer)
    fiscal_period: Mapped[str | None] = mapped_column(String(16))
    form: Mapped[str] = mapped_column(String(16))
    frame: Mapped[str | None] = mapped_column(String(40))
    context_kind: Mapped[str] = mapped_column(String(16))
    is_amendment: Mapped[bool] = mapped_column(Boolean)
    sec_index_url: Mapped[str] = mapped_column(Text)
    first_seen_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("portfolio.research_ingestion_runs.id", ondelete="RESTRICT")
    )
    last_seen_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("portfolio.research_ingestion_runs.id", ondelete="RESTRICT")
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "context_kind IN ('instant', 'duration')",
            name="ck_research_fact_context_kind",
        ),
        Index(
            "ix_research_facts_semantic_period",
            "filer_cik",
            "taxonomy",
            "concept",
            "unit",
            "period_end",
        ),
        Index("ix_research_facts_accession", "accession_number"),
    )

    @property
    def value(self) -> int | float | str:
        return self.value_json


class ResearchCanonicalMapping(Base):
    __tablename__ = "research_canonical_mappings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    metric_key: Mapped[str] = mapped_column(String(80))
    metric_version: Mapped[str] = mapped_column(String(40))
    taxonomy: Mapped[str] = mapped_column(String(80))
    concept: Mapped[str] = mapped_column(String(255))
    unit: Mapped[str] = mapped_column(String(80))
    context_kind: Mapped[str] = mapped_column(String(16))
    priority: Mapped[int] = mapped_column(Integer)
    scope_cik: Mapped[str] = mapped_column(String(10), default="*")
    definition: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "context_kind IN ('instant', 'duration')",
            name="ck_research_mapping_context_kind",
        ),
        UniqueConstraint(
            "metric_key",
            "metric_version",
            "taxonomy",
            "concept",
            "unit",
            "context_kind",
            "scope_cik",
            name="uq_research_canonical_mapping",
        ),
    )


class ResearchFactMetricMapping(Base):
    __tablename__ = "research_fact_metric_mappings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    fact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("portfolio.research_fact_observations.id", ondelete="CASCADE"),
        index=True,
    )
    mapping_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("portfolio.research_canonical_mappings.id", ondelete="RESTRICT"),
    )
    metric_key: Mapped[str] = mapped_column(String(80))
    metric_version: Mapped[str] = mapped_column(String(40))
    quality_state: Mapped[str] = mapped_column(String(32), default="mapped")
    mapped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("fact_id", "metric_version", name="uq_research_fact_metric_version"),
        Index(
            "ix_research_fact_mappings_metric",
            "metric_key",
            "metric_version",
        ),
    )


class ResearchTransformationVersion(Base):
    __tablename__ = "research_transformation_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(40))
    version: Mapped[str] = mapped_column(String(40))
    specification: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("kind", "version", name="uq_research_transformation_version"),
    )


class ResearchReject(Base):
    __tablename__ = "research_rejects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("portfolio.research_ingestion_runs.id", ondelete="CASCADE"), index=True
    )
    filer_cik: Mapped[str] = mapped_column(String(10))
    stage: Mapped[str] = mapped_column(String(40))
    source_locator: Mapped[str | None] = mapped_column(String(500))
    reason_code: Mapped[str] = mapped_column(String(80), index=True)
    detail: Mapped[str] = mapped_column(Text)
    bounded_context: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResearchDerivedMeasure(Base):
    __tablename__ = "research_derived_measures"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    filer_cik: Mapped[str] = mapped_column(
        String(10), ForeignKey("portfolio.research_filers.cik", ondelete="CASCADE")
    )
    measure_kind: Mapped[str] = mapped_column(String(32))
    measure_key: Mapped[str] = mapped_column(String(100))
    analysis_version: Mapped[str] = mapped_column(String(48))
    canonical_metric_version: Mapped[str] = mapped_column(String(40))
    period_end: Mapped[date] = mapped_column(Date)
    period_kind: Mapped[str] = mapped_column(String(24))
    fiscal_quarter: Mapped[int] = mapped_column(Integer)
    revision_policy: Mapped[str] = mapped_column(String(32))
    value_json: Mapped[int | float | None] = mapped_column(JSON)
    unit: Mapped[str] = mapped_column(String(40))
    formula: Mapped[str] = mapped_column(Text)
    quality_state: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text)
    input_fingerprint: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "measure_kind IN ('normalized_fact', 'derived_measure')",
            name="ck_research_derived_measure_kind",
        ),
        CheckConstraint(
            "fiscal_quarter BETWEEN 1 AND 4",
            name="ck_research_derived_measure_quarter",
        ),
        UniqueConstraint(
            "filer_cik",
            "measure_kind",
            "measure_key",
            "analysis_version",
            "period_end",
            "fiscal_quarter",
            "revision_policy",
            "input_fingerprint",
            name="uq_research_derived_measure_identity",
        ),
        Index(
            "ix_research_derived_measure_period",
            "filer_cik",
            "measure_key",
            "period_end",
        ),
    )


class ResearchDerivedMeasureInput(Base):
    __tablename__ = "research_derived_measure_inputs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    measure_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("portfolio.research_derived_measures.id", ondelete="CASCADE"),
        index=True,
    )
    fact_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("portfolio.research_fact_observations.id", ondelete="RESTRICT"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(80))
    ordinal: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint(
            "measure_id",
            "ordinal",
            name="uq_research_derived_measure_input_ordinal",
        ),
    )


class ResearchDocument(Base):
    __tablename__ = "research_documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    filing_accession_number: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("portfolio.research_filings.accession_number", ondelete="CASCADE"),
        index=True,
    )
    sequence: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    document_name: Mapped[str] = mapped_column(String(255))
    document_type: Mapped[str] = mapped_column(String(32), index=True)
    category: Mapped[str] = mapped_column(String(32))
    sec_url: Mapped[str] = mapped_column(Text)
    declared_size_bytes: Mapped[int | None] = mapped_column(Integer)
    fetched_size_bytes: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(100))
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    extraction_version: Mapped[str] = mapped_column(String(48))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "filing_accession_number",
            "document_name",
            name="uq_research_document_identity",
        ),
    )


class ResearchTextEvidence(Base):
    __tablename__ = "research_text_evidence"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("portfolio.research_documents.id", ondelete="CASCADE"),
        index=True,
    )
    category: Mapped[str] = mapped_column(String(64), index=True)
    heading: Mapped[str] = mapped_column(String(240))
    excerpt: Mapped[str] = mapped_column(Text)
    start_offset: Mapped[int] = mapped_column(Integer)
    end_offset: Mapped[int] = mapped_column(Integer)
    extraction_method: Mapped[str] = mapped_column(String(48))
    extraction_version: Mapped[str] = mapped_column(String(48))
    confidence: Mapped[str] = mapped_column(String(16))
    evidence_fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResearchEntity(Base):
    __tablename__ = "research_entities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    canonical_name: Mapped[str] = mapped_column(String(300))
    normalized_name: Mapped[str] = mapped_column(String(300), unique=True)
    entity_type: Mapped[str] = mapped_column(String(48))
    identifiers: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResearchDocumentEntityRole(Base):
    __tablename__ = "research_document_entity_roles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("portfolio.research_documents.id", ondelete="CASCADE"),
        index=True,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("portfolio.research_entities.id", ondelete="RESTRICT"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(160))
    evidence_excerpt: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(16))
    role_fingerprint: Mapped[str] = mapped_column(String(64), unique=True)


class ResearchClaim(Base):
    __tablename__ = "research_claims"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    filer_cik: Mapped[str] = mapped_column(
        String(10), ForeignKey("portfolio.research_filers.cik", ondelete="CASCADE"), index=True
    )
    claim_kind: Mapped[str] = mapped_column(String(64), index=True)
    statement: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[str] = mapped_column(String(16))
    extraction_version: Mapped[str] = mapped_column(String(48))
    claim_fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResearchClaimDocument(Base):
    __tablename__ = "research_claim_documents"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("portfolio.research_claims.id", ondelete="CASCADE"),
        primary_key=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("portfolio.research_documents.id", ondelete="CASCADE"),
        primary_key=True,
    )


class ResearchOpenQuestion(Base):
    __tablename__ = "research_open_questions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    filer_cik: Mapped[str] = mapped_column(
        String(10), ForeignKey("portfolio.research_filers.cik", ondelete="CASCADE"), index=True
    )
    filing_accession_number: Mapped[str | None] = mapped_column(
        String(20),
        ForeignKey("portfolio.research_filings.accession_number", ondelete="CASCADE"),
        index=True,
    )
    category: Mapped[str] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24))
    extraction_version: Mapped[str] = mapped_column(String(48))
    question_fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
