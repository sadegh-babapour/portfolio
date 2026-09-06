from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date

from financial_research.documents import research_filing
from financial_research.edgar import EdgarClient, extract_filing_metadata


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract bounded evidence from one SEC filing without database writes."
    )
    parser.add_argument("cik", help="SEC Central Index Key")
    parser.add_argument("accession", help="SEC accession number with hyphens")
    parser.add_argument(
        "--include-exhibit",
        action="append",
        default=None,
        help="Exhibit type prefix to include; repeat as needed (default: EX-10, EX-99.1).",
    )
    parser.add_argument("--max-documents", type=int, default=6)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = EdgarClient.from_env()
    submissions = client.submissions(args.cik)
    filings = extract_filing_metadata(
        submissions,
        forms=None,
        period_start=date(1994, 1, 1),
    )
    filing = next(
        (item for item in filings if item.accession_number == args.accession),
        None,
    )
    if filing is None:
        raise SystemExit("Accession was not present in the filer's recent Submissions data")
    bundle = research_filing(
        client,
        filing,
        include_exhibit_prefixes=tuple(args.include_exhibit or ("EX-10", "EX-99.1")),
        max_documents=args.max_documents,
    )
    if args.json:
        payload = {
            "filing": asdict(bundle.filing),
            "documents": [asdict(item) for item in bundle.documents],
            "snapshots": [
                {
                    "document_name": item.document.document_name,
                    "content_type": item.content_type,
                    "content_sha256": item.content_sha256,
                    "byte_count": item.byte_count,
                }
                for item in bundle.snapshots
            ],
            "evidence": [asdict(item) for item in bundle.evidence],
            "entity_roles": [asdict(item) for item in bundle.entity_roles],
            "claims": [asdict(item) for item in bundle.claims],
            "questions": [asdict(item) for item in bundle.questions],
        }
        print(json.dumps(payload, default=str, indent=2))
        return 0

    print(
        f"{filing.form} {filing.accession_number} ({filing.report_period_end}): "
        f"{len(bundle.documents)} inventoried, {len(bundle.snapshots)} fetched, "
        f"{len(bundle.evidence)} evidence passages, {len(bundle.entity_roles)} roles, "
        f"{len(bundle.claims)} claims, {len(bundle.questions)} open questions."
    )
    for snapshot in bundle.snapshots:
        print(
            f"  document: {snapshot.document.document_type} "
            f"{snapshot.document.document_name} {snapshot.byte_count:,} bytes "
            f"sha256={snapshot.content_sha256[:12]}…"
        )
    for role in bundle.entity_roles:
        print(f"  role: {role.entity_name} — {role.role} [{role.confidence}]")
    for claim in bundle.claims:
        print(f"  claim: {claim.statement} [{claim.confidence}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
