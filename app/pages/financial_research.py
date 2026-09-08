from __future__ import annotations

from nicegui import ui

from app.components.charts import enable_viewport_chart_animations, viewport_chart
from app.components.navbar import with_layout
from app.financial_research.service import (
    load_filing_directory,
    load_filing_profile,
    load_payments_comparison,
    load_sector_screen,
)


COLORS = {
    "revenue": "#2563eb",
    "growth": "#0891b2",
    "margin": "#d97706",
    "earnings": "#7c3aed",
    "cash": "#0f766e",
    "shares": "#be123c",
}
COMPANY_COLORS = ("#2563eb", "#0f766e", "#d97706", "#7c3aed", "#be123c")


def _source_link(label: str, url: str) -> None:
    ui.link(label, url, new_tab=True).classes(
        "text-primary font-semibold no-underline hover:underline"
    )


def _unavailable_state(message: str = "Financial data is temporarily unavailable") -> None:
    with ui.card().classes("w-full p-5 gap-2 border border-warning"):
        ui.label(message).classes("text-xl font-bold text-warning")
        _source_link("Search SEC EDGAR ↗", "https://www.sec.gov/edgar/search/")


def _section_title(title: str, note: str | None = None) -> None:
    with ui.column().classes("w-full gap-0 mt-2"):
        ui.label(title).classes("text-2xl font-bold text-primary")
        if note:
            ui.label(note).classes("text-sm")


def _metric_map(analysis: dict) -> dict[str, dict]:
    return {metric["key"]: metric for metric in analysis.get("metrics", [])}


def _metric_value(analysis: dict, key: str, divisor: float = 1.0) -> float | None:
    metric = _metric_map(analysis).get(key)
    value = metric.get("value") if metric else None
    return value / divisor if value is not None else None


def _compact_metric_cards(latest: dict) -> None:
    metrics = _metric_map(latest)
    cards = (
        ("Revenue", "revenue", "revenue_growth_yoy", COLORS["revenue"], "Revenue growth YoY"),
        ("Operating margin", "operating_margin", "operating_margin_change_yoy", COLORS["margin"], "Change YoY"),
        ("Net income", "net_income", None, COLORS["earnings"], None),
        ("Simplified FCF", "simplified_free_cash_flow", None, COLORS["cash"], None),
        ("Diluted shares", "diluted_weighted_average_shares", "diluted_share_change_yoy", COLORS["shares"], "Change YoY"),
    )
    with ui.element("section").classes(
        "grid w-full grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5"
    ).props('aria-label="Latest financial measures"'):
        for label, value_key, change_key, color, change_label in cards:
            value = metrics.get(value_key)
            change = metrics.get(change_key) if change_key else None
            with ui.card().classes("w-full h-full p-4 gap-1 border").style(
                f"border-top: 4px solid {color}"
            ):
                ui.label(label).classes("text-sm font-bold").style(f"color: {color}")
                ui.label(value["display_value"] if value else "Unavailable").classes(
                    "text-2xl lg:text-3xl font-bold"
                )
                if change and change.get("value") is not None:
                    ui.label(f"{change['display_value']} {change_label}").classes(
                        "text-xs font-semibold"
                    )


