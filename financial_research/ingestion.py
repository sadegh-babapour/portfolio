from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Mapping

from sqlalchemy import delete, select, union
from sqlalchemy.orm import Session

from .contracts import CompanyProfile, ExtractionIssue, FactObservation, FilingMetadata
from .edgar import (
    EdgarResponseError,
    base_form,
    extract_acceptance_times,
    extract_company_profile,
    extract_facts,
    extract_filing_metadata,
    normalize_cik,
)
from .metrics import CANONICAL_METRIC_VERSION, CANONICAL_METRICS, metric_for_fact
from .models import (
    ResearchCanonicalMapping,
    ResearchFactMetricMapping,
    ResearchFactObservation,
    ResearchFiler,
    ResearchFiling,
    ResearchIngestionRun,
    ResearchReject,
    ResearchSecurity,
    ResearchTransformationVersion,
)
from .provenance import fact_fingerprint, payload_sha256


EXTRACTION_VERSION = "edgar-json-2026-09-05.1"
INGESTION_RUN_RETENTION_DAYS = 730


@dataclass(frozen=True, slots=True)
class ExtractionBundle:
    profile: CompanyProfile
    source_filings: tuple[FilingMetadata, ...]
    facts: tuple[FactObservation, ...]
    issues: tuple[ExtractionIssue, ...]
    period_start: date
    submissions_sha256: str
    companyfacts_sha256: str


@dataclass(frozen=True, slots=True)
class PersistenceSummary:
    run_id: str
    filings_inserted: int
    facts_inserted: int
    facts_seen_again: int
    facts_mapped: int
    rejects_recorded: int


def build_extraction_bundle(
    submissions: Mapping[str, Any],
    companyfacts: Mapping[str, Any],
    *,
    period_start: date = date(2022, 1, 1),
) -> ExtractionBundle:
    profile = extract_company_profile(submissions, period_start=period_start)
    companyfacts_cik = normalize_cik(companyfacts.get("cik", ""))
    if companyfacts_cik != profile.cik:
        raise EdgarResponseError(
            f"Submissions CIK {profile.cik} does not match Company Facts CIK "
            f"{companyfacts_cik}"
        )
    acceptance_times = extract_acceptance_times(submissions)
    facts = extract_facts(
        companyfacts,
        accepted_at_by_accession=acceptance_times,
        period_start=period_start,
    )
    recent_filings = extract_filing_metadata(
        submissions,
        forms=None,
        period_start=period_start,
    )
    filing_by_accession = {
        filing.accession_number: filing for filing in recent_filings
    }
    issues: list[ExtractionIssue] = []

    for fact in facts:
        if fact.accession_number in filing_by_accession:
            continue
        filing_by_accession[fact.accession_number] = FilingMetadata(
            cik=fact.cik,
            accession_number=fact.accession_number,
            form=fact.form,
            filed_on=fact.filed_on,
            report_period_end=fact.period_end,
            accepted_at=fact.accepted_at,
            primary_document=None,
            primary_document_description=None,
            is_amendment=fact.is_amendment,
            is_inline_xbrl=None,
            sec_index_url=fact.sec_index_url,
            metadata_source="companyfacts_fallback",
        )
        issues.append(
            ExtractionIssue(
                stage="filing_join",
                source_locator=fact.accession_number,
                reason_code="submission_metadata_missing",
                detail="Fact accession was absent from the loaded Submissions records.",
                bounded_context={"fact_form": fact.form},
            )
        )

    required_accessions = {
        *(filing.accession_number for filing in profile.filings),
        *(fact.accession_number for fact in facts),
    }
    source_filings = tuple(
        sorted(
            (
                filing
                for accession, filing in filing_by_accession.items()
                if accession in required_accessions
            ),
            key=lambda filing: (filing.filed_on, filing.accession_number),
        )
    )
    return ExtractionBundle(
        profile=profile,
        source_filings=source_filings,
        facts=facts,
        issues=tuple(issues),
        period_start=period_start,
        submissions_sha256=payload_sha256(submissions),
        companyfacts_sha256=payload_sha256(companyfacts),
    )


def _mapping_specification() -> dict[str, Any]:
    return {
        "version": CANONICAL_METRIC_VERSION,
        "selection": {
            "match": "exact taxonomy + concept + unit + context kind",
            "label_matching": False,
            "company_override_precedence": True,
            "ambiguous_match_policy": "reject",
        },
        "metrics": [asdict(metric) for metric in CANONICAL_METRICS],
    }


