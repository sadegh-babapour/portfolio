"""Create database-backed blog posts and immutable revisions.

Revision ID: 20260903_05
Revises: 20260824_04
Create Date: 2026-09-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260903_05"
down_revision: Union[str, Sequence[str], None] = "20260824_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "blog_posts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("summary", sa.String(length=320), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["portfolio.users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
        schema="portfolio",
    )
    op.create_index("ix_blog_posts_status", "blog_posts", ["status"], schema="portfolio")
    op.create_index("ix_blog_posts_created_by", "blog_posts", ["created_by"], schema="portfolio")
    op.create_index("ix_blog_posts_published_at", "blog_posts", ["published_at"], schema="portfolio")

    op.create_table(
        "blog_post_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("post_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("summary", sa.String(length=320), nullable=False),
        sa.Column("body_markdown", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["portfolio.users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["post_id"], ["portfolio.blog_posts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("post_id", "version", name="uq_blog_revision_post_version"),
        schema="portfolio",
    )
    op.create_index("ix_blog_post_revisions_post_id", "blog_post_revisions", ["post_id"], schema="portfolio")


def downgrade() -> None:
    op.drop_index("ix_blog_post_revisions_post_id", table_name="blog_post_revisions", schema="portfolio")
    op.drop_table("blog_post_revisions", schema="portfolio")
    op.drop_index("ix_blog_posts_published_at", table_name="blog_posts", schema="portfolio")
    op.drop_index("ix_blog_posts_created_by", table_name="blog_posts", schema="portfolio")
    op.drop_index("ix_blog_posts_status", table_name="blog_posts", schema="portfolio")
    op.drop_table("blog_posts", schema="portfolio")