def _company_overview_charts(history: list[dict], ticker: str) -> None:
    chronological = sorted(history, key=lambda item: item["period_end"])
    labels = [f"Q{row['fiscal_quarter']} {row['period_end'][:4]}" for row in chronological]
    with ui.element("section").classes(
        "grid w-full grid-cols-1 gap-4 xl:grid-cols-2"
    ):
        with ui.card().classes("w-full min-w-0 p-4 gap-2 border"):
            ui.label("Revenue and operating margin").classes(
                "text-lg font-bold text-primary"
            )
            viewport_chart(
                {
                    "tooltip": {"trigger": "axis"},
                    "legend": {"data": ["Revenue ($B)", "Operating margin (%)"], "bottom": 0},
                    "grid": {"left": 52, "right": 54, "top": 24, "bottom": 54},
                    "xAxis": {"type": "category", "data": labels, "axisLabel": {"rotate": 30}},
                    "yAxis": [
                        {"type": "value", "name": "$B"},
                        {"type": "value", "name": "%"},
                    ],
                    "series": [
                        {
                            "name": "Revenue ($B)",
                            "type": "bar",
                            "data": [_metric_value(row, "revenue", 1_000_000_000) for row in chronological],
                            "itemStyle": {"color": COLORS["revenue"]},
                        },
                        {
                            "name": "Operating margin (%)",
                            "type": "line",
                            "yAxisIndex": 1,
                            "connectNulls": False,
                            "symbolSize": 7,
                            "data": [_metric_value(row, "operating_margin") for row in chronological],
                            "itemStyle": {"color": COLORS["margin"]},
                        },
                    ],
                },
                classes="w-full h-72 xl:h-64",
                aria_label=f"{ticker} quarterly revenue and operating margin",
            )
        with ui.card().classes("w-full min-w-0 p-4 gap-2 border"):
            ui.label("Earnings and cash generation").classes(
                "text-lg font-bold text-positive"
            )
            viewport_chart(
                {
                    "tooltip": {"trigger": "axis"},
                    "legend": {"data": ["Net income ($B)", "Simplified FCF ($B)"], "bottom": 0},
                    "grid": {"left": 52, "right": 18, "top": 24, "bottom": 54},
                    "xAxis": {"type": "category", "data": labels, "axisLabel": {"rotate": 30}},
                    "yAxis": {"type": "value", "name": "$B"},
                    "series": [
                        {
                            "name": "Net income ($B)",
                            "type": "bar",
                            "data": [_metric_value(row, "net_income", 1_000_000_000) for row in chronological],
                            "itemStyle": {"color": COLORS["earnings"]},
                        },
                        {
                            "name": "Simplified FCF ($B)",
                            "type": "line",
                            "connectNulls": False,
                            "symbolSize": 7,
                            "data": [_metric_value(row, "simplified_free_cash_flow", 1_000_000_000) for row in chronological],
                            "itemStyle": {"color": COLORS["cash"]},
                        },
                    ],
                },
                classes="w-full h-72 xl:h-64",
                aria_label=f"{ticker} quarterly net income and simplified free cash flow",
            )


def _company_quarter_tabs(history: list[dict], ticker: str) -> None:
    available = {row["fiscal_quarter"] for row in history}
    if not available:
        return
    default_quarter = max(history, key=lambda item: item["period_end"])[
        "fiscal_quarter"
    ]
    tabs_by_quarter = {}
    with ui.tabs().classes("w-full justify-start text-primary") as tabs:
        for quarter in range(1, 5):
            tabs_by_quarter[quarter] = ui.tab(f"Q{quarter}")
    with ui.tab_panels(tabs, value=tabs_by_quarter[default_quarter]).classes(
        "w-full bg-transparent"
    ):
        for quarter in range(1, 5):
            with ui.tab_panel(tabs_by_quarter[quarter]).classes("w-full p-0 pt-3"):
                points = sorted(
                    (row for row in history if row["fiscal_quarter"] == quarter),
                    key=lambda item: item["period_end"],
                )
                years = [row["period_end"][:4] for row in points]
                with ui.card().classes("w-full min-w-0 p-4 gap-2 border"):
                    ui.label(f"Q{quarter} across reporting years").classes(
                        "text-lg font-bold text-primary"
                    )
                    viewport_chart(
                        {
                            "tooltip": {"trigger": "axis"},
                            "legend": {"data": ["Revenue ($B)", "Operating margin (%)"], "bottom": 0},
                            "grid": {"left": 52, "right": 54, "top": 24, "bottom": 50},
                            "xAxis": {"type": "category", "data": years},
                            "yAxis": [
                                {"type": "value", "name": "$B"},
                                {"type": "value", "name": "%"},
                            ],
                            "series": [
                                {
                                    "name": "Revenue ($B)",
                                    "type": "bar",
                                    "data": [_metric_value(row, "revenue", 1_000_000_000) for row in points],
                                    "itemStyle": {"color": COLORS["revenue"]},
                                },
                                {
                                    "name": "Operating margin (%)",
                                    "type": "line",
                                    "yAxisIndex": 1,
                                    "connectNulls": False,
                                    "symbolSize": 9,
                                    "data": [_metric_value(row, "operating_margin") for row in points],
                                    "itemStyle": {"color": COLORS["margin"]},
                                },
                            ],
                        },
                        classes="w-full h-72 xl:h-64",
                        aria_label=f"{ticker} fiscal Q{quarter} revenue and operating margin across years",
                    )


