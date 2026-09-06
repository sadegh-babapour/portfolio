from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date

from financial_research.documents import research_filing
from financial_research.edgar import EdgarClient, extract_filing_metadata
from financial_research.peer_reviews import (
    PEER_OUTLIER_SPECS,
    review_peer_outlier_filing,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify filing-specific payment-peer outlier gates without database "
            "writes or public publication."
        )
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def review_peer_outliers(client: EdgarClient) -> dict:
    reviews = []
    failures = []
    for spec in PEER_OUTLIER_SPECS:
        try:
            filings = extract_filing_metadata(
                client.submissions(spec.cik),
                forms=None,
                period_start=date.fromisoformat(spec.report_period_end),
            )
            filing = next(
                item
                for item in filings
                if item.accession_number == spec.accession_number
            )
            bundle = research_filing(
                client,
                filing,
                include_exhibit_prefixes=("NONE",),
                max_documents=1,
            )
            reviews.append(
                asdict(
                    review_peer_outlier_filing(
                        filing,
                        bundle.snapshots,
                        spec=spec,
                    )
                )
            )
        except Exception as exc:  # isolated read-only research boundary
            failures.append(
                {
                    "cik": spec.cik,
                    "ticker": spec.ticker,
                    "reason_code": type(exc).__name__,
                    "retryable": True,
                }
            )
    complete = not failures and all(
        review["review_status"] == "complete" for review in reviews
    )
    return {
        "complete": complete,
        "write_performed": False,
        "publication_performed": False,
        "reviews": reviews,
        "failures": failures,
    }


def main() -> int:
    args = parse_args()
    result = review_peer_outliers(EdgarClient.from_env())
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for review in result["reviews"]:
            gate_text = ", ".join(
                f"{gate['metric']}={gate['status']}" for gate in review["gates"]
            )
            print(
                f"{review['ticker']}: {review['review_status']} | "
                f"findings={len(review['findings'])} | {gate_text}"
            )
        for failure in result["failures"]:
            print(f"{failure['ticker']}: failed | {failure['reason_code']}")
        print("No database writes or public publication performed.")
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
