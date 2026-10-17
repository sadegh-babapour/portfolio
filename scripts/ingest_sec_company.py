from __future__ import annotations

import argparse
from datetime import date

from app.contact.database import session_scope
from financial_research.edgar import EdgarClient
from financial_research.ingestion import build_extraction_bundle, persist_extraction_bundle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract SEC company data; persist only when --write is explicit."
    )
    parser.add_argument("cik", help="SEC Central Index Key, with or without leading zeros")
    parser.add_argument("--since", type=date.fromisoformat, default=date(2022, 1, 1))
    parser.add_argument(
        "--write",
        action="store_true",
        help="Commit the extraction to the configured portfolio database.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = EdgarClient.from_env()
    bundle = build_extraction_bundle(
        client.submissions(args.cik),
        client.company_facts(args.cik),
        period_start=args.since,
    )
    print(
        f"Extracted {bundle.profile.name}: {len(bundle.source_filings):,} filing records, "
        f"{len(bundle.facts):,} facts, {len(bundle.issues):,} issues."
    )
    if not args.write:
        print("Dry run only; pass --write to persist to the configured database.")
        return 0

    with session_scope() as database:
        try:
            summary = persist_extraction_bundle(database, bundle)
            database.commit()
        except Exception:
            database.rollback()
            raise
    print(
        f"Committed run {summary.run_id}: {summary.filings_inserted:,} new filings, "
        f"{summary.facts_inserted:,} new facts, {summary.facts_seen_again:,} seen again, "
        f"{summary.facts_mapped:,} new canonical mappings, "
        f"{summary.rejects_recorded:,} rejects."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
