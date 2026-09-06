from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable, Literal

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from .edgar import EdgarClient
from .freshness import supplement_lagging_company_facts
from .ingestion import ExtractionBundle, build_extraction_bundle
from .models import ResearchAutomationAttempt, ResearchAutomationRun
from .universe import CORE_RESEARCH_UNIVERSE, ResearchCompany


RESEARCH_AUTOMATION_VERSION = "sec-refresh-2026-09-06.1"
DEFAULT_COHORT_KEY = "sec-core-30-public-eligible-2026-09-06.1"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    maximum_delay_seconds: float = 8.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.max_attempts > 5:
            raise ValueError("max_attempts must be between 1 and 5")
        if self.initial_delay_seconds < 0 or self.maximum_delay_seconds < 0:
            raise ValueError("retry delays cannot be negative")

    def delay_after(self, attempt_number: int) -> float:
        return min(
            self.initial_delay_seconds * (2 ** max(0, attempt_number - 1)),
            self.maximum_delay_seconds,
        )


@dataclass(frozen=True, slots=True)
class RefreshAttempt:
    cik: str
    ticker: str
    attempt_number: int
    status: Literal["completed", "failed"]
    reason_code: str | None
    retryable: bool
    ingestion_run_id: str | None
    fact_count: int | None
    filing_count: int | None
    started_at: datetime
    completed_at: datetime


@dataclass(frozen=True, slots=True)
class CompanyRefresh:
    cik: str
    ticker: str
    status: Literal["completed", "failed"]
    attempts: tuple[RefreshAttempt, ...]


@dataclass(frozen=True, slots=True)
class RefreshReport:
    cohort_key: str
    trigger_kind: Literal["scheduled", "admin"]
    status: Literal["completed", "completed_with_failures", "failed"]
    period_start: date
    started_at: datetime
    completed_at: datetime
    companies: tuple[CompanyRefresh, ...]
    publication_status: Literal["withheld"] = "withheld"
    publication_performed: bool = False

    @property
    def succeeded_count(self) -> int:
        return sum(company.status == "completed" for company in self.companies)

    @property
    def failed_count(self) -> int:
        return sum(company.status == "failed" for company in self.companies)


def is_retryable_refresh_error(exc: Exception) -> bool:
    if isinstance(exc, requests.HTTPError):
        status_code = exc.response.status_code if exc.response is not None else None
        return status_code in {408, 425, 429} or (
            status_code is not None and status_code >= 500
        )
    return isinstance(exc, (requests.Timeout, requests.ConnectionError, TimeoutError))


