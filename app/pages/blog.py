from __future__ import annotations

import logging
from datetime import datetime
from html import escape

from fastapi import HTTPException
from nicegui import ui

from app.blog.content import render_markdown
from app.blog.service import get_published_post, list_published_posts
from app.components.navbar import with_layout


log = logging.getLogger(__name__)


def _published_label(value: datetime | None) -> str:
    return value.strftime("%B %-d, %Y") if value else "Publication date unavailable"


@ui.page("/blog")
@with_layout
def blog_index():
    ui.page_title("Bizqlab Blog")
    ui.add_head_html(
        '<meta name="description" content="Notes about data engineering, analytics, and building Bizqlab projects.">'
        '<link rel="canonical" href="https://www.bizqlab.com/blog">'
    )
    with ui.column().classes("w-full max-w-6xl mx-auto px-4 py-8 sm:px-8 gap-7"):
        with ui.column().classes("gap-3 max-w-4xl"):
            ui.label("Blog").classes("text-4xl sm:text-5xl font-bold")
            ui.label(
                "Practical notes on data engineering, analytics, system decisions, "
                "and what the projects teach along the way."
            ).classes("text-lg text-grey-7 leading-relaxed")
        try:
            posts = list_published_posts()
        except Exception:
            log.exception("Unable to load published blog posts")
            ui.label("The blog is temporarily unavailable.").classes("text-negative")
            return
        if not posts:
            with ui.card().classes("w-full p-6 gap-2 border"):
                ui.label("First article coming soon").classes("text-2xl font-semibold")
                ui.label(
                    "The publishing system is ready; no articles have been published yet."
                ).classes("text-grey-7")
            return
        with ui.element("section").classes("grid w-full grid-cols-1 gap-5 md:grid-cols-2"):
            for post in posts:
                with ui.card().classes("w-full h-full p-5 gap-3"):
                    ui.label(_published_label(post.published_at)).classes(
                        "text-xs uppercase tracking-wide text-grey-7"
                    )
                    ui.label(post.title).classes("text-2xl font-semibold")
                    ui.label(post.summary).classes("text-sm text-grey-7 leading-relaxed")
                    ui.link("Read article →", f"/blog/{post.slug}").classes(
                        "text-primary font-semibold no-underline hover:underline mt-auto"
                    )


@ui.page("/blog/{slug}")
@with_layout
def blog_post(slug: str):
    try:
        post = get_published_post(slug)
    except Exception:
        log.exception("Unable to load blog post %s", slug)
        raise HTTPException(status_code=503, detail="The blog is temporarily unavailable")
    if post is None:
        raise HTTPException(status_code=404, detail="Blog post not found")

    ui.page_title(f"{post.title} — Bizqlab")
    ui.add_head_html(
        f'<meta name="description" content="{escape(post.summary, quote=True)}">'
        f'<link rel="canonical" href="https://www.bizqlab.com/blog/{post.slug}">'
    )
    ui.add_css("""
      .blog-body { font-size:1.05rem; line-height:1.75; }
      .blog-body h1,.blog-body h2,.blog-body h3,.blog-body h4 { margin:1.6em 0 .5em; font-weight:700; }
      .blog-body h1 { font-size:2rem; } .blog-body h2 { font-size:1.6rem; }
      .blog-body h3 { font-size:1.3rem; } .blog-body a { color:var(--q-primary); }
      .blog-body pre { overflow:auto; padding:1rem; border-radius:.75rem; background:#0f172a; color:#e5e7eb; }
      .blog-body code { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
      .blog-body :not(pre)>code { padding:.12rem .3rem; border-radius:.3rem; background:#e2e8f0; color:#0f172a; }
      html[data-theme="dark"] .blog-body :not(pre)>code { background:#334155; color:#f8fafc; }
      .blog-body blockquote { margin-left:0; padding-left:1rem; border-left:4px solid #5898d4; color:#64748b; }
      .blog-body table { width:100%; border-collapse:collapse; display:block; overflow-x:auto; }
      .blog-body th,.blog-body td { padding:.55rem; border:1px solid #94a3b8; }
    """)
    with ui.column().classes("w-full max-w-4xl mx-auto px-4 py-8 sm:px-8 gap-5"):
        ui.link("← All articles", "/blog").classes(
            "text-primary font-semibold no-underline hover:underline"
        )
        ui.label(post.title).classes("text-4xl sm:text-5xl font-bold leading-tight")
        ui.label(post.summary).classes("text-lg text-grey-7 leading-relaxed")
        ui.label(
            f"Published {_published_label(post.published_at)} · Updated {_published_label(post.updated_at)}"
        ).classes("text-sm text-grey-7")
        ui.separator()
        ui.html(render_markdown(post.body_markdown)).classes("blog-body w-full")
