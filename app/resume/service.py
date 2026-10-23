"""Résumé timeline reads and writes. `position` orders the entries; new ones go on top.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.contact.database import session_scope
from app.resume.models import ResumeEntry


KINDS = ("work", "education", "project", "milestone")
MAX_HIGHLIGHTS = 8
MAX_SKILLS = 20


class ResumeValidationError(ValueError):
    pass


def _bounded_text(value: str, field: str, minimum: int, maximum: int) -> str:
    normalized = " ".join(str(value or "").split())
    if not minimum <= len(normalized) <= maximum:
        raise ResumeValidationError(f"{field} must be {minimum}–{maximum} characters")
    return normalized


def _items(values: list[str], field: str, limit: int, maximum: int) -> list[str]:
    items = [" ".join(str(value).split()) for value in values]
    items = [item for item in items if item]
    if len(items) > limit:
        raise ResumeValidationError(f"{field}: at most {limit}")
    if any(len(item) > maximum for item in items):
        raise ResumeValidationError(f"{field}: each at most {maximum} characters")
    return items


def validate_entry(
    *,
    period: str,
    title: str,
    organization: str,
    kind: str,
    summary: str,
    highlights: list[str],
    skills: list[str],
    visible: bool,
) -> dict:
    if kind not in KINDS:
        raise ResumeValidationError("Type must be work, education, project or milestone")
    return {
        "period": _bounded_text(period, "Period", 2, 60),
        "title": _bounded_text(title, "Title", 2, 160),
        "organization": _bounded_text(organization, "Organization", 2, 160),
        "kind": kind,
        "summary": _bounded_text(summary, "Summary", 0, 600),
        "highlights": _items(highlights, "Highlights", MAX_HIGHLIGHTS, 200),
        "skills": _items(skills, "Skills", MAX_SKILLS, 40),
        "visible": bool(visible),
    }


def list_entries(*, visible_only: bool) -> list[ResumeEntry]:
    with session_scope() as database:
        query = select(ResumeEntry).order_by(ResumeEntry.position, ResumeEntry.created_at)
        if visible_only:
            query = query.where(ResumeEntry.visible.is_(True))
        return list(database.scalars(query).all())


def get_entry(entry_id: uuid.UUID) -> ResumeEntry | None:
    with session_scope() as database:
        return database.get(ResumeEntry, entry_id)


def save_entry(*, entry_id: uuid.UUID | None, **fields) -> ResumeEntry:
    """Create (at the top of the timeline) or update one entry."""
    clean = validate_entry(**fields)
    with session_scope() as database:
        if entry_id is None:
            first = database.scalar(select(func.min(ResumeEntry.position)))
            entry = ResumeEntry(**clean, position=(first or 0) - 1)
            database.add(entry)
        else:
            entry = database.get(ResumeEntry, entry_id)
            if entry is None:
                raise ResumeValidationError("Entry was not found")
            for name, value in clean.items():
                setattr(entry, name, value)
            entry.updated_at = datetime.now(timezone.utc)
        database.commit()
        return entry


def move_entry(entry_id: uuid.UUID, step: int) -> None:
    """Swap an entry with its neighbour above (-1) or below (+1)."""
    with session_scope() as database:
        entries = list(
            database.scalars(
                select(ResumeEntry).order_by(ResumeEntry.position, ResumeEntry.created_at)
            ).all()
        )
        index = next((i for i, entry in enumerate(entries) if entry.id == entry_id), None)
        if index is None:
            raise ResumeValidationError("Entry was not found")
        other = index + step
        if not 0 <= other < len(entries):
            return
        entries[index], entries[other] = entries[other], entries[index]
        for position, entry in enumerate(entries):
            entry.position = position
        database.commit()


def delete_entry(entry_id: uuid.UUID) -> None:
    with session_scope() as database:
        entry = database.get(ResumeEntry, entry_id)
        if entry is None:
            raise ResumeValidationError("Entry was not found")
        database.delete(entry)
        database.commit()
