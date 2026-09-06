from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .metrics import CANONICAL_METRIC_VERSION
from .models import (
    ResearchCanonicalMapping,
    ResearchDerivedMeasure,
    ResearchDocument,
    ResearchDocumentEntityRole,
    ResearchEntity,
    ResearchFactMetricMapping,
    ResearchFactObservation,
    ResearchOpenQuestion,
    ResearchTextEvidence,
)
from .selection import (
    FactSelection,
    PeriodKind,
    RankedFact,
    RevisionPolicy,
    select_canonical_fact,
)


RevisionView = Literal["originally_reported", "latest_corrected", "history"]
MeasureView = Literal["first_calculated", "latest_calculated", "history"]


def filing_text_evidence(
    database: Session,
    *,
    accession_number: str,
    category: str | None = None,
) -> tuple[ResearchTextEvidence, ...]:
    statement = (
        select(ResearchTextEvidence)
        .join(ResearchDocument, ResearchDocument.id == ResearchTextEvidence.document_id)
        .where(ResearchDocument.filing_accession_number == accession_number)
    )
    if category is not None:
        statement = statement.where(ResearchTextEvidence.category == category)
    return tuple(
        database.scalars(
            statement.order_by(
                ResearchTextEvidence.category,
                ResearchTextEvidence.start_offset,
            )
        ).all()
    )


def entity_role_history(
    database: Session,
    *,
    normalized_entity_name: str,
) -> tuple[ResearchDocumentEntityRole, ...]:
    return tuple(
        database.scalars(
            select(ResearchDocumentEntityRole)
            .join(ResearchEntity, ResearchEntity.id == ResearchDocumentEntityRole.entity_id)
            .where(ResearchEntity.normalized_name == normalized_entity_name)
            .order_by(ResearchDocumentEntityRole.document_id)
        ).all()
    )


def open_research_questions(
    database: Session,
    *,
    filer_cik: str,
) -> tuple[ResearchOpenQuestion, ...]:
    return tuple(
        database.scalars(
            select(ResearchOpenQuestion)
            .where(
                ResearchOpenQuestion.filer_cik == filer_cik,
                ResearchOpenQuestion.status == "open",
            )
            .order_by(ResearchOpenQuestion.created_at, ResearchOpenQuestion.id)
        ).all()
    )


def analysis_measure_history(
    database: Session,
    *,
    filer_cik: str,
    measure_key: str,
    period_end: date,
    analysis_version: str | None = None,
    revision_policy: RevisionPolicy = "latest_corrected",
) -> tuple[ResearchDerivedMeasure, ...]:
    statement = select(ResearchDerivedMeasure).where(
        ResearchDerivedMeasure.filer_cik == filer_cik,
        ResearchDerivedMeasure.measure_key == measure_key,
        ResearchDerivedMeasure.period_end == period_end,
        ResearchDerivedMeasure.revision_policy == revision_policy,
    )
    if analysis_version is not None:
        statement = statement.where(
            ResearchDerivedMeasure.analysis_version == analysis_version
        )
    return tuple(
        database.scalars(
            statement.order_by(
                ResearchDerivedMeasure.created_at,
                ResearchDerivedMeasure.id,
            )
        ).all()
    )


def analysis_measure_view(
    database: Session,
    *,
    view: MeasureView,
    filer_cik: str,
    measure_key: str,
    period_end: date,
    analysis_version: str | None = None,
    revision_policy: RevisionPolicy = "latest_corrected",
) -> ResearchDerivedMeasure | tuple[ResearchDerivedMeasure, ...] | None:
    if view not in {"first_calculated", "latest_calculated", "history"}:
        raise ValueError(f"Unsupported measure view: {view}")
    history = analysis_measure_history(
        database,
        filer_cik=filer_cik,
        measure_key=measure_key,
        period_end=period_end,
        analysis_version=analysis_version,
        revision_policy=revision_policy,
    )
    if view == "history":
        return history
    if not history:
        return None
    return history[0] if view == "first_calculated" else history[-1]


def fact_revision_history(
    database: Session,
    *,
    filer_cik: str,
    taxonomy: str,
    concept: str,
    unit: str,
    period_start: date | None,
    period_end: date,
) -> tuple[ResearchFactObservation, ...]:
    rows = list(
        database.scalars(
            select(ResearchFactObservation).where(
                ResearchFactObservation.filer_cik == filer_cik,
                ResearchFactObservation.taxonomy == taxonomy,
                ResearchFactObservation.concept == concept,
                ResearchFactObservation.unit == unit,
                ResearchFactObservation.period_start == period_start,
                ResearchFactObservation.period_end == period_end,
            )
        ).all()
    )
    def acceptance_order(fact: ResearchFactObservation) -> float:
        if fact.accepted_at is None:
            return float("-inf")
        accepted_at = fact.accepted_at
        if accepted_at.tzinfo is None:
            accepted_at = accepted_at.replace(tzinfo=timezone.utc)
        return accepted_at.timestamp()

    rows.sort(
        key=lambda fact: (
            acceptance_order(fact),
            fact.filed_on,
            fact.accession_number,
        )
    )
    return tuple(rows)


def fact_revision_view(
    database: Session,
    *,
    view: RevisionView,
    filer_cik: str,
    taxonomy: str,
    concept: str,
    unit: str,
    period_start: date | None,
    period_end: date,
) -> ResearchFactObservation | tuple[ResearchFactObservation, ...] | None:
    if view not in {"originally_reported", "latest_corrected", "history"}:
        raise ValueError(f"Unsupported revision view: {view}")
    history = fact_revision_history(
        database,
        filer_cik=filer_cik,
        taxonomy=taxonomy,
        concept=concept,
        unit=unit,
        period_start=period_start,
        period_end=period_end,
    )
    if view == "history":
        return history
    if not history:
        return None
    if view == "originally_reported":
        return history[0]
    if view == "latest_corrected":
        return history[-1]
    raise AssertionError("Revision view validation should make this unreachable")


def canonical_fact_view(
    database: Session,
    *,
    filer_cik: str,
    metric_key: str,
    period_end: date,
    period_kind: PeriodKind,
    view: RevisionPolicy = "latest_corrected",
    metric_version: str = CANONICAL_METRIC_VERSION,
) -> FactSelection:
    rows = database.execute(
        select(ResearchFactObservation, ResearchCanonicalMapping)
        .join(
            ResearchFactMetricMapping,
            ResearchFactMetricMapping.fact_id == ResearchFactObservation.id,
        )
        .join(
            ResearchCanonicalMapping,
            ResearchCanonicalMapping.id == ResearchFactMetricMapping.mapping_id,
        )
        .where(
            ResearchFactObservation.filer_cik == filer_cik,
            ResearchFactObservation.period_end == period_end,
            ResearchFactMetricMapping.metric_key == metric_key,
            ResearchFactMetricMapping.metric_version == metric_version,
        )
    ).all()
    return select_canonical_fact(
        (RankedFact(fact, mapping.priority) for fact, mapping in rows),
        period_end=period_end,
        period_kind=period_kind,
        revision_policy=view,
    )
