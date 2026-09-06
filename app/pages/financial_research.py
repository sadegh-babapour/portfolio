from __future__ import annotations

from nicegui import ui

from app.components.charts import enable_viewport_chart_animations, viewport_chart
from app.components.navbar import with_layout
from app.financial_research.service import find_company_research, load_public_research


def _source_link(label: str, url: str) -> None:
    ui.link(label, url, new_tab=True).classes(
        "text-primary font-semibold no-underline hover:underline"
    )


def _quality_badge(state: str, confidence: str) -> None:
    colors = {
        "reported": "positive",
        "reconciled": "positive",
        "derived": "primary",
        "missing": "warning",
        "blocked": "warning",
    }
    ui.badge(f"{state} · {confidence}", color=colors.get(state, "grey")).props(
        "outline"
    )


def _unavailable_state() -> None:
    with ui.card().classes("w-full p-6 gap-3 border"):
        ui.icon("cloud_off", size="md").classes("text-warning")
        ui.label("Research sheet temporarily unavailable").classes(
            "text-xl font-semibold"
        )
        ui.label(
            "The page does not substitute stale or partial values when its reviewed "
            "publication snapshot fails validation. Direct SEC filing search remains available."
        ).classes("text-sm text-grey-7 leading-relaxed")
        _source_link("Search SEC EDGAR", "https://www.sec.gov/edgar/search/")


def _metric_cards(sheet: dict) -> None:
    with ui.element("section").classes(
        "grid w-full grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3"
    ).props('aria-label="Latest reported and derived measures"'):
        for metric in sheet["metrics"]:
            with ui.card().classes("w-full h-full p-5 gap-2 border"):
                ui.label(metric["label"]).classes("text-sm text-grey-7")
                ui.label(metric["display_value"]).classes("text-3xl font-semibold")
                ui.label(metric.get("change", "")).classes("text-sm font-medium")
                with ui.row().classes("w-full items-center justify-between gap-2"):
                    _quality_badge(metric["state"], metric["confidence"])
                    _source_link("SEC evidence ↗", metric["source_url"])


def _operating_history_chart(sheet: dict) -> None:
    history = sheet["quarter_history"]
    viewport_chart(
        {
            "tooltip": {"trigger": "axis"},
            "grid": {"left": 54, "right": 18, "top": 28, "bottom": 52},
            "xAxis": {"type": "category", "data": [row["period"] for row in history]},
            "yAxis": {"type": "value", "name": "$B", "min": 0},
            "series": [
                {
                    "name": "Revenue ($B)",
                    "type": "line",
                    "smooth": True,
                    "symbolSize": 7,
                    "areaStyle": {"opacity": 0.12},
                    "data": [row["revenue_billions"] for row in history],
                    "itemStyle": {"color": "#2563eb"},
                }
            ],
        },
        classes="w-full h-80",
        aria_label="PayPal quarterly revenue from Q1 2022 through Q2 2026",
    )
    ui.label(
        "Quarterly revenue spans $6.483B in Q1 2022 to $8.682B in Q2 2026. "
        "The complete series is shown so seasonal and quarter-to-quarter movement "
        "is not hidden by a two-point comparison."
    ).classes("text-sm text-grey-7 leading-relaxed")


def _margin_history_chart(sheet: dict) -> None:
    history = sheet["quarter_history"]
    viewport_chart(
        {
            "tooltip": {"trigger": "axis"},
            "legend": {"data": ["Operating margin", "Net margin"], "bottom": 0},
            "grid": {"left": 54, "right": 18, "top": 28, "bottom": 58},
            "xAxis": {"type": "category", "data": [row["period"] for row in history]},
            "yAxis": {"type": "value", "name": "%"},
            "series": [
                {
                    "name": "Operating margin",
                    "type": "line",
                    "data": [row["operating_margin_percent"] for row in history],
                    "itemStyle": {"color": "#d97706"},
                },
                {
                    "name": "Net margin",
                    "type": "line",
                    "data": [row["net_margin_percent"] for row in history],
                    "itemStyle": {"color": "#7c3aed"},
                },
            ],
        },
        classes="w-full h-80",
        aria_label="PayPal quarterly operating and net margins from Q1 2022 through Q2 2026",
    )
    ui.label(
        "Margins are volatile rather than steadily improving. Q2 2026 operating "
        "margin was 16.44% and net margin was 12.72%; the Q2 2022 net loss remains "
        "visible instead of being smoothed away."
    ).classes("text-sm text-grey-7 leading-relaxed")


