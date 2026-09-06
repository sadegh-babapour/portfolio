from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .contracts import FactObservation


def payload_sha256(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def fact_fingerprint(fact: FactObservation) -> str:
    identity = {
        "cik": fact.cik,
        "taxonomy": fact.taxonomy,
        "concept": fact.concept,
        "unit": fact.unit,
        "value": fact.value,
        "period_start": fact.period_start.isoformat() if fact.period_start else None,
        "period_end": fact.period_end.isoformat(),
        "filed_on": fact.filed_on.isoformat(),
        "fiscal_year": fact.fiscal_year,
        "fiscal_period": fact.fiscal_period,
        "form": fact.form,
        "accession_number": fact.accession_number,
        "frame": fact.frame,
    }
    return payload_sha256(identity)
