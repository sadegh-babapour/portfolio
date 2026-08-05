"""Create portfolio contact workflow tables.

Revision ID: 20260805_01
Revises:
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260805_01"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS portfolio")
    op.create_table(
        "contact_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("subject", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("verification_digest", sa.String(length=64), nullable=False),
        sa.Column("verification_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("verification_digest"),
        schema="portfolio",
    )
    op.create_index("ix_contact_messages_email", "contact_messages", ["email"], schema="portfolio")
    op.create_index("ix_contact_messages_status", "contact_messages", ["status"], schema="portfolio")
    op.create_index("ix_contact_messages_verification_expires_at", "contact_messages", ["verification_expires_at"], schema="portfolio")
    op.create_index("ix_contact_messages_created_at", "contact_messages", ["created_at"], schema="portfolio")

    op.create_table(
        "contact_attempts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=False),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        schema="portfolio",
    )
    op.create_index("ix_contact_attempts_created_at", "contact_attempts", ["created_at"], schema="portfolio")
    op.create_index("ix_contact_attempt_ip_created", "contact_attempts", ["ip_hash", "created_at"], schema="portfolio")
    op.create_index("ix_contact_attempt_email_created", "contact_attempts", ["email_hash", "created_at"], schema="portfolio")

    op.create_table(
        "contact_audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["portfolio.contact_messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema="portfolio",
    )
    op.create_index("ix_contact_audit_events_message_id", "contact_audit_events", ["message_id"], schema="portfolio")
    op.create_index("ix_contact_audit_events_event_type", "contact_audit_events", ["event_type"], schema="portfolio")
    op.create_index("ix_contact_audit_events_created_at", "contact_audit_events", ["created_at"], schema="portfolio")


def downgrade() -> None:
    op.drop_table("contact_audit_events", schema="portfolio")
    op.drop_table("contact_attempts", schema="portfolio")
    op.drop_table("contact_messages", schema="portfolio")
