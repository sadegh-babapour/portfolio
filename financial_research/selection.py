from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable, Literal

from .contracts import FactObservation


PeriodKind = Literal["instant", "quarter", "half_year", "nine_month", "annual", "other"]
RevisionPolicy = Literal["originally_reported", "latest_corrected"]
SelectionState = Literal["selected", "missing", "ambiguous", "unexpected_period"]


@dataclass(frozen=True, slots=True)
class RankedFact:
    fact: FactObservation
    mapping_priority: int


@dataclass(frozen=True, slots=True)
class FactSelection:
    state: SelectionState
    fact: FactObservation | None
    candidates: tuple[FactObservation, ...]
    reason: str


def classify_period(fact: FactObservation) -> PeriodKind:
    if fact.period_start is None:
        return "instant"
    days = (fact.period_end - fact.period_start).days + 1
    if 70 <= days <= 110:
        return "quarter"
    if 160 <= days <= 205:
        return "half_year"
    if 250 <= days <= 300:
        return "nine_month"
    if 330 <= days <= 380:
        return "annual"
    return "other"


def select_canonical_fact(
    candidates: Iterable[RankedFact],
    *,
    period_end: date,
    period_kind: PeriodKind,
    revision_policy: RevisionPolicy = "latest_corrected",
) -> FactSelection:
    period_candidates = tuple(
        candidate
        for candidate in candidates
        if candidate.fact.period_end == period_end
    )
    matching = tuple(
        candidate
        for candidate in period_candidates
        if classify_period(candidate.fact) == period_kind
    )
    if not matching:
        state: SelectionState = "unexpected_period" if period_candidates else "missing"
        return FactSelection(
            state=state,
            fact=None,
            candidates=tuple(item.fact for item in period_candidates),
            reason=(
                f"No {period_kind} observation ends on {period_end.isoformat()}."
                if period_candidates
                else f"No observation ends on {period_end.isoformat()}."
            ),
        )

    best_priority = min(item.mapping_priority for item in matching)
    preferred = tuple(item.fact for item in matching if item.mapping_priority == best_priority)
    source_concepts = {(fact.taxonomy, fact.concept) for fact in preferred}
    if len(source_concepts) != 1:
        return FactSelection(
            state="ambiguous",
            fact=None,
            candidates=preferred,
            reason="Multiple equally preferred source concepts match the canonical metric.",
        )

    ordered = sorted(
        preferred,
        key=lambda fact: (
            datetime_order(fact.accepted_at),
            fact.filed_on,
            fact.accession_number,
        ),
    )
    chosen = ordered[0] if revision_policy == "originally_reported" else ordered[-1]
    same_filing_values = {
        json_value(fact.value)
        for fact in ordered
        if fact.accession_number == chosen.accession_number
    }
    if len(same_filing_values) > 1:
        return FactSelection(
            state="ambiguous",
            fact=None,
            candidates=tuple(ordered),
            reason="The selected filing contains conflicting values for one semantic context.",
        )
    return FactSelection(
        state="selected",
        fact=chosen,
        candidates=tuple(ordered),
        reason=f"Selected by {revision_policy} policy at mapping priority {best_priority}.",
    )


def json_value(value: int | float | str) -> tuple[str, str]:
    """Keep numeric and string source values distinct during ambiguity checks."""
    return type(value).__name__, str(value)


def datetime_order(value: datetime | None) -> float:
    if value is None:
        return float("-inf")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()