def _seed_mapping_catalog(
    database: Session,
) -> dict[tuple[str, str, str, str, str, str], ResearchCanonicalMapping]:
    existing = list(
        database.scalars(
            select(ResearchCanonicalMapping).where(
                ResearchCanonicalMapping.metric_version == CANONICAL_METRIC_VERSION
            )
        ).all()
    )
    by_identity = {
        (
            row.metric_key,
            row.taxonomy,
            row.concept,
            row.unit,
            row.context_kind,
            row.scope_cik,
        ): row
        for row in existing
    }
    for metric in CANONICAL_METRICS:
        definition = {
            "label": metric.label,
            "statement": metric.statement,
            "description": metric.description,
            "expected_units": list(metric.expected_units),
        }
        for candidate in metric.candidates:
            for unit in metric.expected_units:
                scope_cik = candidate.filer_cik or "*"
                identity = (
                    metric.key,
                    candidate.taxonomy,
                    candidate.concept,
                    unit,
                    metric.context_kind,
                    scope_cik,
                )
                if identity in by_identity:
                    continue
                row = ResearchCanonicalMapping(
                    metric_key=metric.key,
                    metric_version=CANONICAL_METRIC_VERSION,
                    taxonomy=candidate.taxonomy,
                    concept=candidate.concept,
                    unit=unit,
                    context_kind=metric.context_kind,
                    priority=candidate.priority,
                    scope_cik=scope_cik,
                    definition=definition,
                )
                database.add(row)
                by_identity[identity] = row
    database.flush()
    return by_identity


