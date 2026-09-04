from __future__ import annotations

import logging
import re
import uuid
from functools import partial

from nicegui import ui

from app.admin.service import require_admin
from app.auth.service import SESSION_COOKIE
from app.blog.content import BlogValidationError, render_markdown
from app.blog.service import (
    delete_post,
    get_admin_post,
    list_admin_posts,
    list_post_revisions,
    save_post,
)
from app.components.admin_nav import admin_navigation
from app.components.navbar import with_layout


log = logging.getLogger(__name__)
MARKDOWN_EXAMPLE = """## Why this matters

Explain the problem in plain language.

- Show the important evidence
- Describe the trade-off
- End with the result
"""


def _slugify(value: str) -> str:
    return re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", value.lower()))[:120]


@ui.page("/admin/blog")
@with_layout
def admin_blog():
    request = ui.context.client.request
    require_admin(request.cookies.get(SESSION_COOKIE))
    ui.page_title("Blog publishing — Bizqlab")

    selected: dict[str, uuid.UUID | None] = {"id": None}

    with ui.column().classes("w-full max-w-7xl mx-auto px-4 py-8 sm:px-8 gap-6"):
        admin_navigation("/admin/blog")
        with ui.row().classes("w-full items-start justify-between gap-3 flex-wrap"):
            with ui.column().classes("gap-2"):
                ui.label("Blog publishing").classes("text-4xl font-bold")
                ui.label(
                    "Write and preview safely here. Save draft keeps an article private; "
                    "Publish makes it visible immediately without a Railway rebuild."
                ).classes("text-grey-7")

        with ui.element("section").classes(
            "grid w-full grid-cols-1 gap-5 lg:grid-cols-[minmax(15rem,22rem)_minmax(0,1fr)]"
        ):
            with ui.card().classes("w-full p-4 gap-3"):
                with ui.row().classes("w-full items-center justify-between gap-2"):
                    ui.label("Articles").classes("text-xl font-semibold")
                    new_button = ui.button("New article", icon="add").props("outline no-caps")
                posts_container = ui.column().classes("w-full gap-2")

            with ui.card().classes("w-full min-w-0 p-4 sm:p-6 gap-4"):
                title = ui.input(
                    "Title",
                    placeholder="Why live transit maps need delayed playback",
                ).classes("w-full").props("outlined maxlength=180")
                ui.label(
                    "Example: Why live transit maps need delayed playback"
                ).classes("-mt-3 text-xs text-grey-7")

                with ui.row().classes("w-full items-end gap-3"):
                    slug = ui.input(
                        "URL slug",
                        placeholder="delayed-playback-for-live-transit",
                    ).classes("grow min-w-0").props("outlined maxlength=120")
                    slug_button = ui.button("From title", icon="auto_fix_high").props(
                        "outline no-caps"
                    )
                ui.label(
                    "Example: delayed-playback-for-live-transit — lowercase letters, numbers, and hyphens only"
                ).classes("-mt-3 text-xs text-grey-7")

                summary = ui.textarea(
                    "Summary",
                    placeholder=(
                        "A short explanation of how delayed playback turns sparse vehicle "
                        "observations into a steadier rider-facing map."
                    ),
                ).classes("w-full").props("outlined autogrow maxlength=320")
                ui.label(
                    "Example: one or two sentences shown on the blog index and in search descriptions."
                ).classes("-mt-3 text-xs text-grey-7")

                body = ui.textarea(
                    "Article body · Markdown",
                    placeholder=MARKDOWN_EXAMPLE,
                ).classes("w-full font-mono").props("outlined rows=18 maxlength=50000")
                ui.label(
                    "Example Markdown: ## Heading, **bold**, [link text](https://example.com), and - list items."
                ).classes("-mt-3 text-xs text-grey-7")

                with ui.row().classes("w-full gap-3 flex-wrap"):
                    preview_button = ui.button("Preview", icon="visibility").props(
                        "outline no-caps"
                    )
                    draft_button = ui.button("Save draft", icon="save").props(
                        "outline no-caps"
                    )
                    publish_button = ui.button("Publish", icon="publish").props(
                        "unelevated no-caps color=primary"
                    )
                    delete_button = ui.button("Delete", icon="delete").props(
                        "outline no-caps color=negative"
                    )
                    delete_button.disable()
                status_label = ui.label("New unsaved article").classes(
                    "min-h-6 text-sm text-grey-7"
                )

                with ui.expansion("Sanitized preview", icon="preview").classes(
                    "w-full border rounded-lg"
                ) as preview_panel:
                    preview_output = ui.html(
                        "<p>Choose Preview to render the current Markdown. Preview does not save.</p>"
                    ).classes("blog-preview-output w-full p-4")

                with ui.expansion("Revision history", icon="history").classes(
                    "w-full border rounded-lg"
                ):
                    revisions_container = ui.column().classes("w-full gap-2 p-4")

        with ui.dialog() as delete_dialog, ui.card().classes(
            "w-full max-w-md p-5 gap-4"
        ):
            ui.label("Delete this article?").classes("text-xl font-semibold")
            delete_description = ui.label(
                "The article and every saved revision will be permanently deleted."
            ).classes("text-sm text-grey-7")
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=delete_dialog.close).props("flat no-caps")
                confirm_delete_button = ui.button(
                    "Delete permanently", icon="delete"
                ).props("unelevated no-caps color=negative")

    ui.add_css("""
      .blog-preview-output { line-height: 1.7; }
      .blog-preview-output pre { overflow:auto; padding:1rem; border-radius:.65rem; background:#0f172a; color:#e5e7eb; }
      .blog-preview-output code { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
      .blog-preview-output table { width:100%; border-collapse:collapse; display:block; overflow-x:auto; }
      .blog-preview-output th,.blog-preview-output td { padding:.55rem; border:1px solid #94a3b8; }
    """)

    def current_author():
        return require_admin(request.cookies.get(SESSION_COOKIE))

    def refresh_revisions(post_id: uuid.UUID | None) -> None:
        revisions_container.clear()
        with revisions_container:
            if post_id is None:
                ui.label("Save the article to create its first revision.").classes(
                    "text-sm text-grey-7"
                )
                return
            revisions = list_post_revisions(post_id)
            for revision in revisions:
                ui.label(
                    f"Version {revision.version} · {revision.status} · "
                    f"{revision.created_at.strftime('%Y-%m-%d %H:%M UTC')}"
                ).classes("text-sm")

    def load_post(post_id: uuid.UUID) -> None:
        try:
            current_author()
            post = get_admin_post(post_id)
            if post is None:
                raise BlogValidationError("Blog post was not found")
            selected["id"] = post.id
            delete_button.enable()
            title.set_value(post.title)
            slug.set_value(post.slug)
            summary.set_value(post.summary)
            body.set_value(post.body_markdown)
            status_label.set_text(f"{post.status.title()} · version {post.version}")
            refresh_revisions(post.id)
            refresh_posts()
        except Exception:
            log.exception("Unable to load blog post %s", post_id)
            ui.notify("The article could not be loaded.", type="negative")

    def refresh_posts() -> None:
        posts_container.clear()
        try:
            posts = list_admin_posts()
        except Exception:
            log.exception("Unable to list blog posts")
            with posts_container:
                ui.label("Articles are temporarily unavailable.").classes("text-negative")
            return
        with posts_container:
            if not posts:
                ui.label("No articles yet. Choose New article to begin.").classes(
                    "text-sm text-grey-7"
                )
            for post in posts:
                marker = "●" if post.status == "published" else "○"
                button = ui.button(
                    f"{marker} {post.title}\n{post.status.title()} · v{post.version}",
                    on_click=partial(load_post, post.id),
                ).classes("w-full text-left whitespace-pre-line").props("flat no-caps align=left")
                if post.id == selected["id"]:
                    button.props("color=primary")

    def reset_editor() -> None:
        selected["id"] = None
        delete_button.disable()
        title.set_value("")
        slug.set_value("")
        summary.set_value("")
        body.set_value("")
        status_label.set_text("New unsaved article")
        preview_output.set_content(
            "<p>Choose Preview to render the current Markdown. Preview does not save.</p>"
        )
        refresh_revisions(None)
        refresh_posts()
        title.run_method("focus")

    def generate_slug() -> None:
        generated = _slugify(str(title.value or ""))
        slug.set_value(generated)
        status_label.set_text(
            "Slug generated from the title." if generated else "Enter a title first."
        )

    def preview_article() -> None:
        try:
            current_author()
            preview_output.set_content(render_markdown(str(body.value or "")))
            preview_panel.set_value(True)
            status_label.set_text("Preview updated; it has not been saved.")
        except BlogValidationError as exc:
            status_label.set_text(str(exc))
            ui.notify(str(exc), type="warning")

    def persist(next_status: str) -> None:
        try:
            post = save_post(
                author=current_author(),
                post_id=selected["id"],
                slug=str(slug.value or ""),
                title=str(title.value or ""),
                summary=str(summary.value or ""),
                body_markdown=str(body.value or ""),
                status=next_status,
            )
            selected["id"] = post.id
            delete_button.enable()
            status_label.set_text(f"{post.status.title()} · version {post.version} saved")
            refresh_revisions(post.id)
            refresh_posts()
            ui.notify(
                "Article published." if next_status == "published" else "Draft saved.",
                type="positive",
            )
        except BlogValidationError as exc:
            status_label.set_text(str(exc))
            ui.notify(str(exc), type="warning")
        except Exception:
            log.exception("Unable to save blog post")
            status_label.set_text("The article could not be saved. Please try again.")
            ui.notify("The article could not be saved.", type="negative")

    def open_delete_dialog() -> None:
        if selected["id"] is None:
            ui.notify("Choose a saved article first.", type="warning")
            return
        delete_description.set_text(
            f'“{str(title.value or "Untitled")}” and every saved revision will be '
            "permanently deleted."
        )
        delete_dialog.open()

    def confirm_delete() -> None:
        post_id = selected["id"]
        if post_id is None:
            delete_dialog.close()
            return
        try:
            current_author()
            delete_post(post_id)
            delete_dialog.close()
            reset_editor()
            ui.notify("Article permanently deleted.", type="positive")
        except BlogValidationError as exc:
            delete_dialog.close()
            status_label.set_text(str(exc))
            ui.notify(str(exc), type="warning")
        except Exception:
            log.exception("Unable to delete blog post %s", post_id)
            delete_dialog.close()
            ui.notify("The article could not be deleted.", type="negative")

    new_button.on("click", reset_editor)
    slug_button.on("click", generate_slug)
    preview_button.on("click", preview_article)
    draft_button.on("click", partial(persist, "draft"))
    publish_button.on("click", partial(persist, "published"))
    delete_button.on("click", open_delete_dialog)
    confirm_delete_button.on("click", confirm_delete)

    refresh_revisions(None)
    refresh_posts()
