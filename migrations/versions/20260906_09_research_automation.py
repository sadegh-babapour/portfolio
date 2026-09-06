"""Add durable EDGAR automation run visibility.

Revision ID: 20260906_09
Revises: 20260906_08
Create Date: 2026-09-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260906_09"
down_revision: Union[str, Sequence[str], None] = "20260906_08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_automation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("trigger_kind", sa.String(length=24), nullable=False),
        sa.Column("cohort_key", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("succeeded_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("publication_status", sa.String(length=24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "trigger_kind IN ('scheduled', 'admin')",
            name="ck_research_automation_trigger_kind",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'completed_with_failures', 'failed')",
            name="ck_research_automation_status",
        ),
        sa.CheckConstraint(
            "publication_status IN ('withheld', 'ready', 'published')",
            name="ck_research_automation_publication_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="portfolio",
    )
    op.create_index(
        "ix_research_automation_runs_status",
        "research_automation_runs",
        ["status"],
        schema="portfolio",
    )
    op.create_index(
        "ix_research_automation_started",
        "research_automation_runs",
        ["started_at"],
        schema="portfolio",
    )

    op.create_table(
        "research_automation_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("automation_run_id", sa.Uuid(), nullable=False),
        sa.Column("filer_cik", sa.String(length=10), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("ingestion_run_id", sa.Uuid(), nullable=True),
        sa.Column("fact_count", sa.Integer(), nullable=True),
        sa.Column("filing_count", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('completed', 'failed')",
            name="ck_research_automation_attempt_status",
        ),
        sa.ForeignKeyConstraint(
            ["automation_run_id"],
            ["portfolio.research_automation_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"],
            ["portfolio.research_ingestion_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "automation_run_id",
            "filer_cik",
            "attempt_number",
            name="uq_research_automation_attempt",
        ),
        schema="portfolio",
    )
    op.create_index(
        "ix_research_automation_attempts_automation_run_id",
        "research_automation_attempts",
        ["automation_run_id"],
        schema="portfolio",
    )
    op.create_index(
        "ix_research_automation_attempts_filer_cik",
        "research_automation_attempts",
        ["filer_cik"],
        schema="portfolio",
    )


def downgrade() -> None:
    op.drop_table("research_automation_attempts", schema="portfolio")
    op.drop_table("research_automation_runs", schema="portfolio")
