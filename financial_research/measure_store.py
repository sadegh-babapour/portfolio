from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .analysis import ANALYSIS_SPECIFICATION, AnalysisValue, CompanyAnalysis
from .metrics import CANONICAL_METRIC_VERSION
from .models import (
    ResearchDerivedMeasure,
    ResearchDerivedMeasureInput,
    ResearchFactObservation,
    ResearchFiler,
    ResearchTransformationVersion,
)
from .provenance import payload_sha256


MeasureKind = Literal["normalized_fact", "derived_measure"]


def _input_fingerprint(measure_kind: MeasureKind, value: AnalysisValue) -> str:
    return payload_sha256(
        {
            "key": value.key,
            "measure_kind": measure_kind,
            "value": value.value,
            "unit": value.unit,
            "period_end": value.period_end.isoformat(),
            "period_kind": value.period_kind,
            "formula": value.formula,
            "version": value.version,
            "state": value.state,
            "confidence": value.confidence,
            "evidence": [
                {
                    "role": reference.role,
                    "source_fingerprint": reference.source_fingerprint,
                }
                for reference in value.evidence
            ],
        }
    )


def persist_company_analysis(database: Session, analysis: CompanyAnalysis) -> int:
    if database.get(ResearchFiler, analysis.cik) is None:
        raise ValueError("The filer and raw facts must be persisted before analysis")

    transformation = database.scalar(
        select(ResearchTransformationVersion).where(
            ResearchTransformationVersion.kind == "financial_analysis",
            ResearchTransformationVersion.version == ANALYSIS_SPECIFICATION["version"],
        )
    )
    if transformation is None:
        database.add(
            ResearchTransformationVersion(
                kind="financial_analysis",
                version=ANALYSIS_SPECIFICATION["version"],
                specification=ANALYSIS_SPECIFICATION,
            )
        )

    values: tuple[tuple[MeasureKind, AnalysisValue], ...] = tuple(
        ("normalized_fact", value) for value in analysis.normalized_facts
    ) + tuple(("derived_measure", value) for value in analysis.derived_measures)
    evidence_fingerprints = {
        reference.source_fingerprint
        for _, value in values
        for reference in value.evidence
    }
    facts_by_fingerprint = {
        fact.source_fingerprint: fact
        for fact in database.scalars(
            select(ResearchFactObservation).where(
                ResearchFactObservation.source_fingerprint.in_(evidence_fingerprints)
            )
        ).all()
    }
    missing = evidence_fingerprints - facts_by_fingerprint.keys()
    if missing:
        raise ValueError(
            f"Analysis references {len(missing)} raw facts that are not persisted"
        )

    fingerprints = {
        _input_fingerprint(measure_kind, value)
        for measure_kind, value in values
    }
    existing = {
        row.input_fingerprint
        for row in database.scalars(
            select(ResearchDerivedMeasure).where(
                ResearchDerivedMeasure.filer_cik == analysis.cik,
                ResearchDerivedMeasure.analysis_version
                == values[0][1].version,
                ResearchDerivedMeasure.input_fingerprint.in_(fingerprints),
            )
        ).all()
    }
    inserted = 0
    for measure_kind, value in values:
        fingerprint = _input_fingerprint(measure_kind, value)
        if fingerprint in existing:
            continue
        measure = ResearchDerivedMeasure(
            id=uuid.uuid4(),
            filer_cik=analysis.cik,
            measure_kind=measure_kind,
            measure_key=value.key,
            analysis_version=value.version,
            canonical_metric_version=CANONICAL_METRIC_VERSION,
            period_end=value.period_end,
            period_kind=value.period_kind,
            fiscal_quarter=analysis.fiscal_quarter,
            revision_policy=analysis.revision_policy,
            value_json=value.value,
            unit=value.unit,
            formula=value.formula,
            quality_state=value.state,
            confidence=value.confidence,
            note=value.note,
            input_fingerprint=fingerprint,
        )
        database.add(measure)
        for ordinal, reference in enumerate(value.evidence):
            database.add(
                ResearchDerivedMeasureInput(
                    measure_id=measure.id,
                    fact_id=facts_by_fingerprint[reference.source_fingerprint].id,
                    role=reference.role,
                    ordinal=ordinal,
                )
            )
        existing.add(fingerprint)
        inserted += 1
    database.flush()
    return inserted
