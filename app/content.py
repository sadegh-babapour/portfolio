from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"
SUPPORTED_SCHEMA_VERSION = 1
ALLOWED_TIMELINE_KINDS = {"work", "education", "project", "milestone"}
ALLOWED_VISIBILITY = {"public", "registered"}
ALLOWED_DATA_MODES = {"static_content", "static_snapshot", "scheduled_snapshot", "live_database"}


class ContentValidationError(ValueError):
    """Raised when source-controlled portfolio content violates its contract."""


@dataclass(frozen=True)
class TimelineEntry:
    id: str
    period: str
    title: str
    organization: str
    kind: str
    summary: str
    highlights: tuple[str, ...]
    skills: tuple[str, ...]
    icon: str
    color: str


@dataclass(frozen=True)
class ResumeTimeline:
    heading: str
    intro: str
    entries: tuple[TimelineEntry, ...]


@dataclass(frozen=True)
class ProjectLink:
    label: str
    url: str


@dataclass(frozen=True)
class LabTechnique:
    title: str
    concept: str
    implementation: str
    tradeoff: str


@dataclass(frozen=True)
class ProjectLab:
    heading: str
    intro: str
    techniques: tuple[LabTechnique, ...]
    working_method: str


@dataclass(frozen=True)
class ProjectCaseStudy:
    id: str
    title: str
    status: str
    visibility: str
    featured: bool
    summary: str
    problem: str
    architecture: str
    data_sources: tuple[str, ...]
    pipeline: tuple[str, ...]
    stack: tuple[str, ...]
    outcomes: tuple[str, ...]
    limitations: tuple[str, ...]
    data_mode: str
    links: tuple[ProjectLink, ...]
    lab: ProjectLab | None


@dataclass(frozen=True)
class ProjectCollection:
    heading: str
    intro: str
    projects: tuple[ProjectCaseStudy, ...]


