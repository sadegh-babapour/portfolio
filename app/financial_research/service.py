from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import text

from financial_research.automation import RefreshReport
from financial_research.publication import PublicationGate, gate_publication_candidate
from financial_research.public_views import (
    load_public_filing_directory,
    load_public_filing_profile,
    load_public_payments_comparison,
    load_public_sector_screen,
)
from app.contact.database import session_scope


log = logging.getLogger(__name__)
SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "paypal_research_sheet.json"
)
REQUIRED_METRIC_FIELDS = {
    "key",
    "label",
    "display_value",
    "state",
    "confidence",
    "source_url",
}


class ResearchPresentationError(ValueError):
    """Raised when a public research snapshot violates its display contract."""


@dataclass(frozen=True, slots=True)
class ReviewedPublicationCandidate:
    document: dict | None
    gate: PublicationGate


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchPresentationError(f"{field} must be non-empty text")
    return value.strip()


def _sec_url(value: object, field: str) -> str:
    url = _text(value, field)
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.sec.gov"
        or not parsed.path.startswith("/Archives/edgar/data/")
    ):
        raise ResearchPresentationError(f"{field} must be an SEC filing URL")
    return url


def _list(value: object, field: str) -> list:
    if not isinstance(value, list):
        raise ResearchPresentationError(f"{field} must be a list")
    return value


def _numeric_series(value: object, field: str, expected_length: int) -> list:
    series = _list(value, field)
    if len(series) != expected_length or any(
        isinstance(item, bool) or not isinstance(item, (int, float)) for item in series
    ):
        raise ResearchPresentationError(
            f"{field} must contain {expected_length} numeric values"
        )
    return series


def _validate_relationships(value: object, field: str) -> list:
    relationships = _list(value, field)
    for item_index, item in enumerate(relationships):
        if not isinstance(item, dict):
            raise ResearchPresentationError(f"{field}[{item_index}] must be an object")
        _text(item.get("entity"), f"{field}[{item_index}].entity")
        _text(item.get("role"), f"{field}[{item_index}].role")
        item["source_url"] = _sec_url(
            item.get("source_url"), f"{field}[{item_index}].source_url"
        )
    return relationships