def run_research_refresh(
    client: EdgarClient,
    *,
    targets: Iterable[ResearchCompany] = CORE_RESEARCH_UNIVERSE,
    period_start: date = date(2022, 1, 1),
    trigger_kind: Literal["scheduled", "admin"] = "scheduled",
    cohort_key: str = DEFAULT_COHORT_KEY,
    retry_policy: RetryPolicy = RetryPolicy(),
    persist_bundle: Callable[[ExtractionBundle], str | None] | None = None,
    observe_attempt: Callable[[RefreshAttempt], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> RefreshReport:
    """Refresh targets independently and never promote partial results."""
    if trigger_kind not in {"scheduled", "admin"}:
        raise ValueError("trigger_kind must be scheduled or admin")
    candidates = tuple(targets)
    if not candidates:
        raise ValueError("at least one refresh target is required")

    started_at = clock()
    company_results: list[CompanyRefresh] = []
    for candidate in candidates:
        attempts: list[RefreshAttempt] = []
        for attempt_number in range(1, retry_policy.max_attempts + 1):
            attempt_started = clock()
            try:
                bundle = build_extraction_bundle(
                    client.submissions(candidate.cik),
                    client.company_facts(candidate.cik),
                    period_start=period_start,
                )
                facts = supplement_lagging_company_facts(client, bundle)
                bundle = replace(bundle, facts=facts)
                ingestion_run_id = persist_bundle(bundle) if persist_bundle else None
                attempt = RefreshAttempt(
                    cik=candidate.cik,
                    ticker=candidate.ticker,
                    attempt_number=attempt_number,
                    status="completed",
                    reason_code=None,
                    retryable=False,
                    ingestion_run_id=ingestion_run_id,
                    fact_count=len(bundle.facts),
                    filing_count=len(bundle.source_filings),
                    started_at=attempt_started,
                    completed_at=clock(),
                )
            except Exception as exc:  # one target cannot abort the cohort run
                retryable = is_retryable_refresh_error(exc)
                attempt = RefreshAttempt(
                    cik=candidate.cik,
                    ticker=candidate.ticker,
                    attempt_number=attempt_number,
                    status="failed",
                    reason_code=type(exc).__name__,
                    retryable=retryable,
                    ingestion_run_id=None,
                    fact_count=None,
                    filing_count=None,
                    started_at=attempt_started,
                    completed_at=clock(),
                )
            attempts.append(attempt)
            if observe_attempt is not None:
                observe_attempt(attempt)
            if attempt.status == "completed":
                break
            if not attempt.retryable or attempt_number == retry_policy.max_attempts:
                break
            sleep(retry_policy.delay_after(attempt_number))
        company_results.append(
            CompanyRefresh(
                cik=candidate.cik,
                ticker=candidate.ticker,
                status=("completed" if attempts[-1].status == "completed" else "failed"),
                attempts=tuple(attempts),
            )
        )

    successes = sum(item.status == "completed" for item in company_results)
    if successes == len(company_results):
        status = "completed"
    elif successes:
        status = "completed_with_failures"
    else:
        status = "failed"
    return RefreshReport(
        cohort_key=cohort_key,
        trigger_kind=trigger_kind,
        status=status,
        period_start=period_start,
        started_at=started_at,
        completed_at=clock(),
        companies=tuple(company_results),
    )


def begin_automation_run(
    database: Session,
    *,
    trigger_kind: Literal["scheduled", "admin"],
    cohort_key: str,
    period_start: date,
    target_count: int,
    started_at: datetime,
) -> uuid.UUID:
    running = database.scalar(
        select(ResearchAutomationRun.id).where(ResearchAutomationRun.status == "running")
    )
    if running is not None:
        raise RuntimeError("A financial-research automation run is already active")
    row = ResearchAutomationRun(
        trigger_kind=trigger_kind,
        cohort_key=cohort_key,
        status="running",
        period_start=period_start,
        target_count=target_count,
        succeeded_count=0,
        failed_count=0,
        publication_status="withheld",
        started_at=started_at,
    )
    database.add(row)
    database.flush()
    return row.id


def recover_stale_automation_runs(
    database: Session,
    *,
    now: datetime,
    stale_after: timedelta = timedelta(hours=2),
) -> int:
    if stale_after < timedelta(minutes=15):
        raise ValueError("stale_after must be at least 15 minutes")
    stale = list(
        database.scalars(
            select(ResearchAutomationRun).where(
                ResearchAutomationRun.status == "running",
                ResearchAutomationRun.started_at < now - stale_after,
            )
        ).all()
    )
    for row in stale:
        row.status = "failed"
        row.failed_count = max(0, row.target_count - row.succeeded_count)
        row.publication_status = "withheld"
        row.completed_at = now
    database.flush()
    return len(stale)


def record_automation_attempt(
    database: Session,
    *,
    automation_run_id: uuid.UUID,
    attempt: RefreshAttempt,
) -> None:
    database.add(
        ResearchAutomationAttempt(
            automation_run_id=automation_run_id,
            filer_cik=attempt.cik,
            ticker=attempt.ticker,
            attempt_number=attempt.attempt_number,
            status=attempt.status,
            reason_code=attempt.reason_code,
            retryable=attempt.retryable,
            ingestion_run_id=(
                uuid.UUID(attempt.ingestion_run_id) if attempt.ingestion_run_id else None
            ),
            fact_count=attempt.fact_count,
            filing_count=attempt.filing_count,
            started_at=attempt.started_at,
            completed_at=attempt.completed_at,
        )
    )
    database.flush()


def finish_automation_run(
    database: Session,
    *,
    automation_run_id: uuid.UUID,
    report: RefreshReport,
) -> None:
    row = database.get(ResearchAutomationRun, automation_run_id)
    if row is None:
        raise LookupError("Automation run does not exist")
    row.status = report.status
    row.succeeded_count = report.succeeded_count
    row.failed_count = report.failed_count
    row.publication_status = "withheld"
    row.completed_at = report.completed_at
    database.flush()


def fail_automation_run(
    database: Session,
    *,
    automation_run_id: uuid.UUID,
    completed_at: datetime,
) -> None:
    row = database.get(ResearchAutomationRun, automation_run_id)
    if row is None:
        raise LookupError("Automation run does not exist")
    row.status = "failed"
    row.failed_count = max(0, row.target_count - row.succeeded_count)
    row.publication_status = "withheld"
    row.completed_at = completed_at
    database.flush()
