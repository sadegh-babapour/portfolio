from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


UNIVERSE_VERSION = "sec-universe-2026-09-06.1"
PublicationStatus = Literal["published", "public_eligible", "planned_optional"]
ComparisonStatus = Literal["reviewed_with_metric_gates", "sector_contract_defined"]


@dataclass(frozen=True, slots=True)
class ResearchCompany:
    cik: str
    ticker: str
    company_name: str
    business_model: str
    industry_key: str
    comparison_subgroup: str
    publication_status: PublicationStatus
    comparison_status: ComparisonStatus


@dataclass(frozen=True, slots=True)
class SectorMetric:
    key: str
    label: str
    comparison_scope: str
    evidence_note: str


@dataclass(frozen=True, slots=True)
class IndustryContract:
    key: str
    label: str
    launch_status: Literal["core", "optional_after_launch"]
    companies: tuple[ResearchCompany, ...]
    metrics: tuple[SectorMetric, ...]
    comparison_notes: tuple[str, ...]


def _company(
    cik: str,
    ticker: str,
    company_name: str,
    business_model: str,
    industry_key: str,
    comparison_subgroup: str,
    *,
    publication_status: PublicationStatus = "public_eligible",
    comparison_status: ComparisonStatus = "sector_contract_defined",
) -> ResearchCompany:
    return ResearchCompany(
        cik=cik,
        ticker=ticker,
        company_name=company_name,
        business_model=business_model,
        industry_key=industry_key,
        comparison_subgroup=comparison_subgroup,
        publication_status=publication_status,
        comparison_status=comparison_status,
    )


GENERIC_METRICS = (
    SectorMetric(
        "revenue_growth_yoy",
        "Revenue growth",
        "all companies after presentation and transaction review",
        "Use the filing-defined revenue base and flag gross-versus-net changes.",
    ),
    SectorMetric(
        "operating_margin_change_yoy",
        "Operating-margin change",
        "direction across a comparable cost base",
        "Separate restructuring, acquisition, and divestiture effects.",
    ),
    SectorMetric(
        "cash_conversion",
        "Cash conversion",
        "direction after working-capital and denominator review",
        "Do not rank small-profit or timing-distorted ratios.",
    ),
    SectorMetric(
        "diluted_share_change_yoy",
        "Diluted-share change",
        "all companies",
        "Show dilution and repurchases as context, not value creation.",
    ),
)


PAYMENTS = IndustryContract(
    key="payments",
    label="Payments and commerce platforms",
    launch_status="core",
    companies=(
        _company(
            "0001633917", "PYPL", "PayPal Holdings, Inc.",
            "Digital wallet, branded checkout, and payment processing",
            "payments", "wallet_and_processing", publication_status="published",
            comparison_status="reviewed_with_metric_gates",
        ),
        _company(
            "0001512673", "XYZ", "Block, Inc.",
            "Seller ecosystem, consumer wallet, and payment processing",
            "payments", "wallet_and_processing",
            comparison_status="reviewed_with_metric_gates",
        ),
        _company(
            "0000798354", "FISV", "Fiserv, Inc.",
            "Merchant acceptance and financial-institution technology",
            "payments", "merchant_and_issuer_technology",
            comparison_status="reviewed_with_metric_gates",
        ),
        _company(
            "0001123360", "GPN", "Global Payments Inc.",
            "Merchant acquiring, issuer solutions, and payment software",
            "payments", "merchant_and_issuer_technology",
            comparison_status="reviewed_with_metric_gates",
        ),
        _company(
            "0001794669", "FOUR", "Shift4 Payments, Inc.",
            "Merchant acquiring and commerce payment software",
            "payments", "merchant_and_issuer_technology",
            comparison_status="reviewed_with_metric_gates",
        ),
    ),
    metrics=GENERIC_METRICS + (
        SectorMetric(
            "payment_volume_growth",
            "Payment-volume growth",
            "direction within the same processing model",
            "Company definitions differ; never infer volume from revenue.",
        ),
        SectorMetric(
            "transaction_margin_or_yield",
            "Transaction economics",
            "within an explicitly compatible subgroup",
            "Keep take rate, transaction margin, and processing yield distinct.",
        ),
    ),
    comparison_notes=(
        "Wallet/platform and merchant/issuer companies require subgroup views.",
        "Acquisitions, divestitures, gross-versus-net presentation, and settlement timing are filing-specific gates.",
    ),
)


