"""Create authentication identity, role, session, and event tables.

Revision ID: 20260813_02
Revises: 20260805_01
Create Date: 2026-08-13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260813_02"
down_revision: Union[str, Sequence[str], None] = "20260805_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("primary_email", sa.String(length=254), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        schema="portfolio",
    )
    op.create_index("ix_users_primary_email", "users", ["primary_email"], schema="portfolio")
    op.create_index("ix_users_status", "users", ["status"], schema="portfolio")

    op.create_table(
        "external_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["portfolio.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "subject", name="uq_external_identity_provider_subject"),
        schema="portfolio",
    )
    op.create_index("ix_external_identities_user_id", "external_identities", ["user_id"], schema="portfolio")
    op.create_index("ix_external_identity_email", "external_identities", ["email"], schema="portfolio")

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["portfolio.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role"),
        schema="portfolio",
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("csrf_digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["portfolio.users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest"),
        schema="portfolio",
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"], schema="portfolio")
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"], schema="portfolio")
    op.create_index("ix_auth_sessions_revoked_at", "auth_sessions", ["revoked_at"], schema="portfolio")

    op.create_table(
        "oidc_login_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("state_digest", sa.String(length=64), nullable=False),
        sa.Column("nonce_digest", sa.String(length=64), nullable=False),
        sa.Column("browser_digest", sa.String(length=64), nullable=False),
        sa.Column("return_path", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_digest"),
        sa.UniqueConstraint("nonce_digest"),
        sa.UniqueConstraint("browser_digest"),
        schema="portfolio",
    )
    op.create_index("ix_oidc_login_states_expires_at", "oidc_login_states", ["expires_at"], schema="portfolio")

    op.create_table(
        "auth_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["portfolio.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema="portfolio",
    )
    op.create_index("ix_auth_events_user_id", "auth_events", ["user_id"], schema="portfolio")
    op.create_index("ix_auth_events_event_type", "auth_events", ["event_type"], schema="portfolio")
    op.create_index("ix_auth_events_created_at", "auth_events", ["created_at"], schema="portfolio")


def downgrade() -> None:
    op.drop_table("auth_events", schema="portfolio")
    op.drop_table("oidc_login_states", schema="portfolio")
    op.drop_table("auth_sessions", schema="portfolio")
    op.drop_table("user_roles", schema="portfolio")
    op.drop_table("external_identities", schema="portfolio")
    op.drop_table("users", schema="portfolio")
