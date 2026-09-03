from __future__ import annotations

import logging
import uuid
from html import escape
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import Response
from nicegui import app as fastapi_app
from pydantic import BaseModel, Field

from app.admin.service import require_admin
from app.auth.config import AuthSettings
from app.auth.service import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    AuthenticationError,
    SessionUser,
    require_mutation_session,
)
from app.blog.content import BlogValidationError, render_markdown
from app.blog.service import (
    get_admin_post,
    list_admin_posts,
    list_post_revisions,
    list_published_posts,
    save_post,
)


log = logging.getLogger(__name__)
STATIC_SITEMAP_PATHS = (
    "/", "/about", "/resume", "/projects", "/contact", "/dashboard",
    "/blog", "/calgary-transit-live/", "/privacy", "/terms",
)


class BlogPostPayload(BaseModel):
    slug: str = Field(max_length=120)
    title: str = Field(max_length=180)
    summary: str = Field(max_length=320)
    body_markdown: str = Field(max_length=50_000)
    status: str = Field(max_length=20)


class BlogPreviewPayload(BaseModel):
    body_markdown: str = Field(min_length=1, max_length=50_000)


def _post_document(post, *, include_body: bool = False) -> dict:
    value = {
        "id": str(post.id),
        "slug": post.slug,
        "title": post.title,
        "summary": post.summary,
        "status": post.status,
        "version": post.version,
        "published_at": post.published_at,
        "created_at": post.created_at,
        "updated_at": post.updated_at,
    }
    if include_body:
        value["body_markdown"] = post.body_markdown
    return value


def _admin_mutation(request: Request) -> SessionUser:
    settings = AuthSettings.from_env()
    supplied = urlsplit(request.headers.get("origin", ""))
    expected = urlsplit(settings.public_base_url)
    if (supplied.scheme, supplied.netloc) != (expected.scheme, expected.netloc):
        raise HTTPException(status_code=403, detail="Request origin is not allowed")
    try:
        user = require_mutation_session(
            request.cookies.get(SESSION_COOKIE),
            request.cookies.get(CSRF_COOKIE),
            request.headers.get("x-csrf-token"),
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=403, detail="Session expired; reload and try again") from exc
    if "admin" not in user.roles:
        raise HTTPException(status_code=403, detail="Administrator access is required")
    return user


@fastapi_app.get("/api/admin/blog/posts", include_in_schema=False)
def admin_blog_posts(request: Request):
    require_admin(request.cookies.get(SESSION_COOKIE))
    return [_post_document(post) for post in list_admin_posts()]


@fastapi_app.get("/api/admin/blog/posts/{post_id}", include_in_schema=False)
def admin_blog_post(request: Request, post_id: uuid.UUID):
    require_admin(request.cookies.get(SESSION_COOKIE))
    post = get_admin_post(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Blog post was not found")
    result = _post_document(post, include_body=True)
    result["revisions"] = [
        {
            "version": revision.version,
            "status": revision.status,
            "created_at": revision.created_at,
        }
        for revision in list_post_revisions(post_id)
    ]
    return result


@fastapi_app.post("/api/admin/blog/preview", include_in_schema=False)
def preview_blog_post(request: Request, payload: BlogPreviewPayload):
    _admin_mutation(request)
    try:
        return {"html": render_markdown(payload.body_markdown)}
    except BlogValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@fastapi_app.post("/api/admin/blog/posts", include_in_schema=False)
def create_blog_post(request: Request, payload: BlogPostPayload):
    author = _admin_mutation(request)
    try:
        post = save_post(author=author, post_id=None, **payload.model_dump())
    except BlogValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _post_document(post, include_body=True)


@fastapi_app.put("/api/admin/blog/posts/{post_id}", include_in_schema=False)
def update_blog_post(request: Request, post_id: uuid.UUID, payload: BlogPostPayload):
    author = _admin_mutation(request)
    try:
        post = save_post(author=author, post_id=post_id, **payload.model_dump())
    except BlogValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _post_document(post, include_body=True)


@fastapi_app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml():
    base_url = AuthSettings.from_env().public_base_url or "https://www.bizqlab.com"
    urls = [f"{base_url}{path}" for path in STATIC_SITEMAP_PATHS]
    try:
        posts = list_published_posts()
    except Exception:
        log.exception("Unable to include published blog posts in the sitemap")
        posts = []
    entries = [f"<url><loc>{escape(url)}</loc></url>" for url in urls]
    entries.extend(
        f"<url><loc>{escape(f'{base_url}/blog/{post.slug}')}</loc>"
        f"<lastmod>{post.updated_at.date().isoformat()}</lastmod></url>"
        for post in posts
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(entries)
        + "</urlset>"
    )
    return Response(document, media_type="application/xml")


@fastapi_app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    base_url = AuthSettings.from_env().public_base_url or "https://www.bizqlab.com"
    return Response(
        f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n",
        media_type="text/plain",
    )
