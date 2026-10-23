"""Create the résumé timeline table edited from /admin/resume.

Revision ID: 20261023_10
Revises: 20260906_09
Create Date: 2026-10-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261023_10"
down_revision: Union[str, Sequence[str], None] = "20260906_09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resume_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("period", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("organization", sa.String(length=160), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("summary", sa.String(length=600), nullable=False),
        sa.Column("highlights", sa.JSON(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("visible", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="portfolio",
    )
    op.create_index("ix_resume_entries_position", "resume_entries", ["position"], schema="portfolio")


def downgrade() -> None:
    op.drop_index("ix_resume_entries_position", table_name="resume_entries", schema="portfolio")
    op.drop_table("resume_entries", schema="portfolio")
