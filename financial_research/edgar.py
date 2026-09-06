from __future__ import annotations

import os
import time
from collections import OrderedDict
from collections.abc import Callable, Collection, Mapping
from datetime import date, datetime
from itertools import zip_longest
from typing import Any
from urllib.parse import urlparse

import requests

from .contracts import CompanyProfile, FactObservation, FilingMetadata, SecurityIdentifier


SEC_DATA_BASE_URL = "https://data.sec.gov"
SEC_ARCHIVES_BASE_URL = "https://www.sec.gov/Archives/edgar/data"
DEFAULT_FORMS = frozenset({"10-Q", "10-K"})
DEFAULT_PERIOD_START = date(2022, 1, 1)


class EdgarResponseError(ValueError):
    """Raised when an SEC response does not satisfy the extraction contract."""


def normalize_cik(cik: str | int) -> str:
    text = str(cik).strip()
    if not text.isdigit() or len(text) > 10:
        raise ValueError("CIK must contain between one and ten digits")
    return text.zfill(10)


def base_form(form: str) -> str:
    return form.removesuffix("/A")


def filing_index_url(cik: str, accession_number: str) -> str:
    normalized_cik = normalize_cik(cik)
    accession_path = accession_number.replace("-", "")
    if not accession_path.isdigit():
        raise EdgarResponseError(f"Invalid accession number: {accession_number!r}")
    return (
        f"{SEC_ARCHIVES_BASE_URL}/{int(normalized_cik)}/{accession_path}/"
        f"{accession_number}-index.htm"
    )


def _parse_date(value: Any, *, field: str, required: bool = True) -> date | None:
    if value in (None, ""):
        if required:
            raise EdgarResponseError(f"Missing required {field}")
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise EdgarResponseError(f"Invalid {field}: {value!r}") from exc


def _parse_datetime(value: Any, *, field: str) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise EdgarResponseError(f"Invalid {field}: {value!r}") from exc


