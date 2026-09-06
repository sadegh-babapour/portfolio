from __future__ import annotations

import unittest

from financial_research.universe import (
    BROKERAGE,
    CORE_INDUSTRY_CONTRACTS,
    CORE_RESEARCH_UNIVERSE,
    GAMING_OPTIONAL,
    OPTIONAL_RESEARCH_UNIVERSE,
    UNIVERSE_VERSION,
    validate_universe,
)


class ResearchUniverseContractTests(unittest.TestCase):
    def test_core_universe_has_six_groups_and_thirty_unique_filers(self):
        validate_universe()

        self.assertEqual(UNIVERSE_VERSION, "sec-universe-2026-09-06.1")
        self.assertEqual(len(CORE_INDUSTRY_CONTRACTS), 6)
        self.assertEqual(len(CORE_RESEARCH_UNIVERSE), 30)
        self.assertEqual(len({company.cik for company in CORE_RESEARCH_UNIVERSE}), 30)
        self.assertEqual(len({company.ticker for company in CORE_RESEARCH_UNIVERSE}), 30)
        self.assertTrue(
            all(company.publication_status in {"published", "public_eligible"} for company in CORE_RESEARCH_UNIVERSE)
        )

    def test_brokerage_group_centers_robinhood_and_retains_subgroups(self):
        self.assertEqual(
            [company.ticker for company in BROKERAGE.companies],
            ["HOOD", "COIN", "IBKR", "SCHW", "LPLA"],
        )
        self.assertEqual(len({company.comparison_subgroup for company in BROKERAGE.companies}), 5)
        self.assertIn("net_interest_revenue", {metric.key for metric in BROKERAGE.metrics})
        self.assertIn("regulatory_capital_and_liquidity", {metric.key for metric in BROKERAGE.metrics})

    def test_each_core_group_has_explicit_sector_metrics_and_comparison_notes(self):
        for industry in CORE_INDUSTRY_CONTRACTS:
            with self.subTest(industry=industry.key):
                self.assertEqual(industry.launch_status, "core")
                self.assertGreaterEqual(len(industry.metrics), 6)
                self.assertTrue(industry.comparison_notes)
                self.assertTrue(
                    all(company.industry_key == industry.key for company in industry.companies)
                )

    def test_gaming_is_defined_but_excluded_from_core_refresh(self):
        self.assertEqual(GAMING_OPTIONAL.launch_status, "optional_after_launch")
        self.assertEqual(len(OPTIONAL_RESEARCH_UNIVERSE), 5)
        self.assertTrue(
            all(company.publication_status == "planned_optional" for company in OPTIONAL_RESEARCH_UNIVERSE)
        )
        self.assertTrue(
            {company.cik for company in CORE_RESEARCH_UNIVERSE}.isdisjoint(
                company.cik for company in OPTIONAL_RESEARCH_UNIVERSE
            )
        )


if __name__ == "__main__":
    unittest.main()