def persist_extraction_bundle(
    database: Session,
    bundle: ExtractionBundle,
    *,
    observed_at: datetime | None = None,
) -> PersistenceSummary:
    now = observed_at or datetime.now(timezone.utc)
    filer = database.get(ResearchFiler, bundle.profile.cik)
    if filer is None:
        filer = ResearchFiler(
            cik=bundle.profile.cik,
            name=bundle.profile.name,
            sic=bundle.profile.sic,
            sic_description=bundle.profile.sic_description,
            former_names=list(bundle.profile.former_names),
            first_seen_at=now,
            last_seen_at=now,
        )
        database.add(filer)
    else:
        filer.name = bundle.profile.name
        filer.sic = bundle.profile.sic
        filer.sic_description = bundle.profile.sic_description
        filer.former_names = list(bundle.profile.former_names)
        filer.last_seen_at = now
    database.flush()

    run = ResearchIngestionRun(
        filer_cik=bundle.profile.cik,
        status="running",
        period_start=bundle.period_start,
        extraction_version=EXTRACTION_VERSION,
        submissions_sha256=bundle.submissions_sha256,
        companyfacts_sha256=bundle.companyfacts_sha256,
        counts={},
        started_at=now,
    )
    database.add(run)
    database.flush()

    security_rows = list(
        database.scalars(
            select(ResearchSecurity).where(
                ResearchSecurity.filer_cik == bundle.profile.cik
            )
        ).all()
    )
    securities = {(row.ticker, row.exchange): row for row in security_rows}
    for security in bundle.profile.securities:
        identity = (security.ticker, security.exchange or "")
        row = securities.get(identity)
        if row is None:
            row = ResearchSecurity(
                filer_cik=bundle.profile.cik,
                ticker=identity[0],
                exchange=identity[1],
                first_seen_at=now,
                last_seen_at=now,
            )
            database.add(row)
            securities[identity] = row
        else:
            row.last_seen_at = now

    existing_filings = {
        filing.accession_number: filing
        for filing in database.scalars(
            select(ResearchFiling).where(
                ResearchFiling.accession_number.in_(
                    [item.accession_number for item in bundle.source_filings]
                )
            )
        ).all()
    }
    filings_inserted = 0
    for filing in bundle.source_filings:
        row = existing_filings.get(filing.accession_number)
        if row is None:
            row = ResearchFiling(
                accession_number=filing.accession_number,
                filer_cik=filing.cik,
                form=filing.form,
                base_form=base_form(filing.form),
                filed_on=filing.filed_on,
                report_period_end=filing.report_period_end,
                accepted_at=filing.accepted_at,
                primary_document=filing.primary_document,
                primary_document_description=filing.primary_document_description,
                is_amendment=filing.is_amendment,
                is_inline_xbrl=filing.is_inline_xbrl,
                sec_index_url=filing.sec_index_url,
                metadata_source=filing.metadata_source,
                first_seen_run_id=run.id,
                last_seen_run_id=run.id,
                first_seen_at=now,
                last_seen_at=now,
            )
            database.add(row)
            existing_filings[filing.accession_number] = row
            filings_inserted += 1
        else:
            row.last_seen_run_id = run.id
            row.last_seen_at = now
            if row.accepted_at is None and filing.accepted_at is not None:
                row.accepted_at = filing.accepted_at
    database.flush()

    mapping_catalog = _seed_mapping_catalog(database)
    transformation = database.scalar(
        select(ResearchTransformationVersion).where(
            ResearchTransformationVersion.kind == "canonical_metric_catalog",
            ResearchTransformationVersion.version == CANONICAL_METRIC_VERSION,
        )
    )
    if transformation is None:
        database.add(
            ResearchTransformationVersion(
                kind="canonical_metric_catalog",
                version=CANONICAL_METRIC_VERSION,
                specification=_mapping_specification(),
            )
        )

    fingerprints = {fact_fingerprint(fact) for fact in bundle.facts}
    existing_facts = {
        fact.source_fingerprint: fact
        for fact in database.scalars(
            select(ResearchFactObservation).where(
                ResearchFactObservation.source_fingerprint.in_(fingerprints)
            )
        ).all()
    }
    mapped_fact_ids = set(
        database.scalars(
            select(ResearchFactMetricMapping.fact_id).where(
                ResearchFactMetricMapping.metric_version == CANONICAL_METRIC_VERSION
            )
        ).all()
    )
    facts_inserted = 0
    facts_seen_again = 0
    facts_mapped = 0
    for fact in bundle.facts:
        fingerprint = fact_fingerprint(fact)
        fact_row = existing_facts.get(fingerprint)
        if fact_row is None:
            fact_row = ResearchFactObservation(
                id=uuid.uuid4(),
                source_fingerprint=fingerprint,
                filer_cik=fact.cik,
                accession_number=fact.accession_number,
                taxonomy=fact.taxonomy,
                concept=fact.concept,
                label=fact.label,
                description=fact.description,
                unit=fact.unit,
                value_json=fact.value,
                period_start=fact.period_start,
                period_end=fact.period_end,
                filed_on=fact.filed_on,
                accepted_at=fact.accepted_at,
                fiscal_year=fact.fiscal_year,
                fiscal_period=fact.fiscal_period,
                form=fact.form,
                frame=fact.frame,
                context_kind=fact.context_kind,
                is_amendment=fact.is_amendment,
                sec_index_url=fact.sec_index_url,
                first_seen_run_id=run.id,
                last_seen_run_id=run.id,
                first_seen_at=now,
                last_seen_at=now,
            )
            database.add(fact_row)
            existing_facts[fingerprint] = fact_row
            facts_inserted += 1
        else:
            fact_row.last_seen_run_id = run.id
            fact_row.last_seen_at = now
            if fact_row.accepted_at is None and fact.accepted_at is not None:
                fact_row.accepted_at = fact.accepted_at
            facts_seen_again += 1

        resolved = metric_for_fact(
            cik=fact.cik,
            taxonomy=fact.taxonomy,
            concept=fact.concept,
            unit=fact.unit,
            context_kind=fact.context_kind,
        )
        if resolved is not None and fact_row.id not in mapped_fact_ids:
            metric, candidate = resolved
            scope_cik = candidate.filer_cik or "*"
            mapping = mapping_catalog[
                (
                    metric.key,
                    fact.taxonomy,
                    fact.concept,
                    fact.unit,
                    fact.context_kind,
                    scope_cik,
                )
            ]
            database.add(
                ResearchFactMetricMapping(
                    fact_id=fact_row.id,
                    mapping_id=mapping.id,
                    metric_key=metric.key,
                    metric_version=CANONICAL_METRIC_VERSION,
                    quality_state="mapped",
                )
            )
            mapped_fact_ids.add(fact_row.id)
            facts_mapped += 1

    for issue in bundle.issues:
        database.add(
            ResearchReject(
                run_id=run.id,
                filer_cik=bundle.profile.cik,
                stage=issue.stage,
                source_locator=issue.source_locator,
                reason_code=issue.reason_code,
                detail=issue.detail,
                bounded_context=issue.bounded_context,
            )
        )

    run.status = "completed_with_issues" if bundle.issues else "completed"
    run.completed_at = now
    run.counts = {
        "filings_received": len(bundle.source_filings),
        "filings_inserted": filings_inserted,
        "facts_received": len(bundle.facts),
        "facts_inserted": facts_inserted,
        "facts_seen_again": facts_seen_again,
        "facts_mapped": facts_mapped,
        "rejects_recorded": len(bundle.issues),
    }
    database.flush()
    return PersistenceSummary(
        run_id=str(run.id),
        filings_inserted=filings_inserted,
        facts_inserted=facts_inserted,
        facts_seen_again=facts_seen_again,
        facts_mapped=facts_mapped,
        rejects_recorded=len(bundle.issues),
    )


def prune_unreferenced_ingestion_runs(
    database: Session,
    *,
    now: datetime | None = None,
    retention_days: int = INGESTION_RUN_RETENTION_DAYS,
) -> int:
    """Delete old intermediate runs while retaining every provenance anchor."""
    if retention_days < 30:
        raise ValueError("Ingestion-run retention must be at least 30 days")
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
    referenced_run_ids = union(
        select(ResearchFiling.first_seen_run_id),
        select(ResearchFiling.last_seen_run_id),
        select(ResearchFactObservation.first_seen_run_id),
        select(ResearchFactObservation.last_seen_run_id),
    )
    result = database.execute(
        delete(ResearchIngestionRun).where(
            ResearchIngestionRun.status != "running",
            ResearchIngestionRun.completed_at < cutoff,
            ResearchIngestionRun.id.not_in(referenced_run_ids),
        )
    )
    return int(result.rowcount or 0)
