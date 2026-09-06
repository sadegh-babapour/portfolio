from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import PurePosixPath
from typing import Iterable
from urllib.parse import parse_qs, urlparse
from xml.etree import ElementTree

from .contracts import (
    DocumentSnapshot,
    EntityRole,
    EvidenceClaim,
    FactObservation,
    FilingDocument,
    FilingMetadata,
    ResearchQuestion,
    TextEvidence,
)
from .edgar import SEC_ARCHIVES_BASE_URL, EdgarClient, normalize_cik


DOCUMENT_EXTRACTION_VERSION = "edgar-document-2026-09-06.1"
MAX_EVIDENCE_CHARACTERS = 8_000
BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "p",
        "section",
        "table",
        "td",
        "th",
        "tr",
    }
)


@dataclass(frozen=True, slots=True)
class FilingResearchBundle:
    filing: FilingMetadata
    documents: tuple[FilingDocument, ...]
    snapshots: tuple[DocumentSnapshot, ...]
    evidence: tuple[TextEvidence, ...]
    entity_roles: tuple[EntityRole, ...]
    claims: tuple[EvidenceClaim, ...]
    questions: tuple[ResearchQuestion, ...]


class _FilingIndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_target_table = False
        self.in_row = False
        self.in_cell = False
        self.current_cell_text: list[str] = []
        self.current_cell_href: str | None = None
        self.current_row: list[tuple[str, str | None]] = []
        self.rows: list[list[tuple[str, str | None]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "table" and attributes.get("class") == "tableFile":
            self.in_target_table = True
        elif self.in_target_table and tag == "tr":
            self.in_row = True
            self.current_row = []
        elif self.in_row and tag in {"td", "th"}:
            self.in_cell = True
            self.current_cell_text = []
            self.current_cell_href = None
        elif self.in_cell and tag == "a" and attributes.get("href"):
            self.current_cell_href = attributes["href"]

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current_cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.in_cell and tag in {"td", "th"}:
            text = " ".join("".join(self.current_cell_text).split())
            self.current_row.append((text, self.current_cell_href))
            self.in_cell = False
        elif self.in_row and tag == "tr":
            if self.current_row:
                self.rows.append(self.current_row)
            self.in_row = False
        elif self.in_target_table and tag == "table":
            self.in_target_table = False


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden_depth += 1
        elif not self.hidden_depth and tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self.hidden_depth:
            self.hidden_depth -= 1
        elif not self.hidden_depth and tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)

    def text(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self.parts).splitlines())
        return "\n".join(line for line in lines if line)


def filing_archive_url(cik: str, accession_number: str, document_name: str) -> str:
    normalized_cik = normalize_cik(cik)
    accession_path = accession_number.replace("-", "")
    safe_name = PurePosixPath(document_name).name
    if safe_name != document_name or not re.fullmatch(r"[A-Za-z0-9_.-]+", safe_name):
        raise ValueError("SEC document name must be a safe archive filename")
    return f"{SEC_ARCHIVES_BASE_URL}/{int(normalized_cik)}/{accession_path}/{safe_name}"


def filing_index_document_url(cik: str, accession_number: str) -> str:
    return filing_archive_url(cik, accession_number, f"{accession_number}-index.html")


def _unwrapped_href(href: str) -> str:
    parsed = urlparse(href)
    if parsed.path == "/ix":
        values = parse_qs(parsed.query).get("doc")
        if values:
            return values[0]
    return parsed.path


def parse_filing_index(
    source: str,
    *,
    cik: str,
    accession_number: str,
) -> tuple[FilingDocument, ...]:
    parser = _FilingIndexParser()
    parser.feed(source)
    documents: list[FilingDocument] = []
    accession_path = accession_number.replace("-", "")
    expected_prefix = f"/Archives/edgar/data/{int(normalize_cik(cik))}/{accession_path}/"
    for row in parser.rows:
        if len(row) != 5 or row[0][0].lower() == "seq":
            continue
        sequence_text, description, document_cell, document_type, size_text = (
            cell[0] for cell in row
        )
        href = row[2][1]
        if not href:
            continue
        path = _unwrapped_href(href)
        if not path.startswith(expected_prefix):
            raise ValueError("Filing index contains a document outside its SEC directory")
        document_name = PurePosixPath(path).name
        sequence = int(sequence_text) if sequence_text.isdigit() else None
        size_bytes = int(size_text) if size_text.isdigit() else None
        upper_type = document_type.upper()
        if upper_type.startswith("EX-"):
            category = "exhibit"
        elif upper_type == "GRAPHIC":
            category = "graphic"
        elif upper_type.startswith("10-") or upper_type == "8-K":
            category = "primary"
        elif description.lower() == "complete submission text file":
            category = "complete_submission"
        else:
            category = "data"
        documents.append(
            FilingDocument(
                cik=normalize_cik(cik),
                accession_number=accession_number,
                sequence=sequence,
                description=description,
                document_name=document_name,
                document_type=document_type,
                size_bytes=size_bytes,
                category=category,
                sec_url=f"https://www.sec.gov{path}",
            )
        )
    return tuple(documents)


