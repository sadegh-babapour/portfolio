from __future__ import annotations

import argparse
import uuid
from datetime import date, datetime, timezone

from app.contact.database import session_scope
from financial_research.automation import (
    DEFAULT_COHORT_KEY,
    RetryPolicy,
    begin_automation_run,
    fail_automation_run,
    finish_automation_run,
    record_automation_attempt,
    recover_stale_automation_runs,
    run_research_refresh,
)
from financial_research.edgar import EdgarClient
from financial_research.ingestion import ExtractionBundle, persist_extraction_bundle
from financial_research.universe import CORE_RESEARCH_UNIVERSE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh the approved SEC research universe with bounded retries. "
            "Persistence requires explicit --write."
        )
    )
    parser.add_argument("--since", type=date.fromisoformat, default=date(2022, 1, 1))
    parser.add_argument("--trigger", choices=("scheduled", "admin"), default="scheduled")
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    policy = RetryPolicy(max_attempts=args.max_attempts)
    automation_run_id: uuid.UUID | None = None

    if args.write:
        with session_scope() as database:
            recovered = recover_stale_automation_runs(
                database,
                now=datetime.now(timezone.utc),
            )
            automation_run_id = begin_automation_run(
                database,
                trigger_kind=args.trigger,
                cohort_key=DEFAULT_COHORT_KEY,
                period_start=args.since,
                target_count=len(CORE_RESEARCH_UNIVERSE),
                started_at=datetime.now(timezone.utc),
            )
            database.commit()
        if recovered:
            print(f"Recovered {recovered} stale automation run(s) as failed.")

    def persist(bundle: ExtractionBundle) -> str | None:
        if not args.write:
            return None
        with session_scope() as database:
            summary = persist_extraction_bundle(database, bundle)
            database.commit()
            return summary.run_id

    def observe(attempt) -> None:
        if automation_run_id is None:
            return
        with session_scope() as database:
            record_automation_attempt(
                database,
                automation_run_id=automation_run_id,
                attempt=attempt,
            )
            database.commit()

    try:
        report = run_research_refresh(
            EdgarClient.from_env(),
            period_start=args.since,
            trigger_kind=args.trigger,
            retry_policy=policy,
            persist_bundle=persist if args.write else None,
            observe_attempt=observe if args.write else None,
        )
    except Exception:
        if automation_run_id is not None:
            with session_scope() as database:
                fail_automation_run(
                    database,
                    automation_run_id=automation_run_id,
                    completed_at=datetime.now(timezone.utc),
                )
                database.commit()
        raise
    if automation_run_id is not None:
        with session_scope() as database:
            finish_automation_run(
                database,
                automation_run_id=automation_run_id,
                report=report,
            )
            database.commit()

    for company in report.companies:
        final_attempt = company.attempts[-1]
        print(
            f"{company.ticker}: {company.status} | attempts={len(company.attempts)} | "
            f"facts={final_attempt.fact_count if final_attempt.fact_count is not None else '-'} | "
            f"reason={final_attempt.reason_code or '-'}"
        )
    print(
        f"Run {report.status}: {report.succeeded_count} succeeded, "
        f"{report.failed_count} failed; publication withheld."
    )
    if not args.write:
        print("Dry run only; no database writes performed.")
    return 0 if report.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