DIGITAL_ADVERTISING = IndustryContract(
    key="digital_advertising",
    label="Digital advertising platforms",
    launch_status="core",
    companies=(
        _company("0001652044", "GOOGL", "Alphabet Inc.", "Search, video, cloud, and digital advertising", "digital_advertising", "scaled_platform"),
        _company("0001326801", "META", "Meta Platforms, Inc.", "Social platforms and digital advertising", "digital_advertising", "scaled_platform"),
        _company("0001564408", "SNAP", "Snap Inc.", "Camera-based social platform and advertising", "digital_advertising", "social_platform"),
        _company("0001506293", "PINS", "Pinterest, Inc.", "Visual discovery platform and advertising", "digital_advertising", "social_platform"),
        _company("0001713445", "RDDT", "Reddit, Inc.", "Community platform, advertising, and data licensing", "digital_advertising", "social_platform"),
    ),
    metrics=GENERIC_METRICS + (
        SectorMetric("advertising_revenue_growth", "Advertising growth", "all after segment review", "Separate advertising from cloud, subscriptions, and data licensing."),
        SectorMetric("audience_and_engagement", "Audience and engagement", "direction; definition-specific", "Retain each company's exact user and engagement definition."),
        SectorMetric("monetization", "Monetization", "within like-for-like audience definitions", "Do not compare ARPU-like measures across incompatible geographies or user bases."),
        SectorMetric("capital_expenditure_intensity", "Capital intensity", "all after infrastructure review", "Explain data-center and leased-capacity structures found in filings."),
    ),
    comparison_notes=(
        "Alphabet and Meta are scaled diversified platforms; Snap, Pinterest, and Reddit form a narrower subgroup.",
        "Infrastructure commitments and legal entities must be consolidated from the registrant filing evidence.",
    ),
)


AIRLINES = IndustryContract(
    key="airlines",
    label="US passenger airlines",
    launch_status="core",
    companies=(
        _company("0000027904", "DAL", "Delta Air Lines, Inc.", "Global network airline", "airlines", "network_carrier"),
        _company("0000100517", "UAL", "United Airlines Holdings, Inc.", "Global network airline", "airlines", "network_carrier"),
        _company("0000006201", "AAL", "American Airlines Group Inc.", "Global network airline", "airlines", "network_carrier"),
        _company("0000092380", "LUV", "Southwest Airlines Co.", "Primarily domestic passenger airline", "airlines", "domestic_carrier"),
        _company("0000766421", "ALK", "Alaska Air Group, Inc.", "Passenger airline group", "airlines", "domestic_carrier"),
    ),
    metrics=GENERIC_METRICS + (
        SectorMetric("capacity_and_traffic", "Capacity and traffic", "direction using ASM/RPM", "Keep capacity, traffic, and load-factor definitions explicit."),
        SectorMetric("unit_revenue", "Unit revenue", "same passenger/network subgroup", "Reconcile RASM variants and loyalty revenue treatment."),
        SectorMetric("unit_cost", "Unit cost", "direction with fuel and special-item labels", "Do not mix GAAP expense with adjusted CASM-ex definitions."),
        SectorMetric("liquidity_and_obligations", "Liquidity and obligations", "all", "Include aircraft commitments, leases, debt, and restricted cash."),
    ),
    comparison_notes=(
        "Network and primarily domestic carriers are separate comparison subgroups.",
        "Fleet transactions, loyalty programs, labor agreements, and fuel adjustment definitions require filing review.",
    ),
)


