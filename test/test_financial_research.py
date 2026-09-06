from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from unittest.mock import Mock

from financial_research.edgar import (
    EdgarClient,
    EdgarResponseError,
    extract_acceptance_times,
    extract_company_profile,
    extract_filing_metadata,
    extract_facts,
    normalize_cik,
)


SUBMISSIONS = {
    "cik": "1633917",
    "name": "PayPal Holdings, Inc.",
    "sic": "7389",
    "sicDescription": "Services-Business Services, NEC",
    "tickers": ["PYPL"],
    "exchanges": ["Nasdaq"],
    "formerNames": [{"name": "PayPal Parent Holdings, Inc."}],
    "filings": {
        "recent": {
            "accessionNumber": [
                "0001633917-25-000161",
                "0001633917-25-000162",
                "0001633917-21-000099",
                "0001633917-25-000158",
                "0001633917-22-000027",
            ],
            "form": ["10-Q", "10-Q/A", "10-K", "8-K", "8-K"],
            "filingDate": [
                "2025-07-29",
                "2025-08-01",
                "2022-01-10",
                "2025-07-29",
                "2022-01-28",
            ],
            "reportDate": [
                "2025-06-30",
                "2025-06-30",
                "2021-12-31",
                "2025-06-30",
                "2022-01-28",
            ],
            "acceptanceDateTime": [
                "2025-07-29T17:06:28.000Z",
                "2025-08-01T10:00:00.000Z",
                "2022-01-10T09:00:00.000Z",
                "2025-07-29T16:00:00.000Z",
                "2022-01-28T16:30:00.000Z",
            ],
            "primaryDocument": [
                "pypl-20250630.htm",
                "amendment.htm",
                "old.htm",
                "eightk.htm",
                "eightk-20220128.htm",
            ],
            "primaryDocDescription": ["10-Q", "10-Q amendment", "10-K", "8-K", "8-K"],
            "isInlineXBRL": [1, 1, 1, 1, 1],
        }
    },
}


COMPANY_FACTS = {
    "cik": 1633917,
    "facts": {
        "us-gaap": {
            "RevenueFromContractWithCustomerExcludingAssessedTax": {
                "label": "Revenue",
                "description": "Revenue recognized from contracts with customers.",
                "units": {
                    "USD": [
                        {
                            "start": "2025-04-01",
                            "end": "2025-06-30",
                            "val": 8_288_000_000,
                            "accn": "0001633917-25-000161",
                            "fy": 2025,
                            "fp": "Q2",
                            "form": "10-Q",
                            "filed": "2025-07-29",
                            "frame": "CY2025Q2",
                        },
                        {
                            "start": "2025-04-01",
                            "end": "2025-06-30",
                            "val": 8_300_000_000,
                            "accn": "0001633917-25-000162",
                            "fy": 2025,
                            "fp": "Q2",
                            "form": "10-Q/A",
                            "filed": "2025-08-01",
                            "frame": "CY2025Q2",
                        },
                        {
                            "start": "2021-01-01",
                            "end": "2021-12-31",
                            "val": 1,
                            "accn": "0001633917-21-000099",
                            "fy": 2021,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2022-01-10",
                        },
                        {
                            "start": "2025-04-01",
                            "end": "2025-06-30",
                            "val": 8_288_000_000,
                            "accn": "0001633917-25-000158",
                            "fy": 2025,
                            "fp": "Q2",
                            "form": "8-K",
                            "filed": "2025-07-29",
                        },
                    ]
                },
            },
            "CashAndCashEquivalentsAtCarryingValue": {
                "label": "Cash and cash equivalents",
                "description": "Cash balance.",
                "units": {
                    "USD": [
                        {
                            "end": "2025-06-30",
                            "val": 6_688_000_000,
                            "accn": "0001633917-25-000161",
                            "fy": 2025,
                            "fp": "Q2",
                            "form": "10-Q",
                            "filed": "2025-07-29",
                            "frame": "CY2025Q2I",
                        }
                    ]
                },
            },
        }
        ,
        "dei": {
            "EntityCommonStockSharesOutstanding": {
                "label": "Entity common stock shares outstanding",
                "description": "Shares outstanding at the measurement date.",
                "units": {
                    "shares": [
                        {
                            "end": "2022-01-28",
                            "val": 1_168_000_000,
                            "accn": "0001633917-22-000027",
                            "fy": 2021,
                            "fp": "FY",
                            "form": "10-K",
                            "filed": "2022-01-28",
                        }
                    ]
                },
            }
        },
    },
}


