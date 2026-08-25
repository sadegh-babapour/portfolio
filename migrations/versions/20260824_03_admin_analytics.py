"""Create privacy-bounded anonymous page-render events.

Revision ID: 20260824_03
Revises: 20260813_02
Create Date: 2026-08-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260824_03"
down_revision: Union[str, Sequence[str], None] = "20260813_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "page_view_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("path", sa.String(length=160), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="portfolio",
    )
    op.create_index(
        "ix_page_view_events_path", "page_view_events", ["path"], schema="portfolio"
    )
    op.create_index(
        "ix_page_view_events_created_at",
        "page_view_events",
        ["created_at"],
        schema="portfolio",
    )


def downgrade() -> None:
    op.drop_table("page_view_events", schema="portfolio")