ENERGY = IndustryContract(
    key="energy",
    label="US oil and gas producers",
    launch_status="core",
    companies=(
        _company("0000034088", "XOM", "Exxon Mobil Corporation", "Integrated energy producer", "energy", "integrated_major"),
        _company("0000093410", "CVX", "Chevron Corporation", "Integrated energy producer", "energy", "integrated_major"),
        _company("0001163165", "COP", "ConocoPhillips", "Exploration and production", "energy", "upstream_producer"),
        _company("0000797468", "OXY", "Occidental Petroleum Corporation", "Oil, gas, chemicals, and low-carbon businesses", "energy", "diversified_producer"),
        _company("0000821189", "EOG", "EOG Resources, Inc.", "Exploration and production", "energy", "upstream_producer"),
    ),
    metrics=GENERIC_METRICS + (
        SectorMetric("production", "Production", "same commodity and subgroup", "Separate organic output from acquired or divested volumes."),
        SectorMetric("realized_prices", "Realized prices", "same commodity basis", "Show hedging and benchmark effects separately."),
        SectorMetric("capital_expenditure", "Capital expenditure", "direction within subgroup", "Separate maintenance, growth, acquisition, and low-carbon investment where disclosed."),
        SectorMetric("leverage_and_distributions", "Leverage and distributions", "all with balance-sheet gates", "Keep dividends, buybacks, debt reduction, and asset sales distinct."),
    ),
    comparison_notes=(
        "Integrated majors and upstream producers require separate margin and production views.",
        "Commodity prices, acquisitions, divestitures, and hedging can dominate headline growth.",
    ),
)


CONNECTIVITY = IndustryContract(
    key="connectivity",
    label="US connectivity providers",
    launch_status="core",
    companies=(
        _company("0000732712", "VZ", "Verizon Communications Inc.", "Wireless and fixed connectivity", "connectivity", "wireless_led"),
        _company("0000732717", "T", "AT&T Inc.", "Wireless and fiber connectivity", "connectivity", "wireless_led"),
        _company("0001283699", "TMUS", "T-Mobile US, Inc.", "Wireless communications", "connectivity", "wireless_led"),
        _company("0001091667", "CHTR", "Charter Communications, Inc.", "Cable broadband and connectivity", "connectivity", "cable_led"),
        _company("0001166691", "CMCSA", "Comcast Corporation", "Cable broadband, media, and entertainment", "connectivity", "cable_led"),
    ),
    metrics=GENERIC_METRICS + (
        SectorMetric("service_revenue", "Service revenue", "same connectivity subgroup", "Separate equipment, media, studios, and other non-service revenue."),
        SectorMetric("subscriber_change_and_churn", "Subscriber change and churn", "same product and subgroup", "Retain exact subscriber, connection, and churn definitions."),
        SectorMetric("revenue_per_account", "Revenue per account", "same product and definition", "Do not mix ARPU, ARPA, and average-bill measures."),
        SectorMetric("capital_intensity_and_leverage", "Capital intensity and leverage", "all after lease/debt review", "Include spectrum, device financing, leases, and construction commitments."),
    ),
    comparison_notes=(
        "Wireless-led and cable-led operators require separate operating-driver views.",
        "Comcast's media/theme-park exposure must not be attributed to connectivity performance.",
    ),
)


BROKERAGE = IndustryContract(
    key="brokerage",
    label="Brokerage and trading platforms",
    launch_status="core",
    companies=(
        _company("0001783879", "HOOD", "Robinhood Markets, Inc.", "Retail brokerage and financial-services platform", "brokerage", "retail_multi_asset"),
        _company("0001679788", "COIN", "Coinbase Global, Inc.", "Crypto-asset trading and infrastructure platform", "brokerage", "crypto_platform"),
        _company("0001381197", "IBKR", "Interactive Brokers Group, Inc.", "Electronic brokerage, clearing, custody, and securities lending", "brokerage", "active_broker"),
        _company("0000316709", "SCHW", "The Charles Schwab Corporation", "Brokerage, banking, custody, and wealth management", "brokerage", "bank_broker"),
        _company("0001397911", "LPLA", "LPL Financial Holdings Inc.", "Independent broker-dealer and adviser platform", "brokerage", "advisor_platform"),
    ),
    metrics=GENERIC_METRICS + (
        SectorMetric("transaction_revenue", "Transaction revenue", "direction with asset-class mix shown", "Separate crypto, equity, options, and other transaction definitions."),
        SectorMetric("net_interest_revenue", "Net interest revenue", "direction after rate and balance review", "Show rates, client cash, margin lending, and securities-lending effects."),
        SectorMetric("client_assets_and_flows", "Client assets and flows", "direction; definition-specific", "Do not rank custody, platform, and administered assets as identical."),
        SectorMetric("funded_accounts_and_activity", "Accounts and activity", "direction within subgroup", "Retain exact funded-account, active-user, DART, and volume definitions."),
        SectorMetric("regulatory_capital_and_liquidity", "Capital and liquidity", "company-specific gate", "Broker-dealer net capital, bank capital, and crypto safeguards are not interchangeable."),
    ),
    comparison_notes=(
        "Revenue rankings require subgroups because crypto, active brokerage, bank brokerage, and adviser platforms have different economics.",
        "Interest-rate exposure, client-cash mix, regulatory capital, principal-versus-agent presentation, and acquisitions are mandatory gates.",
    ),
)


