from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date

from financial_research.contracts import FilingDocument
from financial_research.documents import fetch_snapshot, filing_archive_url
from financial_research.edgar import EdgarClient, extract_filing_metadata
from financial_research.sector_reviews import (
    SECTOR_FILING_SPECS,
    review_sector_filing,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the 25 frozen non-payment sector filing reviews without "
            "database writes or publication."
        )
    )
    parser.add_argument("--sector")
    parser.add_argument("--ticker")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def review_sector_filings(
    client: EdgarClient,
    *,
    sector: str | None = None,
    ticker: str | None = None,
) -> dict:
    specs = tuple(
        spec
        for spec in SECTOR_FILING_SPECS
        if (sector is None or spec.industry_key == sector)
        and (ticker is None or spec.ticker == ticker.upper())
    )
    reviews = []
    failures = []
    for spec in specs:
        try:
            filings = extract_filing_metadata(
                client.submissions(spec.cik),
                forms=None,
                period_start=date.fromisoformat(spec.report_period_end),
            )
            filing = next(
                item for item in filings if item.accession_number == spec.accession_number
            )
            document = FilingDocument(
                cik=spec.cik,
                accession_number=spec.accession_number,
                sequence=1,
                description=filing.primary_document_description or "10-Q",
                document_name=spec.primary_document,
                document_type=filing.form,
                size_bytes=None,
                category="primary",
                sec_url=filing_archive_url(
                    spec.cik, spec.accession_number, spec.primary_document
                ),
            )
            snapshot = fetch_snapshot(client, document)
            reviews.append(
                asdict(review_sector_filing(filing, (snapshot,), spec=spec))
            )
        except Exception as exc:  # isolated, read-only research boundary
            failures.append(
                {
                    "industry_key": spec.industry_key,
                    "cik": spec.cik,
                    "ticker": spec.ticker,
                    "reason_code": type(exc).__name__,
                    "message": str(exc)[:240],
                    "retryable": True,
                }
            )
    complete = len(reviews) == len(specs) and not failures and all(
        review["review_status"] == "complete" for review in reviews
    )
    return {
        "complete": complete,
        "target_count": len(specs),
        "write_performed": False,
        "publication_performed": False,
        "reviews": reviews,
        "failures": failures,
    }


def main() -> int:
    args = parse_args()
    result = review_sector_filings(
        EdgarClient.from_env(), sector=args.sector, ticker=args.ticker
    )
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for review in result["reviews"]:
            gates = ", ".join(
                f"{gate['metric']}={gate['status']}" for gate in review["gates"]
            ) or "no magnitude gates"
            print(
                f"{review['industry_key']} · {review['ticker']}: "
                f"{review['review_status']} | findings={len(review['findings'])} | {gates}"
            )
            if review["missing_evidence_ids"]:
                print("  missing: " + ", ".join(review["missing_evidence_ids"]))
        for failure in result["failures"]:
            print(
                f"{failure['industry_key']} · {failure['ticker']}: failed | "
                f"{failure['reason_code']}"
            )
        print("No database writes or public publication performed.")
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