def _company_composition_charts(history: list[dict], ticker: str) -> None:
    by_year: dict[str, dict[int, float]] = {}
    for row in history:
        revenue = _metric_value(row, "revenue", 1_000_000_000)
        if revenue is not None:
            by_year.setdefault(row["period_end"][:4], {})[row["fiscal_quarter"]] = revenue
    years = sorted(by_year)
    axis_years = [year if len(by_year[year]) == 4 else f"{year} partial" for year in years]
    chronological = sorted(history, key=lambda item: item["period_end"])
    labels = [f"Q{row['fiscal_quarter']} {row['period_end'][:4]}" for row in chronological]
    with ui.element("section").classes(
        "grid w-full grid-cols-1 gap-4 xl:grid-cols-2"
    ):
        with ui.card().classes("w-full min-w-0 p-4 gap-2 border"):
            ui.label("Quarter contribution by year").classes(
                "text-lg font-bold text-primary"
            )
            viewport_chart(
                {
                    "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                    "legend": {"data": ["Q1", "Q2", "Q3", "Q4"], "bottom": 0},
                    "grid": {"left": 52, "right": 18, "top": 24, "bottom": 54},
                    "xAxis": {"type": "category", "data": axis_years},
                    "yAxis": {"type": "value", "name": "$B"},
                    "series": [
                        {
                            "name": f"Q{quarter}",
                            "type": "bar",
                            "stack": "quarters",
                            "data": [by_year[year].get(quarter) for year in years],
                            "itemStyle": {"color": COMPANY_COLORS[quarter - 1]},
                        }
                        for quarter in range(1, 5)
                    ],
                },
                classes="w-full h-72 xl:h-64",
                aria_label=f"{ticker} annual revenue split into reported fiscal quarters",
            )
        with ui.card().classes("w-full min-w-0 p-4 gap-2 border"):
            ui.label("Diluted share-count trend").classes(
                "text-lg font-bold text-negative"
            )
            viewport_chart(
                {
                    "tooltip": {"trigger": "axis"},
                    "grid": {"left": 58, "right": 18, "top": 24, "bottom": 50},
                    "xAxis": {"type": "category", "data": labels, "axisLabel": {"rotate": 30}},
                    "yAxis": {"type": "value", "name": "Millions", "scale": True},
                    "series": [
                        {
                            "name": "Diluted shares (M)",
                            "type": "line",
                            "connectNulls": False,
                            "symbolSize": 7,
                            "areaStyle": {"opacity": 0.08},
                            "data": [_metric_value(row, "diluted_weighted_average_shares", 1_000_000) for row in chronological],
                            "itemStyle": {"color": COLORS["shares"]},
                        }
                    ],
                },
                classes="w-full h-72 xl:h-64",
                aria_label=f"{ticker} diluted weighted-average share count by quarter",
            )


