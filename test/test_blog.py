from __future__ import annotations

import unittest
from pathlib import Path

from app.blog.content import BlogValidationError, render_markdown, validate_blog_content
from app.blog.models import BlogPost, BlogPostRevision
from app.pages.admin_blog import MARKDOWN_EXAMPLE, _slugify


class BlogContentTests(unittest.TestCase):
    def test_validate_blog_content_normalizes_fields(self) -> None:
        content = validate_blog_content(
            slug="  safe-blog-slug  ",
            title="  A useful article  ",
            summary="  A sufficiently detailed summary.  ",
            body_markdown="  This is long enough to become an article body.  ",
            status=" PUBLISHED ",
        )
        self.assertEqual(
            content,
            {
                "slug": "safe-blog-slug",
                "title": "A useful article",
                "summary": "A sufficiently detailed summary.",
                "body_markdown": "This is long enough to become an article body.",
                "status": "published",
            },
        )

    def test_validate_blog_content_rejects_unsafe_slugs(self) -> None:
        for slug in ("spaces here", "double--hyphen", "../path"):
            with self.subTest(slug=slug), self.assertRaisesRegex(BlogValidationError, "Slug"):
                validate_blog_content(
                    slug=slug,
                    title="Valid title",
                    summary="A valid article summary.",
                    body_markdown="A valid article body with sufficient length.",
                    status="draft",
                )

    def test_render_markdown_sanitizes_untrusted_content(self) -> None:
        rendered = render_markdown(
            "## Safe heading\n\n<script>alert('unsafe')</script>\n\n"
            "[unsafe](javascript:alert('x')) [safe](https://example.com)"
        )
        self.assertIn("<h2>Safe heading</h2>", rendered)
        self.assertNotIn("<script", rendered)
        self.assertNotIn('href="javascript:', rendered)
        self.assertIn('href="https://example.com"', rendered)
        self.assertIn('rel="noopener noreferrer"', rendered)

    def test_blog_models_use_portfolio_schema_and_revision_constraint(self) -> None:
        self.assertEqual(BlogPost.__table__.schema, "portfolio")
        self.assertEqual(BlogPostRevision.__table__.schema, "portfolio")
        constraints = {
            constraint.name for constraint in BlogPostRevision.__table__.constraints
        }
        self.assertIn("uq_blog_revision_post_version", constraints)

    def test_admin_editor_samples_and_native_handlers_are_present(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "app" / "pages" / "admin_blog.py"
        ).read_text(encoding="utf-8")

        self.assertEqual(
            _slugify("Why Live Transit Maps Need Delayed Playback!"),
            "why-live-transit-maps-need-delayed-playback",
        )
        self.assertIn("## Why this matters", MARKDOWN_EXAMPLE)
        self.assertIn('new_button.on("click", reset_editor)', source)
        self.assertIn('preview_button.on("click", preview_article)', source)
        self.assertIn('draft_button.on("click", partial(persist, "draft"))', source)
        self.assertIn('delete_button.on("click", open_delete_dialog)', source)
        self.assertIn('confirm_delete_button.on("click", confirm_delete)', source)
        self.assertNotIn("ui.run_javascript", source)


if __name__ == "__main__":
    unittest.main()