class EdgarContractTests(unittest.TestCase):
    def test_cik_is_validated_and_zero_padded(self):
        self.assertEqual(normalize_cik(1633917), "0001633917")
        with self.assertRaises(ValueError):
            normalize_cik("PYPL")

    def test_profile_preserves_amendments_and_acceptance_time(self):
        profile = extract_company_profile(SUBMISSIONS)

        self.assertEqual(profile.name, "PayPal Holdings, Inc.")
        self.assertEqual(profile.securities[0].ticker, "PYPL")
        self.assertEqual(profile.former_names, ("PayPal Parent Holdings, Inc.",))
        self.assertEqual(len(profile.filings), 2)
        self.assertEqual(profile.filings[0].accepted_at.tzinfo, timezone.utc)
        self.assertFalse(profile.filings[0].is_amendment)
        self.assertTrue(profile.filings[1].is_amendment)
        self.assertIn("000163391725000161", profile.filings[0].sec_index_url)

    def test_facts_preserve_original_semantics_and_join_availability(self):
        accepted_at = datetime(2025, 7, 29, 17, 6, 28, tzinfo=timezone.utc)
        facts = extract_facts(
            COMPANY_FACTS,
            accepted_at_by_accession={"0001633917-25-000161": accepted_at},
        )

        self.assertEqual(len(facts), 4)
        revenue = next(fact for fact in facts if fact.label == "Revenue")
        cash = next(fact for fact in facts if fact.label.startswith("Cash"))
        self.assertEqual(revenue.context_kind, "duration")
        self.assertEqual(revenue.period_start, date(2025, 4, 1))
        self.assertEqual(revenue.unit, "USD")
        self.assertEqual(revenue.accepted_at, accepted_at)
        self.assertEqual(cash.context_kind, "instant")
        self.assertIsNone(cash.period_start)

    def test_parallel_submission_columns_are_validated(self):
        broken = {**SUBMISSIONS, "filings": {"recent": {**SUBMISSIONS["filings"]["recent"]}}}
        broken["filings"]["recent"]["form"] = ["10-Q"]
        with self.assertRaisesRegex(EdgarResponseError, "must contain 5 entries"):
            extract_company_profile(broken)

    def test_acceptance_lookup_is_not_limited_by_research_form_filter(self):
        acceptance_times = extract_acceptance_times(SUBMISSIONS)

        self.assertEqual(
            acceptance_times["0001633917-22-000027"],
            datetime(2022, 1, 28, 16, 30, tzinfo=timezone.utc),
        )
        profile = extract_company_profile(SUBMISSIONS)
        self.assertNotIn(
            "0001633917-22-000027",
            {filing.accession_number for filing in profile.filings},
        )

        source_filings = extract_filing_metadata(SUBMISSIONS, forms=None)
        self.assertIn(
            "0001633917-22-000027",
            {filing.accession_number for filing in source_filings},
        )

    def test_client_declares_identity_paces_and_validates_json(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"cik": 1633917}
        request_get = Mock(return_value=response)
        clock_values = iter([10.0, 10.0, 10.05, 10.25])
        sleep = Mock()
        client = EdgarClient(
            "Bizqlab research owner@example.test",
            request_get=request_get,
            monotonic=lambda: next(clock_values),
            sleep=sleep,
        )

        client.submissions(1633917)
        client.company_facts("0001633917")

        self.assertEqual(request_get.call_count, 2)
        self.assertEqual(
            request_get.call_args_list[0].kwargs["headers"]["User-Agent"],
            "Bizqlab research owner@example.test",
        )
        self.assertFalse(request_get.call_args_list[0].kwargs["stream"])
        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args.args[0], 0.15)

    def test_client_rejects_non_object_json(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = []
        client = EdgarClient("Bizqlab owner@example.test", request_get=Mock(return_value=response))
        with self.assertRaisesRegex(EdgarResponseError, "SEC response must be a JSON object"):
            client.submissions(1633917)


if __name__ == "__main__":
    unittest.main()