def _filing_sources(filings: list[dict], *, title: str = "Recent SEC filings") -> None:
    _section_title(title)
    visible = filings[:4]
    with ui.card().classes("w-full p-3 gap-0 border"):
        for index, filing in enumerate(visible):
            if index:
                ui.separator()
            with ui.row().classes("w-full items-center justify-between gap-3 py-2 flex-wrap"):
                ui.label(
                    f"{filing['form']} · period {filing['period_end']} · filed {filing['filed_on']}"
                ).classes("text-sm font-semibold")
                _source_link("Open SEC filing ↗", filing["filing_index_url"])
        if len(filings) > 4:
            with ui.expansion(f"View {len(filings) - 4} older filings", icon="history").classes(
                "w-full"
            ):
                for filing in filings[4:]:
                    with ui.row().classes("w-full items-center justify-between gap-3 py-2 flex-wrap"):
                        ui.label(
                            f"{filing['form']} · {filing['period_end']} · filed {filing['filed_on']}"
                        ).classes("text-sm")
                        _source_link("Open ↗", filing["filing_index_url"])


def _render_company(profile: dict, *, spotlight: bool = False) -> None:
    with ui.row().classes("w-full items-end justify-between gap-3 flex-wrap"):
        with ui.column().classes("gap-0"):
            if spotlight:
                ui.label("Company spotlight").classes("text-sm font-bold text-primary uppercase")
            ui.label(f"{profile['company_name']} · {profile['ticker']}").classes(
                "text-3xl sm:text-4xl font-bold"
            )
            ui.label(profile["business_model"]).classes("text-base font-medium")
        with ui.row().classes("gap-2 flex-wrap"):
            ui.badge("Official SEC data", color="primary").props("outline")
            ui.badge("No ranking", color="grey").props("outline")

    history = sorted(profile["analyses"], key=lambda item: item["period_end"])
    if not history:
        _unavailable_state("No normalized quarterly series is available")
        _filing_sources(profile["filings"])
        return

    latest = history[-1]
    ui.label(
        f"Latest normalized quarter · Q{latest['fiscal_quarter']} · {latest['period_end']}"
    ).classes("text-sm font-bold text-primary")
    _compact_metric_cards(latest)
    _section_title("Quarterly performance")
    _company_overview_charts(history, profile["ticker"])
    _section_title("Compare the same fiscal quarter", "Choose Q1, Q2, Q3, or Q4.")
    _company_quarter_tabs(history, profile["ticker"])
    _section_title("Annual composition and capital")
    _company_composition_charts(history, profile["ticker"])
    _filing_sources(profile["filings"])


def _lens(company: dict, key: str) -> dict | None:
    return next((item for item in company.get("lenses", []) if item["key"] == key), None)


def _latest_history(company: dict) -> dict | None:
    history = company.get("history", [])
    return max(history, key=lambda item: item["period_end"]) if history else None


def _sector_history_value(company: dict, row: dict, key: str) -> float | None:
    if row["period_end"] == company["period_end"]:
        lens = _lens(company, key)
        if lens and lens.get("gate_status") != "cleared":
            return None
    return _metric_value(row, key)


