from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date
from typing import Iterable

from financial_research.analysis import analyze_company_quarter, ranked_facts_by_metric
from financial_research.edgar import EdgarClient
from financial_research.freshness import quarter_targets, supplement_lagging_company_facts
from financial_research.ingestion import build_extraction_bundle
from financial_research.peers import PAYMENTS_COHORT, assess_payment_cohort


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect the provisional payment cohort against SEC data without database "
            "writes or public publication."
        )
    )
    parser.add_argument("--since", type=date.fromisoformat, default=date(2022, 1, 1))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _inspect_candidate(client: EdgarClient, candidate, since: date) -> tuple[dict, object]:
    bundle = build_extraction_bundle(
        client.submissions(candidate.cik),
        client.company_facts(candidate.cik),
        period_start=since,
    )
    facts = supplement_lagging_company_facts(client, bundle)
    targets = quarter_targets(bundle.profile, facts)
    mapped_metrics = ranked_facts_by_metric(facts)
    securities = {security.ticker for security in bundle.profile.securities}
    identity_matches = (
        bundle.profile.cik == candidate.cik and candidate.ticker in securities
    )
    latest_target = targets[-1] if targets else None
    report = (
        analyze_company_quarter(
            facts,
            company_name=bundle.profile.name,
            period_end=latest_target[0],
            fiscal_quarter=latest_target[1],
        )
        if latest_target is not None
        else None
    )
    return (
        {
            "configured": asdict(candidate),
            "status": "complete",
            "sec_company_name": bundle.profile.name,
            "sec_tickers": sorted(securities),
            "identity_matches": identity_matches,
            "fact_count": len(facts),
            "canonical_metrics": sorted(mapped_metrics),
            "quarter_count": len(targets),
            "latest_target": (
                {"period_end": latest_target[0].isoformat(), "quarter": latest_target[1]}
                if latest_target is not None
                else None
            ),
        },
        report,
    )


def inspect_peer_cohort(
    client: EdgarClient,
    *,
    since: date,
    candidates: Iterable = PAYMENTS_COHORT,
) -> dict:
    """Inspect every candidate independently and withhold partial cohort output."""
    reports = []
    inspections = []
    for candidate in candidates:
        try:
            inspection, report = _inspect_candidate(client, candidate, since)
        except Exception as exc:  # run boundary: record each isolated candidate failure
            inspections.append(
                {
                    "configured": asdict(candidate),
                    "status": "failed",
                    "reason_code": type(exc).__name__,
                    "retryable": True,
                }
            )
            continue
        inspections.append(inspection)
        if report is not None:
            reports.append(report)

    failures = sum(item["status"] == "failed" for item in inspections)
    assessments = assess_payment_cohort(tuple(reports)) if failures == 0 else ()
    return {
        "write_performed": False,
        "publication_performed": False,
        "complete": failures == 0,
        "failure_count": failures,
        "inspections": inspections,
        "assessments": [asdict(item) for item in assessments],
    }


def summary_lines(result: dict) -> tuple[str, ...]:
    lines = []
    for item in result["inspections"]:
        if item["status"] == "failed":
            lines.append(
                f"{item['configured']['ticker']}: failed | "
                f"reason={item['reason_code']} | retryable=yes"
            )
            continue
        target = item["latest_target"]
        target_text = (
            f"Q{target['quarter']} {target['period_end']}" if target else "unavailable"
        )
        lines.append(
            f"{item['configured']['ticker']}: {item['sec_company_name']} | "
            f"identity={'ok' if item['identity_matches'] else 'review'} | "
            f"quarters={item['quarter_count']} | latest={target_text} | "
            f"metrics={len(item['canonical_metrics'])}"
        )
    for assessment in result["assessments"]:
        lines.append(
            f"  assessment: {assessment['company_name']} | "
            f"comparable={'yes' if assessment['comparable'] else 'no'} | "
            f"cohort={assessment['cohort']} | "
            f"signal={assessment['signal_pattern'] or 'blocked'} | "
            f"{' '.join(assessment['reasons'])}"
        )
    lines.append("No database writes or public publication performed.")
    return tuple(lines)


def main() -> int:
    args = parse_args()
    result = inspect_peer_cohort(
        EdgarClient.from_env(),
        since=args.since,
    )
    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if result["complete"] else 1
    for line in summary_lines(result):
        print(line)
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
