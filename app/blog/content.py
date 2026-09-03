from __future__ import annotations

import re

import nh3
from markdown_it import MarkdownIt


SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ALLOWED_STATUSES = frozenset({"draft", "published"})
ALLOWED_TAGS = {
    "a", "blockquote", "br", "code", "em", "h1", "h2", "h3", "h4",
    "hr", "li", "ol", "p", "pre", "strong", "table", "tbody", "td",
    "th", "thead", "tr", "ul",
}
ALLOWED_ATTRIBUTES = {"a": {"href", "title"}}
ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}
MARKDOWN = MarkdownIt(
    "default",
    {"html": False, "linkify": False, "typographer": False},
)


class BlogValidationError(ValueError):
    pass


def _bounded_text(value: str, field: str, minimum: int, maximum: int) -> str:
    normalized = str(value or "").strip()
    if not minimum <= len(normalized) <= maximum:
        raise BlogValidationError(f"{field} must be {minimum}–{maximum} characters")
    return normalized


def validate_blog_content(
    *, slug: str, title: str, summary: str, body_markdown: str, status: str
) -> dict[str, str]:
    clean_slug = str(slug or "").strip().lower()
    if len(clean_slug) > 120 or not SLUG_PATTERN.fullmatch(clean_slug):
        raise BlogValidationError(
            "Slug must use lowercase letters, numbers, and single hyphens"
        )
    clean_status = str(status or "").strip().lower()
    if clean_status not in ALLOWED_STATUSES:
        raise BlogValidationError("Status must be draft or published")
    return {
        "slug": clean_slug,
        "title": _bounded_text(title, "Title", 3, 180),
        "summary": _bounded_text(summary, "Summary", 10, 320),
        "body_markdown": _bounded_text(body_markdown, "Body", 20, 50_000),
        "status": clean_status,
    }


def render_markdown(markdown: str) -> str:
    """Render untrusted Markdown with raw HTML off and sanitize the result."""
    source = _bounded_text(markdown, "Body", 1, 50_000)
    rendered = MARKDOWN.render(source)
    return nh3.clean(
        rendered,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer",
        strip_comments=True,
    )