def fetch_filing_inventory(
    client: EdgarClient,
    filing: FilingMetadata,
) -> tuple[FilingDocument, ...]:
    url = filing_index_document_url(filing.cik, filing.accession_number)
    body, _ = client.filing_document(url)
    return parse_filing_index(
        body.decode("utf-8", errors="replace"),
        cik=filing.cik,
        accession_number=filing.accession_number,
    )


def html_to_text(source: str) -> str:
    parser = _VisibleTextParser()
    parser.feed(source)
    return parser.text()


def fetch_snapshot(client: EdgarClient, document: FilingDocument) -> DocumentSnapshot:
    body, content_type = client.filing_document(document.sec_url)
    if content_type in {"text/html", "application/xhtml+xml"} or document.document_name.lower().endswith(
        (".htm", ".html")
    ):
        text = html_to_text(body.decode("utf-8", errors="replace"))
    elif content_type in {"application/xml", "text/xml", "text/plain"}:
        text = body.decode("utf-8", errors="replace")
    else:
        raise ValueError(f"Unsupported research document content type: {content_type}")
    return DocumentSnapshot(
        document=document,
        content_type=content_type,
        content_sha256=hashlib.sha256(body).hexdigest(),
        byte_count=len(body),
        text=text,
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _taxonomy(namespace: str) -> str:
    if "fasb.org/us-gaap" in namespace:
        return "us-gaap"
    if "xbrl.sec.gov/dei" in namespace:
        return "dei"
    match = re.search(r"/([A-Za-z0-9_-]+)/\d{4}", namespace)
    return match.group(1).lower() if match else namespace[:80]


def _unit_name(unit: ElementTree.Element) -> str | None:
    measures = [
        (item.text or "").rsplit(":", 1)[-1]
        for item in unit.iter()
        if _local_name(item.tag) == "measure"
    ]
    if not measures:
        return None
    if len(measures) == 1:
        return measures[0]
    if len(measures) == 2:
        return f"{measures[0]}/{measures[1]}"
    return None


def extract_instance_facts(
    source: bytes,
    *,
    filing: FilingMetadata,
    source_url: str,
    period_start: date = date(2022, 1, 1),
) -> tuple[FactObservation, ...]:
    root = ElementTree.fromstring(source)
    contexts: dict[str, tuple[date | None, date]] = {}
    units: dict[str, str] = {}
    fiscal_year: int | None = None
    fiscal_period: str | None = None

    for child in root:
        local = _local_name(child.tag)
        if local == "context":
            context_id = child.attrib.get("id")
            if not context_id or any(
                _local_name(item.tag) in {"explicitMember", "typedMember"}
                for item in child.iter()
            ):
                continue
            start_text = next(
                (item.text for item in child.iter() if _local_name(item.tag) == "startDate"),
                None,
            )
            end_text = next(
                (
                    item.text
                    for item in child.iter()
                    if _local_name(item.tag) in {"endDate", "instant"}
                ),
                None,
            )
            if end_text:
                contexts[context_id] = (
                    date.fromisoformat(start_text) if start_text else None,
                    date.fromisoformat(end_text),
                )
        elif local == "unit" and child.attrib.get("id"):
            unit_name = _unit_name(child)
            if unit_name:
                units[child.attrib["id"]] = unit_name

    for child in root:
        local = _local_name(child.tag)
        if local == "DocumentFiscalYearFocus" and child.text:
            fiscal_year = int(child.text.strip())
        elif local == "DocumentFiscalPeriodFocus" and child.text:
            fiscal_period = child.text.strip()

    observations: list[FactObservation] = []
    for child in root:
        context_ref = child.attrib.get("contextRef")
        unit_ref = child.attrib.get("unitRef")
        if not context_ref or context_ref not in contexts or not unit_ref or unit_ref not in units:
            continue
        if child.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
            continue
        raw_value = "".join(child.itertext()).strip().replace(",", "")
        try:
            decimal_value = Decimal(raw_value)
        except InvalidOperation:
            continue
        value: int | float = (
            int(decimal_value)
            if decimal_value == decimal_value.to_integral_value()
            else float(decimal_value)
        )
        start, end = contexts[context_ref]
        if end < period_start:
            continue
        namespace = child.tag[1:].split("}", 1)[0] if child.tag.startswith("{") else ""
        concept = _local_name(child.tag)
        observations.append(
            FactObservation(
                cik=filing.cik,
                taxonomy=_taxonomy(namespace),
                concept=concept,
                label=concept,
                description="Extracted from the filing's SEC XBRL instance.",
                unit=units[unit_ref],
                value=value,
                period_start=start,
                period_end=end,
                filed_on=filing.filed_on,
                accepted_at=filing.accepted_at,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                form=filing.form,
                accession_number=filing.accession_number,
                frame=None,
                context_kind="duration" if start else "instant",
                is_amendment=filing.is_amendment,
                sec_index_url=source_url,
            )
        )
    return tuple(observations)


SECTION_PATTERNS = (
    ("management_discussion", "Management discussion and analysis", r"ITEM\s+2[:.]?\s+MANAGEMENT.?S DISCUSSION", r"ITEM\s+3[:.]?\s+QUANTITATIVE"),
    ("market_risk", "Market risk", r"ITEM\s+3[:.]?\s+QUANTITATIVE", r"ITEM\s+4[:.]?\s+CONTROLS"),
    ("risk_factors", "Risk factors", r"ITEM\s+1A[:.]?\s+RISK FACTORS", r"ITEM\s+1B|ITEM\s+2"),
)

KEYWORD_PATTERNS = (
    ("liquidity", "Liquidity and capital resources", r"LIQUIDITY AND CAPITAL RESOURCES"),
    ("commitments", "Commitments and contingencies", r"COMMITMENTS? AND CONTINGENCIES"),
    ("related_parties", "Related-party disclosure", r"RELATED PART(?:Y|IES)"),
    ("non_gaap", "Non-GAAP disclosure", r"NON-GAAP"),
    ("debt", "Debt or covenant disclosure", r"\b(?:DEBT|COVENANTS?)\b"),
    ("leases", "Lease disclosure", r"\bLEASES?\b"),
    ("vie", "Variable-interest entity disclosure", r"VARIABLE INTEREST ENTIT|\bVIE\b"),
    ("receivables_transfer", "Receivables transfer or securitization", r"RECEIVABLES? (?:SALE|PURCHASE|TRANSFER)|SECURITI[ZS]"),
    ("restructuring", "Restructuring disclosure", r"\bRESTRUCTURING\b"),
    ("acquisition", "Acquisition or business combination", r"\bACQUISITION\b|BUSINESS COMBINATION"),
    ("divestiture", "Divestiture or disposition", r"\bDIVESTITURE\b|\bDISPOSITION\b"),
    ("discontinued_operations", "Discontinued operations", r"DISCONTINUED OPERATIONS"),
    ("held_for_sale", "Assets or business held for sale", r"HELD FOR SALE"),
    ("presentation_change", "Presentation or reclassification change", r"\bRECLASSIF(?:IED|ICATIONS?)\b|CHANGE IN PRESENTATION"),
    ("impairment", "Impairment disclosure", r"\bIMPAIRMENT\b"),
    ("transaction_costs", "Transaction or integration costs", r"TRANSACTION COSTS|INTEGRATION (?:COSTS|EXPENSES)"),
    ("tax_rate", "Effective income-tax rate", r"EFFECTIVE (?:INCOME )?TAX RATE"),
)


def extract_filing_sections(snapshot: DocumentSnapshot) -> tuple[TextEvidence, ...]:
    evidence: list[TextEvidence] = []
    upper_text = snapshot.text.upper()
    for category, heading, start_pattern, end_pattern in SECTION_PATTERNS:
        starts = list(re.finditer(start_pattern, upper_text))
        if not starts:
            continue
        start = starts[-1].start()
        end_match = re.search(end_pattern, upper_text[start + 1 :])
        end = start + 1 + end_match.start() if end_match else len(snapshot.text)
        excerpt_end = min(end, start + MAX_EVIDENCE_CHARACTERS)
        evidence.append(
            TextEvidence(
                category=category,
                heading=heading,
                excerpt=snapshot.text[start:excerpt_end],
                start_offset=start,
                end_offset=excerpt_end,
                extraction_method="heading_boundary",
                extraction_version=DOCUMENT_EXTRACTION_VERSION,
                confidence="high" if end_match else "medium",
                source_url=snapshot.document.sec_url,
                source_sha256=snapshot.content_sha256,
            )
        )
    return tuple(evidence)


def extract_keyword_evidence(snapshot: DocumentSnapshot) -> tuple[TextEvidence, ...]:
    evidence: list[TextEvidence] = []
    upper_text = snapshot.text.upper()
    for category, heading, pattern in KEYWORD_PATTERNS:
        for match in tuple(re.finditer(pattern, upper_text))[:3]:
            start = max(0, match.start() - 300)
            end = min(len(snapshot.text), match.end() + 900)
            evidence.append(
                TextEvidence(
                    category=category,
                    heading=heading,
                    excerpt=snapshot.text[start:end],
                    start_offset=start,
                    end_offset=end,
                    extraction_method="keyword_window",
                    extraction_version=DOCUMENT_EXTRACTION_VERSION,
                    confidence="medium",
                    source_url=snapshot.document.sec_url,
                    source_sha256=snapshot.content_sha256,
                )
            )
    return tuple(evidence)


def extract_entity_roles(snapshots: Iterable[DocumentSnapshot]) -> tuple[EntityRole, ...]:
    roles: list[EntityRole] = []
    advisor_pattern = re.compile(
        r"([^\n.]{2,240}?) acted as (legal|financial and structuring) advisors? to (PayPal|KKR)",
        re.IGNORECASE,
    )
    party_pattern = re.compile(
        r"(?m)^([A-Z][A-Z0-9 ()&.,À-ÖØ-Ý'’/-]{2,180})\n(?:as|in its capacity as) ([A-Za-z][^\n]{1,100})$"
    )
    for snapshot in snapshots:
        for match in advisor_pattern.finditer(snapshot.text):
            entities = re.split(r",|\band\b", match.group(1))
            for entity in entities:
                name = " ".join(entity.split()).strip(" ,")
                if not name:
                    continue
                roles.append(
                    EntityRole(
                        entity_name=name,
                        entity_type=(
                            "law_firm"
                            if match.group(2).casefold() == "legal"
                            else "financial_adviser"
                        ),
                        role=f"{match.group(2).lower()} advisor to {match.group(3)}",
                        evidence_excerpt=match.group(0),
                        source_url=snapshot.document.sec_url,
                        confidence="high",
                    )
                )
        for match in party_pattern.finditer(snapshot.text):
            display_name = " ".join(match.group(1).split()).title()
            display_name = display_name.replace("Paypal", "PayPal").replace("Bny", "BNY")
            roles.append(
                EntityRole(
                    entity_name=display_name,
                    entity_type="organization",
                    role=" ".join(match.group(2).split()),
                    evidence_excerpt=match.group(0),
                    source_url=snapshot.document.sec_url,
                    confidence="medium",
                )
            )
    unique = {
        (role.entity_name.casefold(), role.role.casefold(), role.source_url): role
        for role in roles
    }
    return tuple(unique.values())


def build_paypal_bnpl_claims(
    snapshots: Iterable[DocumentSnapshot],
) -> tuple[tuple[EvidenceClaim, ...], tuple[ResearchQuestion, ...]]:
    documents = tuple(snapshots)
    combined = "\n".join(snapshot.text for snapshot in documents)
    claims: list[EvidenceClaim] = []
    transaction_signal = any(
        marker in combined
        for marker in ("€40 billion", "ALPS PARTNERS", "Freshfields Bruckhaus Deringer")
    )
    if not transaction_signal:
        return (), ()
    if "€40 billion" in combined and "BNPL" in combined:
        scope_urls = tuple(
            snapshot.document.sec_url
            for snapshot in documents
            if "€40 billion" in snapshot.text and "BNPL" in snapshot.text
        )
        claims.append(
            EvidenceClaim(
                claim_kind="transaction_scope",
                statement=(
                    "The disclosed arrangement contemplated purchases of up to €40 "
                    "billion of eligible current and future European PayPal BNPL receivables."
                ),
                status="reported",
                confidence="high",
                source_urls=scope_urls,
            )
        )
    if "Freshfields Bruckhaus Deringer" in combined and "legal advisors to PayPal" in combined:
        adviser_urls = tuple(
            snapshot.document.sec_url
            for snapshot in documents
            if "Freshfields Bruckhaus Deringer" in snapshot.text
            and "legal advisors to PayPal" in snapshot.text
        )
        claims.append(
            EvidenceClaim(
                claim_kind="adviser_role",
                statement="Freshfields Bruckhaus Deringer LLP acted as a legal advisor to PayPal.",
                status="reported",
                confidence="high",
                source_urls=adviser_urls,
            )
        )
    if "as Purchaser" in combined and "PAYPAL (EUROPE)" in combined:
        contract_urls = tuple(
            snapshot.document.sec_url
            for snapshot in documents
            if "as Purchaser" in snapshot.text and "PAYPAL (EUROPE)" in snapshot.text
        )
        claims.append(
            EvidenceClaim(
                claim_kind="contract_structure",
                statement=(
                    "The filed agreements identify an Alps entity as purchaser and "
                    "PayPal (Europe) as seller and receivables manager."
                ),
                status="reported",
                confidence="high",
                source_urls=contract_urls,
            )
        )
    questions = (
        ResearchQuestion(
            category="economic_effect",
            question="How much receivable balance, gain/loss, funding capacity, and risk transfer resulted by period?",
            reason="The contract ceiling is not the same as realized financial impact.",
        ),
        ResearchQuestion(
            category="control_and_risk",
            question="Which credit, servicing, repurchase, indemnity, and termination risks remain with PayPal?",
            reason="A sale structure can transfer funding while retaining material obligations.",
        ),
        ResearchQuestion(
            category="entity_resolution",
            question="Which Alps entities and KKR-managed funds bear each contractual role?",
            reason="Advisers, named special-purpose entities, managers, and economic funders are not interchangeable.",
        ),
    )
    return tuple(claims), questions


def extract_change_explanation_claims(
    snapshots: Iterable[DocumentSnapshot],
) -> tuple[EvidenceClaim, ...]:
    lead_patterns = (
        "increase in net revenues was driven",
        "increase in revenue was driven",
        "decrease in net revenues was driven",
        "decrease in revenue was driven",
        "increase in operating expenses was due",
        "decrease in operating expenses was due",
        "operating margin declined",
        "operating margin increased",
        "decrease in net income was due",
        "increase in net income was due",
        "net cash provided by operating activities increased",
        "net cash provided by operating activities decreased",
    )
    claims: list[EvidenceClaim] = []
    for snapshot in snapshots:
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", snapshot.text)
        for sentence in sentences:
            normalized = " ".join(sentence.split())
            lowered = normalized.casefold()
            if not any(pattern in lowered for pattern in lead_patterns):
                continue
            claims.append(
                EvidenceClaim(
                    claim_kind="management_change_explanation",
                    statement=normalized[:2_000],
                    status="reported",
                    confidence="high",
                    source_urls=(snapshot.document.sec_url,),
                )
            )
    unique = {(claim.statement, claim.source_urls): claim for claim in claims}
    return tuple(unique.values())


def research_filing(
    client: EdgarClient,
    filing: FilingMetadata,
    *,
    include_exhibit_prefixes: tuple[str, ...] = ("EX-10", "EX-99.1"),
    max_documents: int = 6,
) -> FilingResearchBundle:
    if max_documents < 1 or max_documents > 20:
        raise ValueError("max_documents must be between 1 and 20")
    documents = fetch_filing_inventory(client, filing)
    selected = [document for document in documents if document.category == "primary"]
    selected.extend(
        document
        for document in documents
        if document.category == "exhibit"
        and any(document.document_type.upper().startswith(prefix) for prefix in include_exhibit_prefixes)
    )
    selected = selected[:max_documents]
    snapshots = tuple(fetch_snapshot(client, document) for document in selected)
    evidence = tuple(
        item
        for snapshot in snapshots
        for item in (
            *extract_filing_sections(snapshot),
            *extract_keyword_evidence(snapshot),
        )
    )
    entity_roles = extract_entity_roles(snapshots)
    transaction_claims, questions = build_paypal_bnpl_claims(snapshots)
    claims = transaction_claims + extract_change_explanation_claims(snapshots)
    return FilingResearchBundle(
        filing=filing,
        documents=documents,
        snapshots=snapshots,
        evidence=evidence,
        entity_roles=entity_roles,
        claims=claims,
        questions=questions,
    )