GAMING_OPTIONAL = IndustryContract(
    key="interactive_entertainment",
    label="Interactive entertainment",
    launch_status="optional_after_launch",
    companies=(
        _company("0000712515", "EA", "Electronic Arts Inc.", "Video-game publisher and live-services operator", "interactive_entertainment", "publisher", publication_status="planned_optional"),
        _company("0000946581", "TTWO", "Take-Two Interactive Software, Inc.", "Video-game publisher and live-services operator", "interactive_entertainment", "publisher", publication_status="planned_optional"),
        _company("0001315098", "RBLX", "Roblox Corporation", "User-generated interactive platform", "interactive_entertainment", "platform", publication_status="planned_optional"),
        _company("0001810806", "U", "Unity Software Inc.", "Real-time content creation and monetization software", "interactive_entertainment", "software_platform", publication_status="planned_optional"),
        _company("0001828016", "PLTK", "Playtika Holding Corp.", "Mobile-game developer and publisher", "interactive_entertainment", "mobile_publisher", publication_status="planned_optional"),
    ),
    metrics=GENERIC_METRICS + (
        SectorMetric("bookings_and_deferred_revenue", "Bookings and deferred revenue", "direction within compatible revenue models", "Reconcile bookings, virtual currency, and GAAP revenue timing."),
        SectorMetric("audience_and_engagement", "Audience and engagement", "definition-specific direction", "Keep users, payers, hours, and platform activity distinct."),
        SectorMetric("content_and_software_investment", "Content and software investment", "direction within subgroup", "Review capitalization, amortization, impairment, and acquisition effects."),
        SectorMetric("platform_fees_and_dilution", "Platform fees and dilution", "company-specific context", "Separate distribution economics and stock compensation from engagement growth."),
    ),
    comparison_notes=(
        "Publishers, user-generated platforms, and software platforms are not one ranking group.",
        "Fiscal calendars and release schedules differ materially; calendar-quarter matching is not assumed.",
    ),
)


CORE_INDUSTRY_CONTRACTS = (
    PAYMENTS,
    DIGITAL_ADVERTISING,
    AIRLINES,
    ENERGY,
    CONNECTIVITY,
    BROKERAGE,
)
OPTIONAL_INDUSTRY_CONTRACTS = (GAMING_OPTIONAL,)
CORE_RESEARCH_UNIVERSE = tuple(
    company for industry in CORE_INDUSTRY_CONTRACTS for company in industry.companies
)
OPTIONAL_RESEARCH_UNIVERSE = tuple(
    company for industry in OPTIONAL_INDUSTRY_CONTRACTS for company in industry.companies
)


def validate_universe() -> None:
    all_companies = CORE_RESEARCH_UNIVERSE + OPTIONAL_RESEARCH_UNIVERSE
    ciks = [company.cik for company in all_companies]
    tickers = [company.ticker for company in all_companies]
    if len(ciks) != len(set(ciks)) or len(tickers) != len(set(tickers)):
        raise ValueError("research universe CIKs and tickers must be unique")
    if any(len(company.cik) != 10 or not company.cik.isdigit() for company in all_companies):
        raise ValueError("research universe CIKs must be ten digits")
    if any(len(industry.companies) != 5 for industry in CORE_INDUSTRY_CONTRACTS):
        raise ValueError("each core industry contract must contain five companies")
    if any(company.publication_status == "planned_optional" for company in CORE_RESEARCH_UNIVERSE):
        raise ValueError("optional companies cannot enter the core refresh universe")


validate_universe()