def _sector_snapshot_charts(screen: dict) -> None:
    companies = screen["companies"]
    tickers = [company["ticker"] for company in companies]
    growth = []
    margins = []
    revenues = []
    for company in companies:
        growth_lens = _lens(company, "revenue_growth_yoy")
        growth.append(
            growth_lens.get("value")
            if growth_lens and growth_lens.get("gate_status") == "cleared"
            else None
        )
        latest = _latest_history(company)
        margins.append(_metric_value(latest, "operating_margin") if latest else None)
        revenues.append(_metric_value(latest, "revenue", 1_000_000_000) if latest else None)

    with ui.element("section").classes(
        "grid w-full grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3"
    ):
        with ui.card().classes("w-full min-w-0 p-4 gap-2 border"):
            ui.label("Revenue growth · latest quarter").classes(
                "text-lg font-bold text-primary"
            )
            viewport_chart(
                {
                    "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                    "grid": {"left": 52, "right": 18, "top": 20, "bottom": 40},
                    "xAxis": {"type": "category", "data": tickers},
                    "yAxis": {"type": "value", "name": "%"},
                    "series": [{"name": "Revenue growth YoY", "type": "bar", "data": growth, "itemStyle": {"color": COLORS["growth"]}}],
                },
                classes="w-full h-64",
                aria_label=f"{screen['industry_label']} latest comparable revenue growth by company",
            )
        with ui.card().classes("w-full min-w-0 p-4 gap-2 border"):
            ui.label("Operating margin · latest quarter").classes(
                "text-lg font-bold text-warning"
            )
            viewport_chart(
                {
                    "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
                    "grid": {"left": 52, "right": 18, "top": 20, "bottom": 40},
                    "xAxis": {"type": "category", "data": tickers},
                    "yAxis": {"type": "value", "name": "%"},
                    "series": [{"name": "Operating margin", "type": "bar", "data": margins, "itemStyle": {"color": COLORS["margin"]}}],
                },
                classes="w-full h-64",
                aria_label=f"{screen['industry_label']} latest operating margin by company",
            )
        with ui.card().classes("w-full min-w-0 p-4 gap-2 border lg:col-span-2 2xl:col-span-1"):
            ui.label("Selected-cohort revenue mix").classes(
                "text-lg font-bold text-positive"
            )
            viewport_chart(
                {
                    "tooltip": {"trigger": "item"},
                    "legend": {"orient": "vertical", "right": 0, "top": "middle"},
                    "series": [
                        {
                            "name": "Quarterly revenue ($B)",
                            "type": "pie",
                            "radius": ["42%", "70%"],
                            "center": ["38%", "50%"],
                            "label": {"formatter": "{b}\n{d}%"},
                            "data": [
                                {"name": ticker, "value": revenue, "itemStyle": {"color": COMPANY_COLORS[index]}}
                                for index, (ticker, revenue) in enumerate(zip(tickers, revenues, strict=True))
                                if revenue is not None
                            ],
                        }
                    ],
                },
                classes="w-full h-64",
                aria_label=f"Share of selected {screen['industry_label']} cohort quarterly revenue by company, not market share",
            )
            ui.label("Selected five-company cohort · not market share").classes(
                "text-xs font-semibold"
            )


def _sector_quarter_tabs(screen: dict) -> None:
    companies = screen["companies"]
    available = {
        row["fiscal_quarter"]
        for company in companies
        for row in company.get("history", [])
    }
    if not available:
        _unavailable_state("Multi-year sector history is temporarily unavailable")
        return
    latest_row = max(
        (
            row
            for company in companies
            for row in company.get("history", [])
        ),
        key=lambda item: item["period_end"],
    )
    default_quarter = latest_row["fiscal_quarter"]
    tabs_by_quarter = {}
    with ui.tabs().classes("w-full justify-start text-primary") as tabs:
        for quarter in range(1, 5):
            tabs_by_quarter[quarter] = ui.tab(f"Q{quarter}")
    with ui.tab_panels(tabs, value=tabs_by_quarter[default_quarter]).classes(
        "w-full bg-transparent"
    ):
        for quarter in range(1, 5):
            with ui.tab_panel(tabs_by_quarter[quarter]).classes("w-full p-0 pt-3"):
                years = sorted(
                    {
                        row["period_end"][:4]
                        for company in companies
                        for row in company.get("history", [])
                        if row["fiscal_quarter"] == quarter
                    }
                )
                with ui.element("section").classes(
                    "grid w-full grid-cols-1 gap-4 xl:grid-cols-2"
                ):
                    for metric_key, title, unit, color_key in (
                        ("revenue_growth_yoy", f"Q{quarter} revenue growth across years", "%", "growth"),
                        ("operating_margin", f"Q{quarter} operating margin across years", "%", "margin"),
                    ):
                        with ui.card().classes("w-full min-w-0 p-4 gap-2 border"):
                            ui.label(title).classes("text-lg font-bold text-primary")
                            series = []
                            for index, company in enumerate(companies):
                                points = {
                                    row["period_end"][:4]: _sector_history_value(
                                        company, row, metric_key
                                    )
                                    for row in company.get("history", [])
                                    if row["fiscal_quarter"] == quarter
                                }
                                series.append(
                                    {
                                        "name": company["ticker"],
                                        "type": "line",
                                        "connectNulls": False,
                                        "symbolSize": 7,
                                        "data": [points.get(year) for year in years],
                                        "itemStyle": {"color": COMPANY_COLORS[index]},
                                    }
                                )
                            viewport_chart(
                                {
                                    "tooltip": {"trigger": "axis"},
                                    "legend": {"data": [company["ticker"] for company in companies], "bottom": 0},
                                    "grid": {"left": 52, "right": 18, "top": 24, "bottom": 54},
                                    "xAxis": {"type": "category", "data": years},
                                    "yAxis": {"type": "value", "name": unit},
                                    "series": series,
                                },
                                classes="w-full h-72 xl:h-64",
                                aria_label=f"{screen['industry_label']} fiscal Q{quarter} {metric_key.replace('_', ' ')} by company across years",
                            )