def _cash_history_chart(sheet: dict) -> None:
    history = sheet["quarter_history"]
    viewport_chart(
        {
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "grid": {"left": 54, "right": 18, "top": 28, "bottom": 52},
            "xAxis": {"type": "category", "data": [row["period"] for row in history]},
            "yAxis": {"type": "value", "name": "$B"},
            "series": [
                {
                    "name": "Simplified free cash flow",
                    "type": "bar",
                    "data": [
                        row["simplified_free_cash_flow_billions"] for row in history
                    ],
                    "itemStyle": {"color": "#0f766e"},
                }
            ],
        },
        classes="w-full h-80",
        aria_label="PayPal quarterly simplified free cash flow from Q1 2022 through Q2 2026",
    )
    ui.label(
        "Simplified free cash flow varies substantially: Q2 2023 was negative "
        "$350M, while Q4 2023 reached $2.469B. Q2 2026 was $1.775B."
    ).classes("text-sm text-grey-7 leading-relaxed")


def _capital_history_chart(sheet: dict) -> None:
    history = sheet["quarter_history"]
    viewport_chart(
        {
            "tooltip": {"trigger": "axis"},
            "legend": {"data": ["Working capital ($B)", "Diluted shares (M)"], "bottom": 0},
            "grid": {"left": 54, "right": 62, "top": 28, "bottom": 58},
            "xAxis": {"type": "category", "data": [row["period"] for row in history]},
            "yAxis": [
                {"type": "value", "name": "$B"},
                {"type": "value", "name": "M", "min": 0},
            ],
            "series": [
                {
                    "name": "Working capital ($B)",
                    "type": "line",
                    "data": [row["working_capital_billions"] for row in history],
                    "itemStyle": {"color": "#2563eb"},
                },
                {
                    "name": "Diluted shares (M)",
                    "type": "line",
                    "yAxisIndex": 1,
                    "data": [
                        row["diluted_weighted_shares_millions"] for row in history
                    ],
                    "itemStyle": {"color": "#be123c"},
                },
            ],
        },
        classes="w-full h-80",
        aria_label="PayPal quarterly working capital and diluted weighted-average shares from Q1 2022 through Q2 2026",
    )
    ui.label(
        "Working capital fluctuated from $8.415B to $13.940B across the displayed "
        "period, while diluted weighted-average shares declined from 1.172B to 882M. "
        "The chart describes the record; it does not assume that every reduction created value."
    ).classes("text-sm text-grey-7 leading-relaxed")