def _read_document(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContentValidationError(f"Content file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContentValidationError(
            f"Invalid JSON in {path.name} at line {exc.lineno}, column {exc.colno}"
        ) from exc
    if not isinstance(value, dict):
        raise ContentValidationError(f"{path.name} must contain a JSON object")
    if value.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise ContentValidationError(
            f"{path.name} schema_version must be {SUPPORTED_SCHEMA_VERSION}"
        )
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContentValidationError(f"{field} must be a non-empty string")
    return value.strip()


def _text_list(value: Any, field: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or (not allow_empty and not value):
        qualifier = "a non-empty" if not allow_empty else "a"
        raise ContentValidationError(f"{field} must be {qualifier} list")
    return tuple(_text(item, f"{field}[]") for item in value)


def _unique_ids(items: list[dict[str, Any]], field: str) -> None:
    ids = [_text(item.get("id"), f"{field}[].id") for item in items]
    if len(ids) != len(set(ids)):
        raise ContentValidationError(f"{field} contains duplicate ids")


def load_resume_timeline(path: Path | None = None) -> ResumeTimeline:
    document = _read_document(path or CONTENT_DIR / "resume_timeline.json")
    raw_entries = document.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ContentValidationError("entries must be a non-empty list")
    if not all(isinstance(entry, dict) for entry in raw_entries):
        raise ContentValidationError("entries must contain objects")
    _unique_ids(raw_entries, "entries")

    entries = []
    for raw in raw_entries:
        kind = _text(raw.get("kind"), "entries[].kind")
        if kind not in ALLOWED_TIMELINE_KINDS:
            raise ContentValidationError(f"Unsupported timeline kind: {kind}")
        entries.append(
            TimelineEntry(
                id=_text(raw.get("id"), "entries[].id"),
                period=_text(raw.get("period"), "entries[].period"),
                title=_text(raw.get("title"), "entries[].title"),
                organization=_text(raw.get("organization"), "entries[].organization"),
                kind=kind,
                summary=_text(raw.get("summary"), "entries[].summary"),
                highlights=_text_list(raw.get("highlights"), "entries[].highlights"),
                skills=_text_list(raw.get("skills"), "entries[].skills"),
                icon=_text(raw.get("icon"), "entries[].icon"),
                color=_text(raw.get("color"), "entries[].color"),
            )
        )
    return ResumeTimeline(
        heading=_text(document.get("heading"), "heading"),
        intro=_text(document.get("intro"), "intro"),
        entries=tuple(entries),
    )


def load_projects(path: Path | None = None) -> ProjectCollection:
    document = _read_document(path or CONTENT_DIR / "projects.json")
    raw_projects = document.get("projects")
    if not isinstance(raw_projects, list) or not raw_projects:
        raise ContentValidationError("projects must be a non-empty list")
    if not all(isinstance(project, dict) for project in raw_projects):
        raise ContentValidationError("projects must contain objects")
    _unique_ids(raw_projects, "projects")

    projects = []
    for raw in raw_projects:
        visibility = _text(raw.get("visibility"), "projects[].visibility")
        if visibility not in ALLOWED_VISIBILITY:
            raise ContentValidationError(f"Unsupported project visibility: {visibility}")
        data_mode = _text(raw.get("data_mode"), "projects[].data_mode")
        if data_mode not in ALLOWED_DATA_MODES:
            raise ContentValidationError(f"Unsupported project data_mode: {data_mode}")
        if not isinstance(raw.get("featured"), bool):
            raise ContentValidationError("projects[].featured must be a boolean")
        raw_links = raw.get("links")
        if not isinstance(raw_links, list):
            raise ContentValidationError("projects[].links must be a list")
        links = []
        for link in raw_links:
            if not isinstance(link, dict):
                raise ContentValidationError("projects[].links must contain objects")
            url = _text(link.get("url"), "projects[].links[].url")
            if not (url.startswith("/") or url.startswith("https://")):
                raise ContentValidationError("Project links must be root-relative or HTTPS")
            links.append(ProjectLink(_text(link.get("label"), "projects[].links[].label"), url))

        raw_lab = raw.get("lab")
        lab = None
        if raw_lab is not None:
            if not isinstance(raw_lab, dict):
                raise ContentValidationError("projects[].lab must be an object")
            raw_techniques = raw_lab.get("techniques")
            if not isinstance(raw_techniques, list) or not raw_techniques:
                raise ContentValidationError("projects[].lab.techniques must be a non-empty list")
            techniques = []
            for technique in raw_techniques:
                if not isinstance(technique, dict):
                    raise ContentValidationError(
                        "projects[].lab.techniques must contain objects"
                    )
                techniques.append(
                    LabTechnique(
                        title=_text(technique.get("title"), "projects[].lab.techniques[].title"),
                        concept=_text(
                            technique.get("concept"),
                            "projects[].lab.techniques[].concept",
                        ),
                        implementation=_text(
                            technique.get("implementation"),
                            "projects[].lab.techniques[].implementation",
                        ),
                        tradeoff=_text(
                            technique.get("tradeoff"),
                            "projects[].lab.techniques[].tradeoff",
                        ),
                    )
                )
            lab = ProjectLab(
                heading=_text(raw_lab.get("heading"), "projects[].lab.heading"),
                intro=_text(raw_lab.get("intro"), "projects[].lab.intro"),
                techniques=tuple(techniques),
                working_method=_text(
                    raw_lab.get("working_method"), "projects[].lab.working_method"
                ),
            )

        projects.append(
            ProjectCaseStudy(
                id=_text(raw.get("id"), "projects[].id"),
                title=_text(raw.get("title"), "projects[].title"),
                status=_text(raw.get("status"), "projects[].status"),
                visibility=visibility,
                featured=raw["featured"],
                summary=_text(raw.get("summary"), "projects[].summary"),
                problem=_text(raw.get("problem"), "projects[].problem"),
                architecture=_text(raw.get("architecture"), "projects[].architecture"),
                data_sources=_text_list(
                    raw.get("data_sources"),
                    "projects[].data_sources",
                    allow_empty=False,
                ),
                pipeline=_text_list(
                    raw.get("pipeline"),
                    "projects[].pipeline",
                    allow_empty=False,
                ),
                stack=_text_list(raw.get("stack"), "projects[].stack", allow_empty=False),
                outcomes=_text_list(raw.get("outcomes"), "projects[].outcomes"),
                limitations=_text_list(raw.get("limitations"), "projects[].limitations"),
                data_mode=data_mode,
                links=tuple(links),
                lab=lab,
            )
        )
    return ProjectCollection(
        heading=_text(document.get("heading"), "heading"),
        intro=_text(document.get("intro"), "intro"),
        projects=tuple(projects),
    )
