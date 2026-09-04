from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.auth.service import SessionUser
from app.blog.content import BlogValidationError, validate_blog_content
from app.blog.models import BlogPost, BlogPostRevision
from app.contact.database import session_scope


def list_published_posts() -> list[BlogPost]:
    with session_scope() as database:
        return list(
            database.scalars(
                select(BlogPost)
                .where(BlogPost.status == "published")
                .order_by(BlogPost.published_at.desc(), BlogPost.title)
            ).all()
        )


def get_published_post(slug: str) -> BlogPost | None:
    with session_scope() as database:
        return database.scalar(
            select(BlogPost).where(
                BlogPost.slug == slug,
                BlogPost.status == "published",
            )
        )


def list_admin_posts() -> list[BlogPost]:
    with session_scope() as database:
        return list(
            database.scalars(
                select(BlogPost).order_by(BlogPost.updated_at.desc(), BlogPost.title)
            ).all()
        )


def get_admin_post(post_id: uuid.UUID) -> BlogPost | None:
    with session_scope() as database:
        return database.get(BlogPost, post_id)


def delete_post(post_id: uuid.UUID) -> None:
    """Permanently delete one post and its database-cascaded revisions."""
    with session_scope() as database:
        post = database.get(BlogPost, post_id)
        if post is None:
            raise BlogValidationError("Blog post was not found")
        database.delete(post)
        database.commit()


def list_post_revisions(post_id: uuid.UUID) -> list[BlogPostRevision]:
    with session_scope() as database:
        return list(
            database.scalars(
                select(BlogPostRevision)
                .where(BlogPostRevision.post_id == post_id)
                .order_by(BlogPostRevision.version.desc())
            ).all()
        )


def save_post(
    *,
    author: SessionUser,
    post_id: uuid.UUID | None,
    slug: str,
    title: str,
    summary: str,
    body_markdown: str,
    status: str,
) -> BlogPost:
    clean = validate_blog_content(
        slug=slug,
        title=title,
        summary=summary,
        body_markdown=body_markdown,
        status=status,
    )
    now = datetime.now(timezone.utc)
    with session_scope() as database:
        duplicate = database.scalar(
            select(BlogPost.id).where(BlogPost.slug == clean["slug"])
        )
        if duplicate is not None and duplicate != post_id:
            raise BlogValidationError("That slug is already in use")

        if post_id is None:
            post = BlogPost(
                **clean,
                version=1,
                created_by=author.user_id,
                published_at=now if clean["status"] == "published" else None,
            )
            database.add(post)
            database.flush()
        else:
            post = database.get(BlogPost, post_id)
            if post is None:
                raise BlogValidationError("Blog post was not found")
            post.version += 1
            post.slug = clean["slug"]
            post.title = clean["title"]
            post.summary = clean["summary"]
            post.body_markdown = clean["body_markdown"]
            post.status = clean["status"]
            post.updated_at = now
            if clean["status"] == "published" and post.published_at is None:
                post.published_at = now
            elif clean["status"] == "draft":
                post.published_at = None

        database.add(
            BlogPostRevision(
                post_id=post.id,
                version=post.version,
                slug=post.slug,
                title=post.title,
                summary=post.summary,
                body_markdown=post.body_markdown,
                status=post.status,
                created_by=author.user_id,
            )
        )
        database.commit()
        return post
