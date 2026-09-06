"""Create financial filing-document and evidence records.

Revision ID: 20260906_08
Revises: 20260906_07
Create Date: 2026-09-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260906_08"
down_revision: Union[str, Sequence[str], None] = "20260906_07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("filing_accession_number", sa.String(length=20), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("document_name", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("sec_url", sa.Text(), nullable=False),
        sa.Column("declared_size_bytes", sa.Integer(), nullable=True),
        sa.Column("fetched_size_bytes", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
        sa.Column("extraction_version", sa.String(length=48), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["filing_accession_number"],
            ["portfolio.research_filings.accession_number"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "filing_accession_number",
            "document_name",
            name="uq_research_document_identity",
        ),
        schema="portfolio",
    )
    op.create_index(
        "ix_research_documents_filing_accession_number",
        "research_documents",
        ["filing_accession_number"],
        schema="portfolio",
    )
    op.create_index(
        "ix_research_documents_document_type",
        "research_documents",
        ["document_type"],
        schema="portfolio",
    )

    op.create_table(
        "research_text_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("heading", sa.String(length=240), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("extraction_method", sa.String(length=48), nullable=False),
        sa.Column("extraction_version", sa.String(length=48), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["portfolio.research_documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evidence_fingerprint"),
        schema="portfolio",
    )
    op.create_index(
        "ix_research_text_evidence_document_id",
        "research_text_evidence",
        ["document_id"],
        schema="portfolio",
    )
    op.create_index(
        "ix_research_text_evidence_category",
        "research_text_evidence",
        ["category"],
        schema="portfolio",
    )

    op.create_table(
        "research_entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canonical_name", sa.String(length=300), nullable=False),
        sa.Column("normalized_name", sa.String(length=300), nullable=False),
        sa.Column("entity_type", sa.String(length=48), nullable=False),
        sa.Column("identifiers", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name"),
        schema="portfolio",
    )

    op.create_table(
        "research_document_entity_roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=160), nullable=False),
        sa.Column("evidence_excerpt", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("role_fingerprint", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["portfolio.research_documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["portfolio.research_entities.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_fingerprint"),
        schema="portfolio",
    )
    op.create_index(
        "ix_research_document_entity_roles_document_id",
        "research_document_entity_roles",
        ["document_id"],
        schema="portfolio",
    )
    op.create_index(
        "ix_research_document_entity_roles_entity_id",
        "research_document_entity_roles",
        ["entity_id"],
        schema="portfolio",
    )

    op.create_table(
        "research_claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("filer_cik", sa.String(length=10), nullable=False),
        sa.Column("claim_kind", sa.String(length=64), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("extraction_version", sa.String(length=48), nullable=False),
        sa.Column("claim_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["filer_cik"], ["portfolio.research_filers.cik"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("claim_fingerprint"),
        schema="portfolio",
    )
    op.create_index(
        "ix_research_claims_filer_cik",
        "research_claims",
        ["filer_cik"],
        schema="portfolio",
    )
    op.create_index(
        "ix_research_claims_claim_kind",
        "research_claims",
        ["claim_kind"],
        schema="portfolio",
    )

    op.create_table(
        "research_claim_documents",
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["claim_id"], ["portfolio.research_claims.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["portfolio.research_documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("claim_id", "document_id"),
        schema="portfolio",
    )

    op.create_table(
        "research_open_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("filer_cik", sa.String(length=10), nullable=False),
        sa.Column("filing_accession_number", sa.String(length=20), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("extraction_version", sa.String(length=48), nullable=False),
        sa.Column("question_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["filer_cik"], ["portfolio.research_filers.cik"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["filing_accession_number"],
            ["portfolio.research_filings.accession_number"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_fingerprint"),
        schema="portfolio",
    )
    op.create_index(
        "ix_research_open_questions_filer_cik",
        "research_open_questions",
        ["filer_cik"],
        schema="portfolio",
    )
    op.create_index(
        "ix_research_open_questions_filing_accession_number",
        "research_open_questions",
        ["filing_accession_number"],
        schema="portfolio",
    )


def downgrade() -> None:
    op.drop_table("research_open_questions", schema="portfolio")
    op.drop_table("research_claim_documents", schema="portfolio")
    op.drop_table("research_claims", schema="portfolio")
    op.drop_table("research_document_entity_roles", schema="portfolio")
    op.drop_table("research_entities", schema="portfolio")
    op.drop_table("research_text_evidence", schema="portfolio")
    op.drop_table("research_documents", schema="portfolio")
