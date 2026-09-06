from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import requests
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.admin.service import _financial_research_health
from financial_research.automation import (
    RetryPolicy,
    begin_automation_run,
    finish_automation_run,
    record_automation_attempt,
    recover_stale_automation_runs,
    run_research_refresh,
)
from financial_research.ingestion import build_extraction_bundle
from financial_research.models import (
    ResearchAutomationAttempt,
    ResearchAutomationRun,
    ResearchFiler,
    ResearchIngestionRun,
)
from financial_research.peers import PAYMENTS_COHORT
from test_financial_research import COMPANY_FACTS, SUBMISSIONS


NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
AUTOMATION_TABLES = (
    ResearchFiler.__table__,
    ResearchIngestionRun.__table__,
    ResearchAutomationRun.__table__,
    ResearchAutomationAttempt.__table__,
)


class RefreshOrchestrationTests(unittest.TestCase):
    def test_transient_failure_retries_then_completes_without_publication(self):
        bundle = build_extraction_bundle(SUBMISSIONS, COMPANY_FACTS)
        client = MagicMock()
        client.submissions.side_effect = [
            requests.ConnectionError("temporary"),
            SUBMISSIONS,
        ]
        client.company_facts.return_value = COMPANY_FACTS
        delays = []

        with patch(
            "financial_research.automation.supplement_lagging_company_facts",
            return_value=bundle.facts,
        ):
            report = run_research_refresh(
                client,
                targets=PAYMENTS_COHORT[:1],
                retry_policy=RetryPolicy(max_attempts=3, initial_delay_seconds=0.25),
                sleep=delays.append,
                clock=lambda: NOW,
            )

        self.assertEqual(report.status, "completed")
        self.assertEqual(len(report.companies[0].attempts), 2)
        self.assertTrue(report.companies[0].attempts[0].retryable)
        self.assertEqual(delays, [0.25])
        self.assertEqual(report.publication_status, "withheld")
        self.assertFalse(report.publication_performed)

    def test_permanent_validation_failure_is_not_retried(self):
        client = MagicMock()
        client.submissions.return_value = {"invalid": True}
        client.company_facts.return_value = COMPANY_FACTS

        report = run_research_refresh(
            client,
            targets=PAYMENTS_COHORT[:1],
            retry_policy=RetryPolicy(max_attempts=3),
            sleep=MagicMock(),
            clock=lambda: NOW,
        )

        self.assertEqual(report.status, "failed")
        self.assertEqual(len(report.companies[0].attempts), 1)
        self.assertFalse(report.companies[0].attempts[0].retryable)
        self.assertEqual(report.companies[0].attempts[0].reason_code, "ValueError")


class AutomationPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        self.connection = self.engine.connect()
        self.connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS portfolio")
        ResearchFiler.metadata.create_all(self.connection, tables=AUTOMATION_TABLES)
        self.database = Session(bind=self.connection, expire_on_commit=False)

    def tearDown(self):
        self.database.close()
        self.connection.close()
        self.engine.dispose()

    def test_attempts_are_durable_and_visible_to_admin_summary(self):
        run_id = begin_automation_run(
            self.database,
            trigger_kind="scheduled",
            cohort_key="test-cohort",
            period_start=date(2022, 1, 1),
            target_count=1,
            started_at=NOW,
        )
        bundle = build_extraction_bundle(SUBMISSIONS, COMPANY_FACTS)
        client = MagicMock()
        client.submissions.return_value = SUBMISSIONS
        client.company_facts.return_value = COMPANY_FACTS
        attempts = []
        with patch(
            "financial_research.automation.supplement_lagging_company_facts",
            return_value=bundle.facts,
        ):
            report = run_research_refresh(
                client,
                targets=PAYMENTS_COHORT[:1],
                observe_attempt=attempts.append,
                clock=lambda: NOW,
            )
        record_automation_attempt(
            self.database,
            automation_run_id=run_id,
            attempt=attempts[0],
        )
        finish_automation_run(
            self.database,
            automation_run_id=run_id,
            report=report,
        )
        self.database.commit()

        stored = self.database.scalar(select(ResearchAutomationRun))
        attempt = self.database.scalar(select(ResearchAutomationAttempt))
        health = _financial_research_health(self.database)
        self.assertEqual(stored.status, "completed")
        self.assertEqual(attempt.status, "completed")
        self.assertEqual(health["status"], "completed")
        self.assertEqual(health["runs"][0]["publication"], "withheld")

    def test_second_running_batch_is_rejected(self):
        begin_automation_run(
            self.database,
            trigger_kind="admin",
            cohort_key="test-cohort",
            period_start=date(2022, 1, 1),
            target_count=1,
            started_at=NOW,
        )
        with self.assertRaisesRegex(RuntimeError, "already active"):
            begin_automation_run(
                self.database,
                trigger_kind="scheduled",
                cohort_key="test-cohort",
                period_start=date(2022, 1, 1),
                target_count=1,
                started_at=NOW,
            )

    def test_stale_running_batch_is_failed_before_next_schedule(self):
        run_id = begin_automation_run(
            self.database,
            trigger_kind="scheduled",
            cohort_key="test-cohort",
            period_start=date(2022, 1, 1),
            target_count=5,
            started_at=NOW - timedelta(hours=3),
        )

        recovered = recover_stale_automation_runs(self.database, now=NOW)

        row = self.database.get(ResearchAutomationRun, run_id)
        self.assertEqual(recovered, 1)
        self.assertEqual(row.status, "failed")
        self.assertEqual(row.failed_count, 5)
        self.assertEqual(row.publication_status, "withheld")


if __name__ == "__main__":
    unittest.main()