def _optional_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _required_mapping(value: Any, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EdgarResponseError(f"{field} must be a JSON object")
    return value


def _column(columns: Mapping[str, Any], name: str, length: int) -> list[Any]:
    values = columns.get(name)
    if values is None:
        return [None] * length
    if not isinstance(values, list) or len(values) != length:
        raise EdgarResponseError(f"filings.recent.{name} must contain {length} entries")
    return values


def extract_acceptance_times(payload: Mapping[str, Any]) -> dict[str, datetime | None]:
    """Return accession-level acceptance times without applying a form filter.

    Company Facts and Submissions can classify the same accession differently.
    Acceptance time is accession metadata, so joining it must remain independent
    from the set of forms selected for financial research.
    """
    filings = _required_mapping(payload.get("filings"), field="filings")
    recent = _required_mapping(filings.get("recent"), field="filings.recent")
    accessions = recent.get("accessionNumber")
    if not isinstance(accessions, list):
        raise EdgarResponseError("filings.recent.accessionNumber must be an array")
    accepted_values = _column(recent, "acceptanceDateTime", len(accessions))

    acceptance_times: dict[str, datetime | None] = {}
    for accession, accepted_value in zip(accessions, accepted_values, strict=True):
        accession_number = str(accession or "")
        if not accession_number:
            raise EdgarResponseError("filings.recent contains an empty accession number")
        accepted_at = _parse_datetime(accepted_value, field="acceptanceDateTime")
        previous = acceptance_times.get(accession_number)
        if previous is not None and accepted_at is not None and previous != accepted_at:
            raise EdgarResponseError(
                f"Conflicting acceptance times for accession {accession_number}"
            )
        if accession_number not in acceptance_times or accepted_at is not None:
            acceptance_times[accession_number] = accepted_at
    return acceptance_times


def extract_company_profile(
    payload: Mapping[str, Any],
    *,
    forms: Collection[str] = DEFAULT_FORMS,
    period_start: date = DEFAULT_PERIOD_START,
) -> CompanyProfile:
    cik = normalize_cik(payload.get("cik", ""))
    name = str(payload.get("name", "")).strip()
    if not name:
        raise EdgarResponseError("SEC submissions response is missing the company name")

    tickers = payload.get("tickers") or []
    exchanges = payload.get("exchanges") or []
    if not isinstance(tickers, list) or not isinstance(exchanges, list):
        raise EdgarResponseError("tickers and exchanges must be arrays")
    securities = tuple(
        SecurityIdentifier(str(ticker), _optional_text(exchange))
        for ticker, exchange in zip_longest(tickers, exchanges)
        if ticker not in (None, "")
    )

    former_names_payload = payload.get("formerNames") or []
    if not isinstance(former_names_payload, list):
        raise EdgarResponseError("formerNames must be an array")
    former_names = tuple(
        str(item.get("name")).strip()
        for item in former_names_payload
        if isinstance(item, Mapping) and item.get("name")
    )

    filing_records = extract_filing_metadata(
        payload,
        forms=forms,
        period_start=period_start,
    )

    return CompanyProfile(
        cik=cik,
        name=name,
        sic=_optional_text(payload.get("sic")),
        sic_description=_optional_text(payload.get("sicDescription")),
        securities=securities,
        former_names=former_names,
        filings=filing_records,
    )


def extract_filing_metadata(
    payload: Mapping[str, Any],
    *,
    forms: Collection[str] | None = DEFAULT_FORMS,
    period_start: date = DEFAULT_PERIOD_START,
) -> tuple[FilingMetadata, ...]:
    """Extract recent submission records, optionally without a form filter."""
    cik = normalize_cik(payload.get("cik", ""))
    filings = _required_mapping(payload.get("filings"), field="filings")
    recent = _required_mapping(filings.get("recent"), field="filings.recent")
    accessions = recent.get("accessionNumber")
    if not isinstance(accessions, list):
        raise EdgarResponseError("filings.recent.accessionNumber must be an array")

    length = len(accessions)
    form_values = _column(recent, "form", length)
    filed_values = _column(recent, "filingDate", length)
    report_values = _column(recent, "reportDate", length)
    accepted_values = _column(recent, "acceptanceDateTime", length)
    document_values = _column(recent, "primaryDocument", length)
    description_values = _column(recent, "primaryDocDescription", length)
    inline_values = _column(recent, "isInlineXBRL", length)

    allowed_forms = {base_form(form) for form in forms} if forms is not None else None
    filing_records: list[FilingMetadata] = []
    for index, accession in enumerate(accessions):
        form = str(form_values[index] or "")
        if allowed_forms is not None and base_form(form) not in allowed_forms:
            continue
        filed_on = _parse_date(filed_values[index], field="filingDate")
        report_end = _parse_date(
            report_values[index], field="reportDate", required=False
        )
        assert filed_on is not None
        if (report_end or filed_on) < period_start:
            continue
        accession_number = str(accession or "")
        inline_value = inline_values[index]
        filing_records.append(
            FilingMetadata(
                cik=cik,
                accession_number=accession_number,
                form=form,
                filed_on=filed_on,
                report_period_end=report_end,
                accepted_at=_parse_datetime(
                    accepted_values[index], field="acceptanceDateTime"
                ),
                primary_document=_optional_text(document_values[index]),
                primary_document_description=_optional_text(description_values[index]),
                is_amendment=form.endswith("/A"),
                is_inline_xbrl=(bool(inline_value) if inline_value is not None else None),
                sec_index_url=filing_index_url(cik, accession_number),
            )
        )

    return tuple(filing_records)


def extract_facts(
    payload: Mapping[str, Any],
    *,
    accepted_at_by_accession: Mapping[str, datetime | None] | None = None,
    forms: Collection[str] = DEFAULT_FORMS,
    period_start: date = DEFAULT_PERIOD_START,
) -> tuple[FactObservation, ...]:
    cik = normalize_cik(payload.get("cik", ""))
    taxonomies = _required_mapping(payload.get("facts"), field="facts")
    allowed_forms = {base_form(form) for form in forms}
    acceptance_times = accepted_at_by_accession or {}
    observations: list[FactObservation] = []

    for taxonomy, concepts_value in taxonomies.items():
        concepts = _required_mapping(concepts_value, field=f"facts.{taxonomy}")
        for concept, concept_value in concepts.items():
            concept_data = _required_mapping(
                concept_value, field=f"facts.{taxonomy}.{concept}"
            )
            label = str(concept_data.get("label") or concept)
            description = str(concept_data.get("description") or "")
            units = _required_mapping(
                concept_data.get("units"), field=f"facts.{taxonomy}.{concept}.units"
            )
            for unit, fact_values in units.items():
                if not isinstance(fact_values, list):
                    raise EdgarResponseError(
                        f"facts.{taxonomy}.{concept}.units.{unit} must be an array"
                    )
                for fact in fact_values:
                    fact_data = _required_mapping(fact, field=f"fact {taxonomy}.{concept}")
                    form = str(fact_data.get("form") or "")
                    if base_form(form) not in allowed_forms:
                        continue
                    end = _parse_date(fact_data.get("end"), field="fact end")
                    assert end is not None
                    if end < period_start:
                        continue
                    accession_number = str(fact_data.get("accn") or "")
                    if not accession_number:
                        raise EdgarResponseError(
                            f"Fact {taxonomy}.{concept} is missing its accession number"
                        )
                    if "val" not in fact_data:
                        raise EdgarResponseError(f"Fact {taxonomy}.{concept} is missing its value")
                    filed_on = _parse_date(fact_data.get("filed"), field="fact filed")
                    assert filed_on is not None
                    start = _parse_date(
                        fact_data.get("start"), field="fact start", required=False
                    )
                    fiscal_year = fact_data.get("fy")
                    observations.append(
                        FactObservation(
                            cik=cik,
                            taxonomy=str(taxonomy),
                            concept=str(concept),
                            label=label,
                            description=description,
                            unit=str(unit),
                            value=fact_data["val"],
                            period_start=start,
                            period_end=end,
                            filed_on=filed_on,
                            accepted_at=acceptance_times.get(accession_number),
                            fiscal_year=(int(fiscal_year) if fiscal_year is not None else None),
                            fiscal_period=_optional_text(fact_data.get("fp")),
                            form=form,
                            accession_number=accession_number,
                            frame=_optional_text(fact_data.get("frame")),
                            context_kind="duration" if start else "instant",
                            is_amendment=form.endswith("/A"),
                            sec_index_url=filing_index_url(cik, accession_number),
                        )
                    )
    return tuple(observations)


class EdgarClient:
    """Small SEC JSON client with explicit identity and conservative pacing."""

    def __init__(
        self,
        user_agent: str,
        *,
        timeout_seconds: float = 30.0,
        minimum_interval_seconds: float = 0.2,
        request_get: Callable[..., Any] = requests.get,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        document_max_bytes: int = 8_000_000,
        document_cache_entries: int = 16,
    ) -> None:
        identity = user_agent.strip()
        if not identity:
            raise ValueError("A descriptive SEC User-Agent is required")
        if timeout_seconds <= 0 or minimum_interval_seconds < 0:
            raise ValueError("SEC timeout must be positive and request interval non-negative")
        if document_max_bytes <= 0 or document_cache_entries < 0:
            raise ValueError("SEC document limits must be non-negative and bounded")
        self.user_agent = identity
        self.timeout_seconds = timeout_seconds
        self.minimum_interval_seconds = minimum_interval_seconds
        self._request_get = request_get
        self._monotonic = monotonic
        self._sleep = sleep
        self._last_request_at: float | None = None
        self.document_max_bytes = document_max_bytes
        self.document_cache_entries = document_cache_entries
        self._document_cache: OrderedDict[str, tuple[bytes, str]] = OrderedDict()

    @classmethod
    def from_env(cls) -> EdgarClient:
        return cls(os.getenv("SEC_USER_AGENT", ""))

    def submissions(self, cik: str | int) -> Mapping[str, Any]:
        return self._get_json(f"{SEC_DATA_BASE_URL}/submissions/CIK{normalize_cik(cik)}.json")

    def company_facts(self, cik: str | int) -> Mapping[str, Any]:
        return self._get_json(
            f"{SEC_DATA_BASE_URL}/api/xbrl/companyfacts/CIK{normalize_cik(cik)}.json"
        )

    def filing_document(self, url: str) -> tuple[bytes, str]:
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "www.sec.gov"
            or not parsed.path.startswith("/Archives/edgar/data/")
        ):
            raise ValueError("Only HTTPS SEC filing-archive documents are allowed")
        cached = self._document_cache.get(url)
        if cached is not None:
            self._document_cache.move_to_end(url)
            return cached

        response = self._request(
            url,
            accept="text/html, application/xml, text/xml, text/plain",
            stream=True,
        )
        content_length = response.headers.get("Content-Length")
        try:
            declared_bytes = int(content_length) if content_length else None
        except ValueError as exc:
            response.close()
            raise EdgarResponseError(f"SEC document has invalid Content-Length: {url}") from exc
        if declared_bytes is not None and declared_bytes > self.document_max_bytes:
            response.close()
            raise EdgarResponseError(f"SEC document exceeds byte limit: {url}")
        chunks: list[bytes] = []
        byte_count = 0
        try:
            for chunk in response.iter_content(chunk_size=65_536):
                if not chunk:
                    continue
                byte_count += len(chunk)
                if byte_count > self.document_max_bytes:
                    raise EdgarResponseError(f"SEC document exceeds byte limit: {url}")
                chunks.append(chunk)
        finally:
            response.close()
        body = b"".join(chunks)
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        result = (body, content_type.split(";", 1)[0].strip().lower())
        if self.document_cache_entries:
            self._document_cache[url] = result
            self._document_cache.move_to_end(url)
            while len(self._document_cache) > self.document_cache_entries:
                self._document_cache.popitem(last=False)
        return result

    def _get_json(self, url: str) -> Mapping[str, Any]:
        response = self._request(url, accept="application/json")
        try:
            payload = response.json()
        except ValueError as exc:
            raise EdgarResponseError(f"SEC request failed for {url}") from exc
        return _required_mapping(payload, field="SEC response")

    def _request(self, url: str, *, accept: str, stream: bool = False) -> Any:
        now = self._monotonic()
        if self._last_request_at is not None:
            remaining = self.minimum_interval_seconds - (now - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
        response = self._request_get(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": accept,
                "Accept-Encoding": "gzip, deflate",
            },
            timeout=self.timeout_seconds,
            stream=stream,
        )
        self._last_request_at = self._monotonic()
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise EdgarResponseError(f"SEC request failed for {url}") from exc
        return response