def _sector_sources(screen: dict) -> None:
    _section_title("Source filings")
    with ui.card().classes("w-full p-3 gap-0 border"):
        for index, company in enumerate(screen["companies"]):
            if index:
                ui.separator()
            with ui.row().classes("w-full items-center justify-between gap-3 py-2 flex-wrap"):
                ui.label(
                    f"{company['ticker']} · period {company['period_end']}"
                ).classes("text-sm font-semibold")
                _source_link("Open SEC filing ↗", company["filing_index_url"])


def _render_sector(screen: dict) -> None:
    ui.label(screen["industry_label"]).classes("text-3xl sm:text-4xl font-bold")
    ui.label("Five-company SEC comparison · reported and formula-derived values").classes(
        "text-base font-medium"
    )
    with ui.row().classes("gap-2 flex-wrap"):
        ui.badge("Same reporting period" if screen.get("same_period") else "Fiscal periods shown", color="positive").props("outline")
        ui.badge("No ranking", color="grey").props("outline")
    _section_title("Latest-quarter comparison")
    _sector_snapshot_charts(screen)
    _section_title("Compare the same fiscal quarter", "Choose Q1, Q2, Q3, or Q4.")
    _sector_quarter_tabs(screen)
    _sector_sources(screen)


@ui.page("/research/financials")
@with_layout
def financial_research_index():
    ui.page_title("Financial Performance — Bizqlab")
    ui.add_head_html(
        '<meta name="description" content="SEC-based quarterly company and industry financial comparisons.">'
    )
    directory = load_filing_directory()
    with ui.column().classes("w-full max-w-7xl mx-auto px-4 py-7 sm:px-8 gap-5"):
        ui.label("Financial performance").classes("text-3xl sm:text-4xl font-bold")
        ui.label("Quarterly company trends and five-company industry comparisons from official SEC filings.").classes(
            "text-base font-medium"
        )
        with ui.card().classes("w-full p-4 gap-2 border").style(
            "border-left: 5px solid #2563eb"
        ):
            ui.label("Company spotlight · PayPal").classes("text-xl font-bold text-primary")
            ui.label("Quarterly performance, same-quarter history, cash generation, and share-count trends.").classes(
                "text-sm font-medium"
            )
            ui.link("Open PayPal analysis →", "/research/financials/paypal").classes(
                "text-primary font-semibold no-underline hover:underline"
            )
        if not directory["available"]:
            _unavailable_state("The company directory is temporarily unavailable")
            return
        _section_title("Browse by industry")
        for industry in directory["industries"]:
            with ui.card().classes("w-full p-4 gap-3 border"):
                with ui.row().classes("w-full items-center justify-between gap-3 flex-wrap"):
                    ui.label(industry["label"]).classes("text-xl font-bold text-primary")
                    comparison_path = (
                        "/research/financials/comparisons/payments"
                        if industry["key"] == "payments"
                        else f"/research/financials/sectors/{industry['key']}"
                    )
                    ui.link("Compare all five →", comparison_path).classes(
                        "text-primary font-semibold no-underline hover:underline"
                    )
                with ui.element("section").classes(
                    "grid w-full grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-5"
                ):
                    for company in industry["companies"]:
                        target = (
                            "/research/financials/paypal"
                            if company["ticker"] == "PYPL"
                            else f"/research/financials/company/{company['slug']}"
                        )
                        with ui.card().classes("w-full h-full p-3 gap-1 border"):
                            ui.label(company["ticker"]).classes("text-lg font-bold text-primary")
                            ui.label(company["company_name"]).classes("text-sm font-semibold")
                            ui.label(f"{company['form']} · {company['period_end']}").classes("text-xs")
                            with ui.row().classes("gap-3 flex-wrap mt-1"):
                                ui.link("Analyze →", target).classes(
                                    "text-primary font-semibold no-underline hover:underline"
                                )
                                _source_link("SEC ↗", company["filing_index_url"])


