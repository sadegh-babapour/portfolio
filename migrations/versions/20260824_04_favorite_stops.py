"""Create signed-in transit stop favorites.

Revision ID: 20260824_04
Revises: 20260824_03
Create Date: 2026-08-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260824_04"
down_revision: Union[str, Sequence[str], None] = "20260824_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "favorite_stops",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("stop_id", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["portfolio.users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "stop_id"),
        schema="portfolio",
    )


def downgrade() -> None:
    op.drop_table("favorite_stops", schema="portfolio")
