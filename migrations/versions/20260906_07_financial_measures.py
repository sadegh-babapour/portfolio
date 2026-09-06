"""Create versioned financial analysis measures and evidence links.

Revision ID: 20260906_07
Revises: 20260905_06
Create Date: 2026-09-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260906_07"
down_revision: Union[str, Sequence[str], None] = "20260905_06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_derived_measures",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("filer_cik", sa.String(length=10), nullable=False),
        sa.Column("measure_kind", sa.String(length=32), nullable=False),
        sa.Column("measure_key", sa.String(length=100), nullable=False),
        sa.Column("analysis_version", sa.String(length=48), nullable=False),
        sa.Column("canonical_metric_version", sa.String(length=40), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("period_kind", sa.String(length=24), nullable=False),
        sa.Column("fiscal_quarter", sa.Integer(), nullable=False),
        sa.Column("revision_policy", sa.String(length=32), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("formula", sa.Text(), nullable=False),
        sa.Column("quality_state", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "measure_kind IN ('normalized_fact', 'derived_measure')",
            name="ck_research_derived_measure_kind",
        ),
        sa.CheckConstraint(
            "fiscal_quarter BETWEEN 1 AND 4",
            name="ck_research_derived_measure_quarter",
        ),
        sa.ForeignKeyConstraint(
            ["filer_cik"],
            ["portfolio.research_filers.cik"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
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
        schema="portfolio",
    )
    op.create_index(
        "ix_research_derived_measure_period",
        "research_derived_measures",
        ["filer_cik", "measure_key", "period_end"],
        schema="portfolio",
    )

    op.create_table(
        "research_derived_measure_inputs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("measure_id", sa.Uuid(), nullable=False),
        sa.Column("fact_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=80), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["fact_id"],
            ["portfolio.research_fact_observations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["measure_id"],
            ["portfolio.research_derived_measures.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "measure_id",
            "ordinal",
            name="uq_research_derived_measure_input_ordinal",
        ),
        schema="portfolio",
    )
    op.create_index(
        "ix_research_derived_measure_inputs_measure_id",
        "research_derived_measure_inputs",
        ["measure_id"],
        schema="portfolio",
    )
    op.create_index(
        "ix_research_derived_measure_inputs_fact_id",
        "research_derived_measure_inputs",
        ["fact_id"],
        schema="portfolio",
    )


def downgrade() -> None:
    op.drop_table("research_derived_measure_inputs", schema="portfolio")
    op.drop_table("research_derived_measures", schema="portfolio")
