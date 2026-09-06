from __future__ import annotations

import argparse
from collections import Counter
from datetime import date

from financial_research.edgar import (
    EdgarClient,
    extract_acceptance_times,
    extract_company_profile,
    extract_facts,
)
from financial_research.metrics import CANONICAL_METRIC_VERSION, metric_for_fact


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect SEC submissions and Company Facts without storing the payloads."
    )
    parser.add_argument("cik", help="SEC Central Index Key, with or without leading zeros")
    parser.add_argument("--since", type=date.fromisoformat, default=date(2022, 1, 1))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = EdgarClient.from_env()
    submissions = client.submissions(args.cik)
    profile = extract_company_profile(submissions, period_start=args.since)
    acceptance_times = extract_acceptance_times(submissions)
    observations = extract_facts(
        client.company_facts(args.cik),
        accepted_at_by_accession=acceptance_times,
        period_start=args.since,
    )

    forms = Counter(fact.form for fact in observations)
    taxonomies = Counter(fact.taxonomy for fact in observations)
    units = Counter(fact.unit for fact in observations)
    concepts = {(fact.taxonomy, fact.concept) for fact in observations}
    canonical_metrics = Counter()
    for fact in observations:
        resolved = metric_for_fact(
            cik=fact.cik,
            taxonomy=fact.taxonomy,
            concept=fact.concept,
            unit=fact.unit,
            context_kind=fact.context_kind,
        )
        if resolved is not None:
            canonical_metrics[resolved[0].key] += 1
    missing_acceptance_facts = [fact for fact in observations if fact.accepted_at is None]

    print(f"Company: {profile.name}")
    print(f"CIK: {profile.cik}")
    print(
        "Securities: "
        + ", ".join(
            f"{item.ticker} ({item.exchange or 'exchange unavailable'})"
            for item in profile.securities
        )
    )
    print(f"Selected filings since {args.since.isoformat()}: {len(profile.filings):,}")
    print(f"Raw fact observations: {len(observations):,}")
    print(f"Distinct concepts: {len(concepts):,}")
    print("Forms: " + ", ".join(f"{key}={value}" for key, value in forms.most_common()))
    print(
        "Taxonomies: "
        + ", ".join(f"{key}={value}" for key, value in taxonomies.most_common())
    )
    print("Units: " + ", ".join(f"{key}={value}" for key, value in units.most_common()))
    print(f"Facts without an acceptance-time join: {len(missing_acceptance_facts):,}")
    for fact in missing_acceptance_facts[:10]:
        print(
            "  missing acceptance: "
            f"{fact.accession_number} {fact.form} {fact.period_end} "
            f"{fact.taxonomy}:{fact.concept}"
        )
    print(
        f"Canonical catalog {CANONICAL_METRIC_VERSION}: "
        f"{sum(canonical_metrics.values()):,} observations across "
        f"{len(canonical_metrics):,} metrics"
    )
    for metric, count in canonical_metrics.most_common():
        print(f"  canonical: {metric}={count:,}")
    print("\nMost frequent concepts (inspection only; not canonical mappings):")
    concept_counts = Counter((fact.taxonomy, fact.concept) for fact in observations)
    for (taxonomy, concept), count in concept_counts.most_common(25):
        print(f"  {taxonomy}:{concept} — {count:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
