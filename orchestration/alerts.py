"""Email the owner when a production run fails, or succeeds with a data check in error.

Nobody watches the Railway service (it has no UI), so these two sensors are how a
failure gets noticed. They send through Resend's HTTP API, as the contact form does,
but with the service's own send-only key: the Dagster service never holds the site's.

The emails carry the job, the failed steps or checks, and the first line of the error
with any connection URL removed. Successes send nothing; a freshness warning (4-6 days,
e.g. a long weekend) sends nothing; only checks that fail at ERROR severity do.
"""
import os
import re

import requests
from dagster import (
    AssetCheckSeverity,
    DagsterEventType,
    DagsterRunStatus,
    DefaultSensorStatus,
    RunFailureSensorContext,
    RunStatusSensorContext,
    run_failure_sensor,
    run_status_sensor,
)

RESEND_EMAILS_URL = "https://api.resend.com/emails"
SETTINGS = ("DAGSTER_ALERT_RESEND_KEY", "DAGSTER_ALERT_FROM", "DAGSTER_ALERT_TO")
URL_PATTERN = re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.IGNORECASE)
MAX_ERROR_CHARS = 300


def send(subject: str, body: str, env=os.environ, post=requests.post) -> None:
    """One plain-text email to the owner. Missing settings fail loudly (in the daemon log)."""
    missing = [key for key in SETTINGS if not env.get(key)]
    if missing:
        raise RuntimeError(f"alert email not configured: missing {', '.join(missing)}")
    response = post(
        RESEND_EMAILS_URL,
        headers={"Authorization": f"Bearer {env['DAGSTER_ALERT_RESEND_KEY']}",
                 "User-Agent": "bizqlab-dagster-alerts/1.0"},
        json={"from": env["DAGSTER_ALERT_FROM"], "to": [env["DAGSTER_ALERT_TO"]],
              "subject": subject, "text": body},
        timeout=15,
    )
    response.raise_for_status()


def first_line(message: str | None) -> str:
    """The error's first line, URLs removed (a URL could carry a password), and capped."""
    line = (message or "").strip().splitlines()[0] if (message or "").strip() else "no message"
    line = URL_PATTERN.sub("[url removed]", line)
    return line if len(line) <= MAX_ERROR_CHARS else line[:MAX_ERROR_CHARS] + "…"


def failure_email(job: str, run_id: str, steps: list[tuple[str, str | None]], reason: str | None) -> tuple[str, str]:
    lines = [f"Dagster run failed: {job}", f"Run: {run_id}", ""]
    if steps:
        lines += [f"- step {step}: {first_line(error)}" for step, error in steps]
    else:  # stopped before any step, e.g. the database check refused
        lines.append(f"- before any step: {first_line(reason)}")
    lines += ["", "The site keeps showing the last good data. Run history: the dagster schema on Railway."]
    return f"[bizqlab] Dagster run failed: {job}", "\n".join(lines)


def error_message(event) -> str | None:
    """The root error carried by a failure event (Dagster wraps it), or the event's own message."""
    error = getattr(event.event_specific_data, "error", None)
    if error is None:
        return event.message
    while error.cause is not None:
        error = error.cause
    return error.message


def failed_checks(instance, run_id: str) -> list[str]:
    """ERROR-severity checks that failed in a run, as 'asset: check' strings."""
    failed = []
    for record in instance.all_logs(run_id, of_type=DagsterEventType.ASSET_CHECK_EVALUATION):
        evaluation = record.dagster_event.event_specific_data
        if not evaluation.passed and evaluation.severity == AssetCheckSeverity.ERROR:
            failed.append(f"{evaluation.asset_key.to_user_string()}: {evaluation.check_name}")
    return sorted(failed)


def check_email(job: str, run_id: str, checks: list[str]) -> tuple[str, str]:
    lines = [f"Dagster run succeeded, but a data check failed: {job}", f"Run: {run_id}", ""]
    lines += [f"- {check}" for check in checks]
    lines += ["", "If it's the freshness check, the Bank of Canada data is 7 or more days old."]
    return f"[bizqlab] Data check failed: {job}", "\n".join(lines)


def sensors(default_status: DefaultSensorStatus) -> list:
    """The two alert sensors. Running by default only in production (see definitions.py)."""

    @run_failure_sensor(name="email_on_run_failure", default_status=default_status,
                        description="Email the owner when a run fails.")
    def email_on_run_failure(context: RunFailureSensorContext):
        steps = [(event.step_key, error_message(event)) for event in context.get_step_failure_events()]
        send(*failure_email(context.dagster_run.job_name, context.dagster_run.run_id, steps,
                            error_message(context.failure_event)))

    @run_status_sensor(run_status=DagsterRunStatus.SUCCESS, name="email_on_failed_check",
                       default_status=default_status,
                       description="Email the owner when a run succeeds with an ERROR-severity check failed.")
    def email_on_failed_check(context: RunStatusSensorContext):
        checks = failed_checks(context.instance, context.dagster_run.run_id)
        if checks:
            send(*check_email(context.dagster_run.job_name, context.dagster_run.run_id, checks))

    return [email_on_run_failure, email_on_failed_check]