def _quarter_history_table(sheet: dict) -> None:
    rows = [
        {
            "period": row["period"],
            "revenue": f"${row['revenue_billions']:.3f}B",
            "operating_margin": f"{row['operating_margin_percent']:.2f}%",
            "net_margin": f"{row['net_margin_percent']:.2f}%",
            "free_cash_flow": f"${row['simplified_free_cash_flow_billions']:.3f}B",
            "working_capital": f"${row['working_capital_billions']:.3f}B",
            "diluted_shares": f"{row['diluted_weighted_shares_millions']:.1f}M",
        }
        for row in sheet["quarter_history"]
    ]
    with ui.expansion("View all 18 quarterly values", icon="table_view").classes(
        "w-full"
    ):
        ui.table(
            columns=[
                {"name": "period", "label": "Quarter", "field": "period", "align": "left"},
                {"name": "revenue", "label": "Revenue", "field": "revenue", "align": "right"},
                {"name": "operating_margin", "label": "Op. margin", "field": "operating_margin", "align": "right"},
                {"name": "net_margin", "label": "Net margin", "field": "net_margin", "align": "right"},
                {"name": "free_cash_flow", "label": "Simplified FCF", "field": "free_cash_flow", "align": "right"},
                {"name": "working_capital", "label": "Working capital", "field": "working_capital", "align": "right"},
                {"name": "diluted_shares", "label": "Diluted shares", "field": "diluted_shares", "align": "right"},
            ],
            rows=rows,
            row_key="period",
            pagination={"rowsPerPage": 0},
        ).classes("w-full").props("flat bordered dense wrap-cells")
        with ui.row().classes("gap-3 flex-wrap p-2"):
            for row in sheet["quarter_history"]:
                _source_link(f"{row['period']} evidence", row["source_url"])


def _cash_chart(sheet: dict) -> None:
    bridge = sheet["charts"]["cash_bridge"]
    viewport_chart(
        {
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "grid": {"left": 58, "right": 18, "top": 28, "bottom": 72},
            "xAxis": {"type": "category", "data": bridge["labels"], "axisLabel": {"interval": 0, "rotate": 14}},
            "yAxis": {"type": "value", "name": "$B"},
            "series": [
                {
                    "name": "$B",
                    "type": "bar",
                    "data": bridge["billions"],
                    "itemStyle": {
                        "color": "#0f766e",
                    },
                }
            ],
        },
        classes="w-full h-80",
        aria_label="PayPal Q2 2026 operating cash flow, capital expenditure, and simplified free cash flow",
    )
    ui.label(
        "$1.983B of operating cash flow less $208M of capital expenditure yields "
        "$1.775B of simplified free cash flow. This is a transparent formula, not "
        "PayPal's non-GAAP free-cash-flow measure."
    ).classes("text-sm text-grey-7 leading-relaxed")


def _evidence_column(title: str, icon: str, items: list[dict], tone: str) -> None:
    with ui.card().classes(f"w-full h-full p-5 gap-4 border {tone}"):
        with ui.row().classes("items-center gap-2"):
            ui.icon(icon, size="sm")
            ui.label(title).classes("text-xl font-semibold")
        for item in items:
            with ui.column().classes("w-full gap-1"):
                ui.label(item["title"]).classes("font-semibold")
                ui.label(item["statement"]).classes("text-sm leading-relaxed")
                ui.label(item["kind"]).classes("text-xs text-grey-7")
                _source_link("Open supporting filing", item["source_url"])


def _historical_events(sheet: dict) -> None:
    ui.label("Historical filings and material structures").classes(
        "text-2xl font-semibold mt-3"
    )
    ui.label(
        "Older events are dated and separated from the latest-quarter explanation. "
        "They remain here only when their structure or unresolved obligations may "
        "matter to longer-term research."
    ).classes("text-sm text-grey-7 leading-relaxed max-w-5xl")
    for event in sheet["historical_events"]:
        with ui.card().classes("w-full p-5 sm:p-6 gap-4 border"):
            with ui.row().classes("w-full items-start justify-between gap-3 flex-wrap"):
                with ui.column().classes("gap-1"):
                    ui.label(event["title"]).classes("text-xl font-semibold")
                    ui.label(event["date"]).classes("text-sm text-grey-7")
                ui.badge("historical filing", color="grey").props("outline")
            ui.label(event["summary"]).classes("text-sm leading-relaxed")
            with ui.card().classes("w-full p-4 gap-2 border border-dashed"):
                ui.label("Why it remains on the research sheet").classes("font-semibold")
                ui.label(event["current_relevance"]).classes(
                    "text-sm text-grey-7 leading-relaxed"
                )
            _source_link("Open transaction announcement", event["source_url"])
            ui.table(
                columns=[
                    {"name": "entity", "label": "Entity", "field": "entity", "align": "left"},
                    {"name": "role", "label": "Documented role", "field": "role", "align": "left"},
                ],
                rows=event["relationships"],
                row_key="entity",
            ).classes("w-full").props("flat bordered wrap-cells")
            with ui.expansion("Evidence links and unresolved questions", icon="search").classes(
                "w-full"
            ):
                with ui.column().classes("w-full gap-2 p-2"):
                    for relationship in event["relationships"]:
                        _source_link(
                            f"Evidence: {relationship['entity']}",
                            relationship["source_url"],
                        )
                    for question in event["open_questions"]:
                        with ui.row().classes("items-start gap-2 no-wrap"):
                            ui.icon("help_outline", size="xs").classes("mt-1 text-warning")
                            ui.label(question).classes("text-sm leading-relaxed")