def _validate_sheet(raw: object, index: int) -> dict:
    if not isinstance(raw, dict):
        raise ResearchPresentationError(f"companies[{index}] must be an object")
    sheet = dict(raw)
    prefix = f"companies[{index}]"
    for field in (
        "slug",
        "company_name",
        "ticker",
        "cik",
        "form",
        "period_end",
        "filed_on",
        "headline",
        "summary",
    ):
        sheet[field] = _text(sheet.get(field), f"{prefix}.{field}")
    sheet["filing_index_url"] = _sec_url(
        sheet.get("filing_index_url"), f"{prefix}.filing_index_url"
    )
    sheet["primary_document_url"] = _sec_url(
        sheet.get("primary_document_url"), f"{prefix}.primary_document_url"
    )

    metrics = _list(sheet.get("metrics"), f"{prefix}.metrics")
    if not metrics:
        raise ResearchPresentationError(f"{prefix}.metrics must not be empty")
    metric_keys: set[str] = set()
    for metric_index, metric in enumerate(metrics):
        if not isinstance(metric, dict) or not REQUIRED_METRIC_FIELDS <= metric.keys():
            raise ResearchPresentationError(
                f"{prefix}.metrics[{metric_index}] is incomplete"
            )
        metric["key"] = _text(metric["key"], f"{prefix}.metrics[{metric_index}].key")
        if metric["key"] in metric_keys:
            raise ResearchPresentationError(f"duplicate metric key {metric['key']}")
        metric_keys.add(metric["key"])
        metric["source_url"] = _sec_url(
            metric["source_url"], f"{prefix}.metrics[{metric_index}].source_url"
        )

    for collection in ("supporting_evidence", "contrary_evidence"):
        items = _list(sheet.get(collection), f"{prefix}.{collection}")
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ResearchPresentationError(
                    f"{prefix}.{collection}[{item_index}] must be an object"
                )
            for field in ("title", "statement", "kind"):
                _text(item.get(field), f"{prefix}.{collection}[{item_index}].{field}")
            item["source_url"] = _sec_url(
                item.get("source_url"),
                f"{prefix}.{collection}[{item_index}].source_url",
            )
    for item_index, item in enumerate(
        _list(sheet.get("unknowns"), f"{prefix}.unknowns")
    ):
        if not isinstance(item, dict):
            raise ResearchPresentationError(
                f"{prefix}.unknowns[{item_index}] must be an object"
            )
        _text(item.get("question"), f"{prefix}.unknowns[{item_index}].question")
        _text(item.get("reason"), f"{prefix}.unknowns[{item_index}].reason")
    historical_events = _list(
        sheet.get("historical_events"), f"{prefix}.historical_events"
    )
    for event_index, event in enumerate(historical_events):
        field = f"{prefix}.historical_events[{event_index}]"
        if not isinstance(event, dict):
            raise ResearchPresentationError(f"{field} must be an object")
        for event_field in ("date", "title", "summary", "current_relevance"):
            _text(event.get(event_field), f"{field}.{event_field}")
        event["source_url"] = _sec_url(
            event.get("source_url"), f"{field}.source_url"
        )
        _validate_relationships(event.get("relationships"), f"{field}.relationships")
        for question_index, question in enumerate(
            _list(event.get("open_questions"), f"{field}.open_questions")
        ):
            _text(question, f"{field}.open_questions[{question_index}]")
    quality_notes = _list(sheet.get("quality_notes"), f"{prefix}.quality_notes")
    for note_index, note in enumerate(quality_notes):
        _text(note, f"{prefix}.quality_notes[{note_index}]")
    quarter_history = _list(sheet.get("quarter_history"), f"{prefix}.quarter_history")
    if len(quarter_history) < 8:
        raise ResearchPresentationError(
            f"{prefix}.quarter_history must contain multi-year quarters"
        )
    numeric_history_fields = (
        "revenue_billions",
        "operating_margin_percent",
        "net_margin_percent",
        "simplified_free_cash_flow_billions",
        "working_capital_billions",
        "diluted_weighted_shares_millions",
    )
    period_ends: list[str] = []
    for history_index, item in enumerate(quarter_history):
        field = f"{prefix}.quarter_history[{history_index}]"
        if not isinstance(item, dict):
            raise ResearchPresentationError(f"{field} must be an object")
        _text(item.get("period"), f"{field}.period")
        period_ends.append(_text(item.get("period_end"), f"{field}.period_end"))
        for numeric_field in numeric_history_fields:
            value = item.get(numeric_field)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ResearchPresentationError(f"{field}.{numeric_field} must be numeric")
        item["source_url"] = _sec_url(item.get("source_url"), f"{field}.source_url")
    if period_ends != sorted(period_ends) or len(period_ends) != len(set(period_ends)):
        raise ResearchPresentationError(
            f"{prefix}.quarter_history periods must be unique and chronological"
        )

    charts = sheet.get("charts")
    if not isinstance(charts, dict):
        raise ResearchPresentationError(f"{prefix}.charts must be an object")
    cash_bridge = charts.get("cash_bridge")
    if not isinstance(cash_bridge, dict):
        raise ResearchPresentationError(f"{prefix}.charts.cash_bridge is required")
    labels = _list(cash_bridge.get("labels"), f"{prefix}.charts.cash_bridge.labels")
    _numeric_series(
        cash_bridge.get("billions"),
        f"{prefix}.charts.cash_bridge.billions",
        len(labels),
    )
    return sheet


def validate_public_research_document(document: object) -> dict:
    if not isinstance(document, dict):
        raise ResearchPresentationError("snapshot root must be an object")
    schema_version = _text(document.get("schema_version"), "schema_version")
    generated_at = _text(document.get("generated_at"), "generated_at")
    companies = [
        _validate_sheet(raw, index)
        for index, raw in enumerate(_list(document.get("companies"), "companies"))
    ]
    if not companies:
        raise ResearchPresentationError("companies must not be empty")
    slugs = [company["slug"] for company in companies]
    if len(slugs) != len(set(slugs)):
        raise ResearchPresentationError("company slugs must be unique")
    return {
        "schema_version": schema_version,
        "generated_at": generated_at,
        "companies": companies,
    }


