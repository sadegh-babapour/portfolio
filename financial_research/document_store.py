from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .documents import DOCUMENT_EXTRACTION_VERSION, FilingResearchBundle
from .models import (
    ResearchClaim,
    ResearchClaimDocument,
    ResearchDocument,
    ResearchDocumentEntityRole,
    ResearchEntity,
    ResearchFiling,
    ResearchOpenQuestion,
    ResearchTextEvidence,
    ResearchTransformationVersion,
)
from .provenance import payload_sha256


@dataclass(frozen=True, slots=True)
class DocumentPersistenceSummary:
    documents_inserted: int
    evidence_inserted: int
    entities_inserted: int
    roles_inserted: int
    claims_inserted: int
    questions_inserted: int


def _normalized_entity_name(name: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name.casefold()).split())


def persist_filing_research(
    database: Session,
    bundle: FilingResearchBundle,
) -> DocumentPersistenceSummary:
    accession = bundle.filing.accession_number
    if database.get(ResearchFiling, accession) is None:
        raise ValueError("The filing must be persisted before its document research")
    now = datetime.now(timezone.utc)
    transformation = database.scalar(
        select(ResearchTransformationVersion).where(
            ResearchTransformationVersion.kind == "filing_document_extraction",
            ResearchTransformationVersion.version == DOCUMENT_EXTRACTION_VERSION,
        )
    )
    if transformation is None:
        database.add(
            ResearchTransformationVersion(
                kind="filing_document_extraction",
                version=DOCUMENT_EXTRACTION_VERSION,
                specification={
                    "full_document_storage": False,
                    "max_evidence_characters": 8_000,
                    "methods": ["heading_boundary", "keyword_window", "explicit_role"],
                    "missing_policy": "open_question",
                },
            )
        )

    snapshots_by_url = {snapshot.document.sec_url: snapshot for snapshot in bundle.snapshots}
    existing_documents = {
        document.document_name: document
        for document in database.scalars(
            select(ResearchDocument).where(
                ResearchDocument.filing_accession_number == accession
            )
        ).all()
    }
    documents_by_url: dict[str, ResearchDocument] = {}
    documents_inserted = 0
    for document in bundle.documents:
        snapshot = snapshots_by_url.get(document.sec_url)
        stored = existing_documents.get(document.document_name)
        if stored is None:
            stored = ResearchDocument(
                id=uuid.uuid4(),
                filing_accession_number=accession,
                sequence=document.sequence,
                description=document.description,
                document_name=document.document_name,
                document_type=document.document_type,
                category=document.category,
                sec_url=document.sec_url,
                declared_size_bytes=document.size_bytes,
                fetched_size_bytes=snapshot.byte_count if snapshot else None,
                content_type=snapshot.content_type if snapshot else None,
                content_sha256=snapshot.content_sha256 if snapshot else None,
                extraction_version=DOCUMENT_EXTRACTION_VERSION,
                first_seen_at=now,
                last_seen_at=now,
            )
            database.add(stored)
            existing_documents[document.document_name] = stored
            documents_inserted += 1
        else:
            if (
                snapshot
                and stored.content_sha256
                and stored.content_sha256 != snapshot.content_sha256
            ):
                raise ValueError("A previously observed SEC document changed content")
            stored.last_seen_at = now
            if snapshot and stored.content_sha256 is None:
                stored.content_sha256 = snapshot.content_sha256
                stored.content_type = snapshot.content_type
                stored.fetched_size_bytes = snapshot.byte_count
        documents_by_url[document.sec_url] = stored
    database.flush()

    evidence_inserted = 0
    for evidence in bundle.evidence:
        document = documents_by_url[evidence.source_url]
        fingerprint = payload_sha256(
            {
                "document_id": str(document.id),
                "category": evidence.category,
                "start": evidence.start_offset,
                "end": evidence.end_offset,
                "excerpt": evidence.excerpt,
                "version": evidence.extraction_version,
            }
        )
        if database.scalar(
            select(ResearchTextEvidence.id).where(
                ResearchTextEvidence.evidence_fingerprint == fingerprint
            )
        ):
            continue
        database.add(
            ResearchTextEvidence(
                id=uuid.uuid4(),
                document_id=document.id,
                category=evidence.category,
                heading=evidence.heading,
                excerpt=evidence.excerpt,
                start_offset=evidence.start_offset,
                end_offset=evidence.end_offset,
                extraction_method=evidence.extraction_method,
                extraction_version=evidence.extraction_version,
                confidence=evidence.confidence,
                evidence_fingerprint=fingerprint,
            )
        )
        evidence_inserted += 1

    entities_inserted = 0
    roles_inserted = 0
    for role in bundle.entity_roles:
        normalized_name = _normalized_entity_name(role.entity_name)
        entity = database.scalar(
            select(ResearchEntity).where(
                ResearchEntity.normalized_name == normalized_name
            )
        )
        if entity is None:
            entity = ResearchEntity(
                id=uuid.uuid4(),
                canonical_name=role.entity_name,
                normalized_name=normalized_name,
                entity_type=role.entity_type,
                identifiers={},
            )
            database.add(entity)
            database.flush()
            entities_inserted += 1
        document = documents_by_url[role.source_url]
        fingerprint = payload_sha256(
            {
                "document_id": str(document.id),
                "entity_id": str(entity.id),
                "role": role.role,
                "evidence": role.evidence_excerpt,
            }
        )
        if database.scalar(
            select(ResearchDocumentEntityRole.id).where(
                ResearchDocumentEntityRole.role_fingerprint == fingerprint
            )
        ):
            continue
        database.add(
            ResearchDocumentEntityRole(
                id=uuid.uuid4(),
                document_id=document.id,
                entity_id=entity.id,
                role=role.role,
                evidence_excerpt=role.evidence_excerpt,
                confidence=role.confidence,
                role_fingerprint=fingerprint,
            )
        )
        roles_inserted += 1

    claims_inserted = 0
    for claim in bundle.claims:
        fingerprint = payload_sha256(
            {
                "cik": bundle.filing.cik,
                "kind": claim.claim_kind,
                "statement": claim.statement,
                "status": claim.status,
                "version": DOCUMENT_EXTRACTION_VERSION,
                "sources": sorted(claim.source_urls),
            }
        )
        stored_claim = database.scalar(
            select(ResearchClaim).where(ResearchClaim.claim_fingerprint == fingerprint)
        )
        if stored_claim is None:
            stored_claim = ResearchClaim(
                id=uuid.uuid4(),
                filer_cik=bundle.filing.cik,
                claim_kind=claim.claim_kind,
                statement=claim.statement,
                status=claim.status,
                confidence=claim.confidence,
                extraction_version=DOCUMENT_EXTRACTION_VERSION,
                claim_fingerprint=fingerprint,
            )
            database.add(stored_claim)
            database.flush()
            claims_inserted += 1
        linked_ids = set(
            database.scalars(
                select(ResearchClaimDocument.document_id).where(
                    ResearchClaimDocument.claim_id == stored_claim.id
                )
            ).all()
        )
        for source_url in claim.source_urls:
            document = documents_by_url.get(source_url)
            if document is not None and document.id not in linked_ids:
                database.add(
                    ResearchClaimDocument(
                        claim_id=stored_claim.id,
                        document_id=document.id,
                    )
                )
                linked_ids.add(document.id)

    questions_inserted = 0
    for question in bundle.questions:
        fingerprint = payload_sha256(
            {
                "cik": bundle.filing.cik,
                "accession": accession,
                "category": question.category,
                "question": question.question,
                "version": DOCUMENT_EXTRACTION_VERSION,
            }
        )
        if database.scalar(
            select(ResearchOpenQuestion.id).where(
                ResearchOpenQuestion.question_fingerprint == fingerprint
            )
        ):
            continue
        database.add(
            ResearchOpenQuestion(
                id=uuid.uuid4(),
                filer_cik=bundle.filing.cik,
                filing_accession_number=accession,
                category=question.category,
                question=question.question,
                reason=question.reason,
                status=question.status,
                extraction_version=DOCUMENT_EXTRACTION_VERSION,
                question_fingerprint=fingerprint,
            )
        )
        questions_inserted += 1
    database.flush()
    return DocumentPersistenceSummary(
        documents_inserted=documents_inserted,
        evidence_inserted=evidence_inserted,
        entities_inserted=entities_inserted,
        roles_inserted=roles_inserted,
        claims_inserted=claims_inserted,
        questions_inserted=questions_inserted,
    )
