"""Create replay-safe EDGAR financial research tables.

Revision ID: 20260905_06
Revises: 20260903_05
Create Date: 2026-09-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260905_06"
down_revision: Union[str, Sequence[str], None] = "20260903_05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_filers",
        sa.Column("cik", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("sic", sa.String(length=8), nullable=True),
        sa.Column("sic_description", sa.String(length=240), nullable=True),
        sa.Column("former_names", sa.JSON(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("cik"),
        schema="portfolio",
    )

    op.create_table(
        "research_ingestion_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("filer_cik", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("extraction_version", sa.String(length=40), nullable=False),
        sa.Column("submissions_sha256", sa.String(length=64), nullable=False),
        sa.Column("companyfacts_sha256", sa.String(length=64), nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["filer_cik"], ["portfolio.research_filers.cik"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'completed_with_issues', 'failed')",
            name="ck_research_ingestion_run_status",
        ),
        schema="portfolio",
    )
    op.create_index("ix_research_ingestion_runs_status", "research_ingestion_runs", ["status"], schema="portfolio")
    op.create_index("ix_research_runs_filer_started", "research_ingestion_runs", ["filer_cik", "started_at"], schema="portfolio")

    op.create_table(
        "research_securities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("filer_cik", sa.String(length=10), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("exchange", sa.String(length=80), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["filer_cik"], ["portfolio.research_filers.cik"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("filer_cik", "ticker", "exchange", name="uq_research_security_identity"),
        schema="portfolio",
    )
    op.create_index("ix_research_securities_ticker", "research_securities", ["ticker"], schema="portfolio")

    op.create_table(
        "research_filings",
        sa.Column("accession_number", sa.String(length=20), nullable=False),
        sa.Column("filer_cik", sa.String(length=10), nullable=False),
        sa.Column("form", sa.String(length=16), nullable=False),
        sa.Column("base_form", sa.String(length=16), nullable=False),
        sa.Column("filed_on", sa.Date(), nullable=False),
        sa.Column("report_period_end", sa.Date(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("primary_document", sa.String(length=255), nullable=True),
        sa.Column("primary_document_description", sa.String(length=255), nullable=True),
        sa.Column("is_amendment", sa.Boolean(), nullable=False),
        sa.Column("is_inline_xbrl", sa.Boolean(), nullable=True),
        sa.Column("sec_index_url", sa.Text(), nullable=False),
        sa.Column("metadata_source", sa.String(length=32), nullable=False),
        sa.Column("first_seen_run_id", sa.Uuid(), nullable=False),
        sa.Column("last_seen_run_id", sa.Uuid(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["filer_cik"], ["portfolio.research_filers.cik"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["first_seen_run_id"], ["portfolio.research_ingestion_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["last_seen_run_id"], ["portfolio.research_ingestion_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("accession_number"),
        schema="portfolio",
    )
    op.create_index("ix_research_filings_filer_cik", "research_filings", ["filer_cik"], schema="portfolio")
    op.create_index("ix_research_filings_base_form", "research_filings", ["base_form"], schema="portfolio")
    op.create_index("ix_research_filings_filed_on", "research_filings", ["filed_on"], schema="portfolio")
    op.create_index("ix_research_filings_report_period_end", "research_filings", ["report_period_end"], schema="portfolio")
    op.create_index("ix_research_filings_accepted_at", "research_filings", ["accepted_at"], schema="portfolio")

    op.create_table(
        "research_fact_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("filer_cik", sa.String(length=10), nullable=False),
        sa.Column("accession_number", sa.String(length=20), nullable=False),
        sa.Column("taxonomy", sa.String(length=80), nullable=False),
        sa.Column("concept", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(length=80), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("filed_on", sa.Date(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("fiscal_period", sa.String(length=16), nullable=True),
        sa.Column("form", sa.String(length=16), nullable=False),
        sa.Column("frame", sa.String(length=40), nullable=True),
        sa.Column("context_kind", sa.String(length=16), nullable=False),
        sa.Column("is_amendment", sa.Boolean(), nullable=False),
        sa.Column("sec_index_url", sa.Text(), nullable=False),
        sa.Column("first_seen_run_id", sa.Uuid(), nullable=False),
        sa.Column("last_seen_run_id", sa.Uuid(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("context_kind IN ('instant', 'duration')", name="ck_research_fact_context_kind"),
        sa.ForeignKeyConstraint(["accession_number"], ["portfolio.research_filings.accession_number"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["filer_cik"], ["portfolio.research_filers.cik"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["first_seen_run_id"], ["portfolio.research_ingestion_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["last_seen_run_id"], ["portfolio.research_ingestion_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_fingerprint"),
        schema="portfolio",
    )
    op.create_index("ix_research_facts_accession", "research_fact_observations", ["accession_number"], schema="portfolio")
    op.create_index("ix_research_facts_semantic_period", "research_fact_observations", ["filer_cik", "taxonomy", "concept", "unit", "period_end"], schema="portfolio")

    op.create_table(
        "research_canonical_mappings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("metric_key", sa.String(length=80), nullable=False),
        sa.Column("metric_version", sa.String(length=40), nullable=False),
        sa.Column("taxonomy", sa.String(length=80), nullable=False),
        sa.Column("concept", sa.String(length=255), nullable=False),
        sa.Column("unit", sa.String(length=80), nullable=False),
        sa.Column("context_kind", sa.String(length=16), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("scope_cik", sa.String(length=10), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("context_kind IN ('instant', 'duration')", name="ck_research_mapping_context_kind"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("metric_key", "metric_version", "taxonomy", "concept", "unit", "context_kind", "scope_cik", name="uq_research_canonical_mapping"),
        schema="portfolio",
    )

    op.create_table(
        "research_fact_metric_mappings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("fact_id", sa.Uuid(), nullable=False),
        sa.Column("mapping_id", sa.Uuid(), nullable=False),
        sa.Column("metric_key", sa.String(length=80), nullable=False),
        sa.Column("metric_version", sa.String(length=40), nullable=False),
        sa.Column("quality_state", sa.String(length=32), nullable=False),
        sa.Column("mapped_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["fact_id"], ["portfolio.research_fact_observations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["mapping_id"], ["portfolio.research_canonical_mappings.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fact_id", "metric_version", name="uq_research_fact_metric_version"),
        schema="portfolio",
    )
    op.create_index("ix_research_fact_metric_mappings_fact_id", "research_fact_metric_mappings", ["fact_id"], schema="portfolio")
    op.create_index("ix_research_fact_mappings_metric", "research_fact_metric_mappings", ["metric_key", "metric_version"], schema="portfolio")

    op.create_table(
        "research_transformation_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("specification", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "version", name="uq_research_transformation_version"),
        schema="portfolio",
    )

    op.create_table(
        "research_rejects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("filer_cik", sa.String(length=10), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("source_locator", sa.String(length=500), nullable=True),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("bounded_context", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["portfolio.research_ingestion_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="portfolio",
    )
    op.create_index("ix_research_rejects_run_id", "research_rejects", ["run_id"], schema="portfolio")
    op.create_index("ix_research_rejects_reason_code", "research_rejects", ["reason_code"], schema="portfolio")


def downgrade() -> None:
    op.drop_table("research_rejects", schema="portfolio")
    op.drop_table("research_fact_metric_mappings", schema="portfolio")
    op.drop_table("research_transformation_versions", schema="portfolio")
    op.drop_table("research_canonical_mappings", schema="portfolio")
    op.drop_table("research_fact_observations", schema="portfolio")
    op.drop_table("research_filings", schema="portfolio")
    op.drop_table("research_securities", schema="portfolio")
    op.drop_table("research_ingestion_runs", schema="portfolio")
    op.drop_table("research_filers", schema="portfolio")