def prepare_reviewed_publication_candidate(
    document: object,
    refresh: RefreshReport,
) -> ReviewedPublicationCandidate:
    try:
        validated = validate_public_research_document(document)
    except ResearchPresentationError as exc:
        return ReviewedPublicationCandidate(
            document=None,
            gate=PublicationGate(
                ready_for_owner_approval=False,
                gate_version="financial-promotion-2026-09-06.1",
                reasons=(str(exc),),
                approved_ciks=(),
            ),
        )
    return ReviewedPublicationCandidate(
        document=validated,
        gate=gate_publication_candidate(validated, refresh),
    )


def load_public_research(path: Path | None = None) -> dict:
    """Load and validate the deliberately published research boundary."""
    snapshot_path = path or SNAPSHOT_PATH
    try:
        validated = validate_public_research_document(
            json.loads(snapshot_path.read_text(encoding="utf-8"))
        )
        return {
            "available": True,
            **validated,
            "error": None,
        }
    except (OSError, json.JSONDecodeError, ResearchPresentationError) as exc:
        log.warning("Unable to load public financial research snapshot: %s", exc)
        return {
            "available": False,
            "schema_version": None,
            "generated_at": None,
            "companies": [],
            "error": "The reviewed research snapshot is temporarily unavailable.",
        }


def find_company_research(slug: str, path: Path | None = None) -> dict | None:
    research = load_public_research(path)
    if not research["available"]:
        return None
    return next(
        (company for company in research["companies"] if company["slug"] == slug),
        None,
    )


def _set_public_read_timeout(database) -> None:
    bind = database.get_bind()
    if bind.dialect.name == "postgresql":
        database.execute(text("SET LOCAL statement_timeout = '5000ms'"))


@lru_cache(maxsize=4)
def _load_filing_directory_cached(_time_bucket: int) -> dict:
    try:
        with session_scope() as database:
            _set_public_read_timeout(database)
            return load_public_filing_directory(database)
    except Exception as exc:
        log.warning("Unable to load public SEC filing directory: %s", exc)
        return {
            "available": False,
            "version": None,
            "company_count": 0,
            "industries": [],
        }


def load_filing_directory() -> dict:
    return _load_filing_directory_cached(int(time.time() // 300))


@lru_cache(maxsize=96)
def _load_filing_profile_cached(ticker: str, _time_bucket: int) -> dict | None:
    try:
        with session_scope() as database:
            _set_public_read_timeout(database)
            return load_public_filing_profile(database, ticker)
    except Exception as exc:
        log.warning("Unable to load public SEC filing profile for %s: %s", ticker, exc)
        return None


def load_filing_profile(ticker: str) -> dict | None:
    return _load_filing_profile_cached(ticker.lower(), int(time.time() // 300))


@lru_cache(maxsize=4)
def _load_payments_comparison_cached(_time_bucket: int) -> dict:
    try:
        with session_scope() as database:
            _set_public_read_timeout(database)
            return load_public_payments_comparison(database)
    except Exception as exc:
        log.warning("Unable to load public payment comparison: %s", exc)
        return {
            "available": False,
            "version": None,
            "model_version": None,
            "period_end": None,
            "ranking_performed": False,
            "companies": [],
            "comparison_notes": [],
        }


def load_payments_comparison() -> dict:
    return _load_payments_comparison_cached(int(time.time() // 300))


@lru_cache(maxsize=24)
def _load_sector_screen_cached(industry_key: str, _time_bucket: int) -> dict | None:
    try:
        with session_scope() as database:
            _set_public_read_timeout(database)
            return load_public_sector_screen(database, industry_key)
    except Exception as exc:
        log.warning("Unable to load public sector screen for %s: %s", industry_key, exc)
        return None


def load_sector_screen(industry_key: str) -> dict | None:
    return _load_sector_screen_cached(industry_key, int(time.time() // 300))