@ui.page("/research/financials/company/{ticker}")
@with_layout
def company_filing_profile(ticker: str):
    profile = load_filing_profile(ticker)
    ui.page_title(f"{ticker.upper()} Financial Performance — Bizqlab")
    with ui.column().classes("w-full max-w-7xl mx-auto px-4 py-7 sm:px-8 gap-5"):
        ui.link("← Financial performance", "/research/financials").classes(
            "text-primary font-semibold no-underline hover:underline"
        )
        if profile is None:
            _unavailable_state()
            return
        _render_company(profile)
        enable_viewport_chart_animations()


@ui.page("/research/financials/paypal")
@with_layout
def paypal_research_page():
    profile = load_filing_profile("PYPL")
    ui.page_title("PayPal Financial Performance — Bizqlab")
    with ui.column().classes("w-full max-w-7xl mx-auto px-4 py-7 sm:px-8 gap-5"):
        ui.link("← Financial performance", "/research/financials").classes(
            "text-primary font-semibold no-underline hover:underline"
        )
        if profile is None:
            _unavailable_state()
            return
        _render_company(profile, spotlight=True)
        enable_viewport_chart_animations()


@ui.page("/research/financials/comparisons/payments")
@with_layout
def payments_comparison_page():
    comparison = load_payments_comparison()
    ui.page_title("Payments Industry Comparison — Bizqlab")
    with ui.column().classes("w-full max-w-7xl mx-auto px-4 py-7 sm:px-8 gap-5"):
        ui.link("← Financial performance", "/research/financials").classes(
            "text-primary font-semibold no-underline hover:underline"
        )
        if not comparison["available"]:
            _unavailable_state()
            return
        comparison["industry_label"] = "Payments and commerce platforms"
        comparison["same_period"] = True
        _render_sector(comparison)
        enable_viewport_chart_animations()


@ui.page("/research/financials/sectors/{industry_key}")
@with_layout
def sector_screen_page(industry_key: str):
    screen = load_sector_screen(industry_key)
    ui.page_title(f"Industry Comparison — {industry_key.replace('_', ' ').title()} — Bizqlab")
    with ui.column().classes("w-full max-w-7xl mx-auto px-4 py-7 sm:px-8 gap-5"):
        ui.link("← Financial performance", "/research/financials").classes(
            "text-primary font-semibold no-underline hover:underline"
        )
        if screen is None:
            _unavailable_state()
            return
        _render_sector(screen)
        enable_viewport_chart_animations()
