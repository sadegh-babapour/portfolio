from __future__ import annotations

import argparse
import json
from datetime import date

from financial_research.analysis import CompanyAnalysis, analyze_company_quarter
from financial_research.edgar import EdgarClient
from financial_research.freshness import quarter_targets, supplement_lagging_company_facts
from financial_research.ingestion import build_extraction_bundle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calculate evidence-linked SEC measures without writing source or "
            "analysis data to the database."
        )
    )
    parser.add_argument("cik", help="SEC Central Index Key, with or without leading zeros")
    parser.add_argument("--since", type=date.fromisoformat, default=date(2022, 1, 1))
    parser.add_argument("--period-end", type=date.fromisoformat)
    parser.add_argument("--quarter", type=int, choices=(1, 2, 3, 4))
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the complete prompt-ready evidence bundle instead of a summary.",
    )
    return parser.parse_args()


def _display_value(value: int | float | None) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, int) or value.is_integer():
        return f"{int(value):,}"
    return f"{value:,.3f}"


def _print_summary(report: CompanyAnalysis) -> None:
    print(
        f"{report.company_name} | {report.period_end.isoformat()} | "
        f"Q{report.fiscal_quarter} | {report.revision_policy}"
    )
    print("Normalized facts:")
    for value in report.normalized_facts:
        print(
            f"  {value.key}: {_display_value(value.value)} {value.unit} "
            f"[{value.state}; {value.confidence}; evidence={len(value.evidence)}]"
        )
    print("Derived measures:")
    for value in report.derived_measures:
        print(
            f"  {value.key}: {_display_value(value.value)} {value.unit} "
            f"[{value.state}; {value.confidence}; evidence={len(value.evidence)}]"
        )


def main() -> int:
    args = parse_args()
    if (args.period_end is None) != (args.quarter is None):
        raise SystemExit("--period-end and --quarter must be supplied together")

    client = EdgarClient.from_env()
    bundle = build_extraction_bundle(
        client.submissions(args.cik),
        client.company_facts(args.cik),
        period_start=args.since,
    )
    facts = supplement_lagging_company_facts(client, bundle)
    targets = (
        ((args.period_end, args.quarter),)
        if args.period_end is not None and args.quarter is not None
        else quarter_targets(bundle.profile, facts)
    )
    reports = tuple(
        analyze_company_quarter(
            facts,
            company_name=bundle.profile.name,
            period_end=period_end,
            fiscal_quarter=quarter,
        )
        for period_end, quarter in targets
    )
    if args.json:
        print(json.dumps([report.prompt_context() for report in reports], indent=2))
        return 0

    print(
        f"Analyzed {len(reports)} fiscal quarters from {len(facts):,} "
        "SEC observations; no database writes performed."
    )
    for report in reports:
        _print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