def _research_sheet(sheet: dict) -> None:
    with ui.column().classes("w-full gap-2"):
        with ui.row().classes("w-full items-start justify-between gap-4 flex-wrap"):
            with ui.column().classes("gap-1"):
                ui.label(f"{sheet['company_name']} · {sheet['ticker']}").classes(
                    "text-4xl sm:text-5xl font-bold"
                )
                ui.label(
                    f"{sheet['form']} · period ended {sheet['period_end']} · "
                    f"filed {sheet['filed_on']}"
                ).classes("text-sm text-grey-7")
            with ui.row().classes("gap-2 flex-wrap"):
                ui.badge("SEC evidence only", color="primary").props("outline")
                ui.badge("No price target", color="grey").props("outline")
        ui.label(sheet["headline"]).classes("text-2xl font-semibold mt-2")
        ui.label(sheet["summary"]).classes(
            "text-base sm:text-lg text-grey-7 leading-relaxed max-w-5xl"
        )
        with ui.row().classes("gap-4 flex-wrap"):
            _source_link("Open filing index", sheet["filing_index_url"])
            _source_link("Read the complete 10-Q", sheet["primary_document_url"])

    ui.label("Latest quarter at a glance").classes("text-2xl font-semibold mt-3")
    _metric_cards(sheet)

    ui.label("Latest-quarter cash mechanics").classes("text-2xl font-semibold mt-3")
    with ui.card().classes("w-full min-w-0 p-5 gap-3"):
        ui.label("Q2 2026 cash bridge").classes("text-xl font-semibold")
        _cash_chart(sheet)

    ui.label("Multi-year quarterly record").classes("text-2xl font-semibold mt-3")
    ui.label(
        "All 18 normalized quarters from Q1 2022 through Q2 2026 are shown. "
        "Hover or tap a point for the underlying quarter."
    ).classes("text-sm text-grey-7")
    with ui.element("section").classes(
        "grid w-full grid-cols-1 gap-5 xl:grid-cols-2"
    ):
        with ui.card().classes("w-full min-w-0 p-5 gap-3"):
            ui.label("Quarterly revenue").classes("text-xl font-semibold")
            _operating_history_chart(sheet)
        with ui.card().classes("w-full min-w-0 p-5 gap-3"):
            ui.label("Profitability range").classes("text-xl font-semibold")
            _margin_history_chart(sheet)
        with ui.card().classes("w-full min-w-0 p-5 gap-3"):
            ui.label("Cash generation history").classes("text-xl font-semibold")
            _cash_history_chart(sheet)
        with ui.card().classes("w-full min-w-0 p-5 gap-3"):
            ui.label("Financial position and share count").classes(
                "text-xl font-semibold"
            )
            _capital_history_chart(sheet)
    _quarter_history_table(sheet)

    ui.label("Current-quarter evidence in tension").classes(
        "text-2xl font-semibold mt-3"
    )
    ui.label(
        "Supporting and contrary observations are kept separate so a favorable fact "
        "cannot silently cancel an unfavorable one."
    ).classes("text-sm text-grey-7")
    with ui.element("section").classes(
        "grid w-full grid-cols-1 gap-5 lg:grid-cols-2"
    ):
        _evidence_column(
            "Supporting evidence",
            "trending_up",
            sheet["supporting_evidence"],
            "research-supporting",
        )
        _evidence_column(
            "Contrary evidence",
            "warning_amber",
            sheet["contrary_evidence"],
            "research-contrary",
        )

    with ui.card().classes("w-full p-5 gap-3 border border-dashed"):
        ui.label("What remains unknown about the latest quarter").classes(
            "text-xl font-semibold"
        )
        for item in sheet["unknowns"]:
            with ui.column().classes("gap-1"):
                ui.label(item["question"]).classes("font-semibold")
                ui.label(item["reason"]).classes(
                    "text-sm text-grey-7 leading-relaxed"
                )

    _historical_events(sheet)

    with ui.expansion("Method, quality, and limitations", icon="fact_check").classes(
        "w-full"
    ):
        with ui.column().classes("w-full gap-2 p-3"):
            for note in sheet["quality_notes"]:
                with ui.row().classes("items-start gap-2 no-wrap"):
                    ui.icon("arrow_right", size="xs").classes("mt-1 text-primary")
                    ui.label(note).classes("text-sm leading-relaxed")
            ui.label(
                "The page helps prioritize deeper research. It is not personalized "
                "financial advice or an instruction to trade."
            ).classes("text-sm font-semibold")


@ui.page("/research/financials")
@with_layout
def financial_research_index():
    ui.page_title("Recently Reported Companies — Bizqlab")
    ui.add_head_html(
        '<meta name="description" content="Evidence-backed SEC filing research with transparent calculations, contrary evidence, and unresolved questions.">'
    )
    research = load_public_research()
    with ui.column().classes("w-full max-w-7xl mx-auto px-4 py-8 sm:px-8 gap-6"):
        ui.label("Recently reported").classes("text-4xl sm:text-5xl font-bold")
        ui.label(
            "Reviewed SEC filing research designed to reveal what changed, what supports "
            "the interpretation, what argues against it, and what still needs investigation."
        ).classes("text-lg text-grey-7 leading-relaxed max-w-4xl")
        if not research["available"]:
            _unavailable_state()
            return
        for company in research["companies"]:
            with ui.card().classes("w-full p-5 sm:p-6 gap-3 border"):
                with ui.row().classes("w-full items-start justify-between gap-3 flex-wrap"):
                    with ui.column().classes("gap-1"):
                        ui.label(
                            f"{company['company_name']} · {company['ticker']}"
                        ).classes("text-2xl font-semibold")
                        ui.label(
                            f"{company['form']} filed {company['filed_on']} · "
                            f"period ended {company['period_end']}"
                        ).classes("text-sm text-grey-7")
                    ui.badge("reviewed", color="positive").props("outline")
                ui.label(company["headline"]).classes("text-lg font-semibold")
                ui.label(company["summary"]).classes(
                    "text-sm text-grey-7 leading-relaxed max-w-5xl"
                )
                ui.link(
                    "Open PayPal research sheet →", "/research/financials/paypal"
                ).classes("text-primary font-semibold no-underline hover:underline")


@ui.page("/research/financials/paypal")
@with_layout
def paypal_research_page():
    ui.page_title("PayPal Q2 2026 Research Sheet — Bizqlab")
    ui.add_head_html(
        '<meta name="description" content="PayPal Q2 2026 SEC filing analysis with normalized facts, transparent calculations, evidence, risks, and open questions.">'
    )
    sheet = find_company_research("paypal")
    with ui.column().classes("w-full max-w-7xl mx-auto px-4 py-8 sm:px-8 gap-7"):
        ui.link("← Recently reported", "/research/financials").classes(
            "text-primary font-semibold no-underline hover:underline"
        )
        if sheet is None:
            _unavailable_state()
            return
        _research_sheet(sheet)
        enable_viewport_chart_animations()
