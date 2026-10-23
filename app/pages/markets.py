from __future__ import annotations

import hashlib
from datetime import date
from html import escape
from pathlib import Path

from nicegui import ui

from app.components.charts import (
    AMBER,
    AXIS,
    BLUE,
    CYAN,
    GRID,
    LEGEND as CHART_LEGEND,
    MUTED,
    RED,
    TOOLTIP,
    VIOLET,
    enable_viewport_chart_animations,
    viewport_chart,
)
from app.components.navbar import with_layout
from app.markets.service import load_rates


THEME_STYLESHEET = Path(__file__).resolve().parents[2] / "static" / "bizqlab-theme.css"
THEME_STYLESHEET_URL = (
    "/static/bizqlab-theme.css?v="
    + hashlib.sha256(THEME_STYLESHEET.read_bytes()).hexdigest()[:12]
)

LEGEND = {"top": 0, **CHART_LEGEND}
PERCENT = "v => v == null ? '–' : v.toFixed(2) + '%'"
BPS = "v => v == null ? '–' : Math.round(v) + ' bps'"

KPIS = (
    ("policy_rate", "Policy rate", "rate"),
    ("corra", "CORRA overnight", "rate"),
    ("gov_2y", "2-year yield", "rate"),
    ("gov_10y", "10-year yield", "rate"),
    ("spread_10y_2y_bps", "10Y − 2Y spread", "bps"),
    ("usd_cad", "USD/CAD", "fx"),
)


def _fmt(kind: str, value: float) -> str:
    if kind == "rate":
        return f"{value:.2f}%"
    if kind == "bps":
        return f"{value:,.0f} bps"
    return f"{value:.4f}"


def _fmt_change(measure: str, change: float | None) -> tuple[str, str]:
    """The change label and its class: amber for up, blue for down. Not good or bad."""
    if change is None:
        return "no data a year ago", ""
    if change == 0:
        return "unchanged on the year", ""
    unit = "%" if measure == "usd_cad" else " bps"
    number = f"{change:+.1f}" if measure == "usd_cad" else f"{change:+,.0f}"
    arrow = "▲" if change > 0 else "▼"
    return f"{arrow} {number.replace('-', '−')}{unit} on the year", "is-up" if change > 0 else "is-down"


def _day(value: date) -> str:
    return f"{value:%b} {value.day}, {value.year}"


def _five_years_before(last: date) -> str:
    return last.replace(year=last.year - 5, day=min(last.day, 28)).isoformat()


def _points(rows: list[dict], key: str, where=None) -> list[list]:
    return [[r["date"].isoformat(), r[key]] for r in rows if r[key] is not None and (where is None or where(r))]


def _zoom(start: str) -> list[dict]:
    return [
        {"type": "inside", "startValue": start},
        {
            "type": "slider", "startValue": start, "height": 22, "bottom": 6,
            "borderColor": GRID, "fillerColor": "rgba(47, 123, 245, 0.14)",
            "dataBackground": {"lineStyle": {"color": MUTED}, "areaStyle": {"color": GRID}},
            "handleStyle": {"color": BLUE, "borderColor": BLUE},
            "moveHandleStyle": {"color": BLUE}, "textStyle": {"color": MUTED},
        },
    ]


def _line(name: str, data: list, color: str, **extra) -> dict:
    return {
        "name": name, "type": "line", "data": data, "showSymbol": False,
        "lineStyle": {"width": 2, "color": color}, "itemStyle": {"color": color}, **extra,
    }


def _spark(points: list[list], color: str) -> None:
    ui.echart({
        "animation": False,
        "grid": {"left": 0, "right": 0, "top": 6, "bottom": 3},
        "xAxis": {"type": "time", "show": False},
        "yAxis": {"type": "value", "show": False, "scale": True},
        "series": [_line("", points, color, areaStyle={"color": {
            "type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
            "colorStops": [{"offset": 0, "color": color + "55"}, {"offset": 1, "color": color + "00"}],
        }})],
    }).classes("bq-spark").props('aria-hidden="true"')


def _card(title: str, note: str, options: dict, *, wide: bool = False, tall: bool = False) -> None:
    with ui.element("section").classes("bq-card" + (" is-wide" if wide else "")):
        ui.html(f"<h3>{escape(title)}</h3><p class='bq-note'>{escape(note)}</p>")
        viewport_chart(options, classes="bq-chart" + (" is-tall" if tall else ""), aria_label=title)


def _hero(data: dict | None) -> None:
    with ui.element("header").classes("bq-hero"):
        with ui.element("div").classes("bq-wrap"):
            if data is None:
                ui.html(
                    "<p class='bq-eyebrow'>Bizqlab data lab · Bank of Canada</p>"
                    "<h1>Canada rates</h1>"
                    "<p class='bq-lede'>Interest rates, government bond yields and the Canadian "
                    "dollar, loaded daily from the Bank of Canada and modelled with dbt.</p>"
                )
                return
            latest = data["latest"]
            policy = latest["policy_rate"]
            spread = latest.get("spread_10y_2y_bps", {}).get("value")
            change = policy["change_1y"]
            policy_change = (
                "" if change is None else ", unchanged from a year ago" if change == 0
                else f", {'up' if change > 0 else 'down'} {abs(change):,.0f} bps from a year ago"
            )
            shape = data["curve_shape"]
            slope = {"upward": "slopes upward", "inverted": "is inverted", "flat": "is flat"}.get(shape, "")
            spread_text = (
                f" The 10-year bond yields <b>{escape(_fmt('bps', spread))}</b> more than the 2-year, "
                f"so the yield curve {slope}." if spread is not None else ""
            )
            load = data.get("last_load") or {}
            loaded = load.get("finished_at")
            ui.html(
                "<p class='bq-eyebrow'>Bizqlab data lab · Bank of Canada</p>"
                "<h1>Canada rates</h1>"
                f"<p class='bq-lede'>The Bank of Canada's policy rate is "
                f"<b>{escape(_fmt('rate', policy['value']))}</b>"
                f"{escape(policy_change)}.{spread_text}</p>"
                "<div class='bq-chips'>"
                f"<span class='bq-chip'><span class='bq-dot{' is-warn' if shape == 'inverted' else ''}'></span>"
                f"Curve {escape(shape or 'unknown')}</span>"
                f"<span class='bq-chip'>Data to {escape(_day(data['last_date']))}</span>"
                + (f"<span class='bq-chip'>Loaded {escape(_day(loaded.date()))}</span>" if loaded else "")
                + "</div>"
            )


def _kpis(data: dict) -> None:
    colors = (AMBER, CYAN, BLUE, VIOLET, BLUE, CYAN)
    with ui.element("section").classes("bq-kpis").props('aria-label="Latest values"'):
        for (measure, label, kind), color in zip(KPIS, colors):
            item = data["latest"].get(measure)
            if not item:
                continue
            change, change_class = _fmt_change(measure, item["change_1y"])
            with ui.element("article").classes("bq-kpi"):
                ui.html(
                    f"<div class='bq-label'>{escape(label)}</div>"
                    f"<div class='bq-value'>{escape(_fmt(kind, item['value']))}</div>"
                    f"<div class='bq-delta {change_class}'>{escape(change)}</div>"
                ).classes("bq-kpi-body")
                _spark(item["spark"], color)


def _history(data: dict) -> None:
    rows = data["rows"]
    start = _five_years_before(data["last_date"])
    business = lambda r: r["gov_10y"] is not None  # noqa: E731 - yields are business days only
    spread = _points(rows, "spread_10y_2y_bps")

    with ui.element("section").classes("bq-section"):
        ui.html(
            "<h2>Rates and yields</h2>"
            "<p>Drag the slider under a chart to change its period; it opens on the last five years.</p>"
        ).classes("bq-section-head")
        with ui.element("div").classes("bq-grid"):
            _card(
                "Policy rate and Government of Canada bond yields",
                "Percent. Bond yields move ahead of the policy rate because they price in where "
                "markets expect it to go.",
                {
                    "legend": LEGEND,
                    "tooltip": {**TOOLTIP, "trigger": "axis", ":valueFormatter": PERCENT},
                    "grid": {"left": 44, "right": 16, "top": 36, "bottom": 56},
                    "xAxis": {"type": "time", **AXIS, "splitLine": {"show": False}},
                    "yAxis": {"type": "value", "scale": True, **AXIS,
                              "axisLabel": {"color": MUTED, ":formatter": "v => v + '%'"}},
                    "dataZoom": _zoom(start),
                    "series": [
                        _line("Policy rate", _points(rows, "policy_rate", business), AMBER, step="end",
                              lineStyle={"width": 2.5, "color": AMBER}),
                        _line("2-year", _points(rows, "gov_2y"), BLUE),
                        _line("5-year", _points(rows, "gov_5y"), CYAN),
                        _line("10-year", _points(rows, "gov_10y"), VIOLET),
                    ],
                },
                wide=True, tall=True,
            )
            _card(
                "Yield curve slope (10-year minus 2-year)",
                "Basis points (1 bp = 0.01%). Red where the curve is inverted, which has often come "
                "before recessions.",
                {
                    "tooltip": {**TOOLTIP, "trigger": "axis", ":valueFormatter": BPS},
                    "grid": {"left": 44, "right": 16, "top": 16, "bottom": 56},
                    "xAxis": {"type": "time", **AXIS, "splitLine": {"show": False}},
                    "yAxis": {"type": "value", **AXIS},
                    "dataZoom": _zoom(start),
                    "series": [
                        _line("10Y − 2Y", spread, BLUE,
                              markLine={"silent": True, "symbol": "none", "data": [{"yAxis": 0}],
                                        "lineStyle": {"color": MUTED, "type": "dashed"},
                                        "label": {"show": False}}),
                        # The inverted stretch, shaded: the spread where it is below zero.
                        {"name": "Inverted", "type": "line", "showSymbol": False, "silent": True,
                         "tooltip": {"show": False}, "lineStyle": {"width": 0},
                         "data": [[d, min(v, 0)] for d, v in spread],
                         "areaStyle": {"color": RED, "opacity": 0.3}},
                    ],
                },
            )
            curve = data["curve"]
            dates = data["curve_dates"]
            if curve:
                _card(
                    "Yield curve, now and a year earlier",
                    f"Percent by maturity, {_day(dates['now'])} against {_day(dates['year_ago'])}. "
                    "Overnight is the policy rate.",
                    {
                        "legend": LEGEND,
                        "tooltip": {**TOOLTIP, "trigger": "axis", ":valueFormatter": PERCENT},
                        "grid": {"left": 52, "right": 28, "top": 44, "bottom": 28},
                        "xAxis": {"type": "category", "boundaryGap": False,
                                  "data": [c["tenor"] for c in curve], **AXIS, "splitLine": {"show": False}},
                        "yAxis": {"type": "value", "scale": True, **AXIS,
                                  "axisLabel": {"color": MUTED, ":formatter": "v => v + '%'"}},
                        "series": [
                            _line(_day(dates["now"]), [c["now"] for c in curve], BLUE, showSymbol=True,
                                  symbolSize=8, label={"show": True, "position": "top", "color": BLUE,
                                                       ":formatter": "p => p.value.toFixed(2) + '%'"}),
                            _line(_day(dates["year_ago"]), [c["year_ago"] for c in curve], MUTED,
                                  showSymbol=True, symbolSize=6,
                                  lineStyle={"width": 2, "color": MUTED, "type": "dashed"}),
                        ],
                    },
                )


def _policy(data: dict) -> None:
    rows = data["rows"]
    decisions = data["decisions"]
    corra_gap = [
        [r["date"].isoformat(), round((r["corra"] - r["policy_rate"]) * 100)]
        for r in rows if r["corra"] is not None and r["policy_rate"] is not None
    ]
    with ui.element("section").classes("bq-section"):
        ui.html(
            "<h2>Policy decisions</h2>"
            "<p>Every change to the policy rate since 2015, and how closely the overnight market "
            "follows it.</p>"
        ).classes("bq-section-head")
        with ui.element("div").classes("bq-grid"):
            if decisions:
                _card(
                    "Each rate change",
                    "Basis points per decision. Amber is a hike, blue a cut.",
                    {
                        "tooltip": {**TOOLTIP, "trigger": "axis", ":valueFormatter": "v => (v > 0 ? '+' : '') + v + ' bps'"},
                        "grid": {"left": 44, "right": 16, "top": 16, "bottom": 28},
                        "xAxis": {"type": "category", "data": [d["date"].isoformat() for d in decisions], **AXIS,
                                  "axisLabel": {"color": MUTED, ":formatter": "v => v.slice(0, 4)"},
                                  "splitLine": {"show": False}},
                        "yAxis": {"type": "value", **AXIS},
                        "series": [{
                            "name": "Change", "type": "bar", "barMaxWidth": 18,
                            "data": [{"value": d["change_bps"], "itemStyle": {
                                "color": AMBER if d["change_bps"] > 0 else BLUE,
                                "borderRadius": [4, 4, 0, 0] if d["change_bps"] > 0 else [0, 0, 4, 4]}}
                                for d in decisions],
                        }],
                    },
                )
            _card(
                "CORRA minus the policy rate",
                "Basis points. Near zero means overnight lending trades at the Bank's target; "
                "spikes show funding stress.",
                {
                    "tooltip": {**TOOLTIP, "trigger": "axis", ":valueFormatter": BPS},
                    "grid": {"left": 44, "right": 16, "top": 16, "bottom": 56},
                    "xAxis": {"type": "time", **AXIS, "splitLine": {"show": False}},
                    "yAxis": {"type": "value", **AXIS},
                    "dataZoom": _zoom(_five_years_before(data["last_date"])),
                    "series": [_line("CORRA − policy", corra_gap, CYAN)],
                },
            )
            if decisions:
                with ui.element("section").classes("bq-card is-wide"):
                    body = "".join(
                        f"<tr><td>{escape(_day(d['date']))}</td>"
                        f"<td class='num {'bq-hike' if d['change_bps'] > 0 else 'bq-cut'}'>"
                        f"{'+' if d['change_bps'] > 0 else '−'}{abs(d['change_bps'])} bps</td>"
                        f"<td class='num'>{escape(_fmt('rate', d['rate']))}</td></tr>"
                        for d in reversed(decisions)
                    )
                    ui.html(
                        "<h3>Decision log</h3><p class='bq-note'>Newest first.</p>"
                        "<div class='bq-table-wrap'><table class='bq-table'>"
                        "<thead><tr><th>Effective</th><th class='num'>Change</th>"
                        "<th class='num'>New rate</th></tr></thead>"
                        f"<tbody>{body}</tbody></table></div>"
                    )


def _currency(data: dict) -> None:
    points = _points(data["rows"], "usd_cad")
    if not points:
        return
    with ui.element("section").classes("bq-section"):
        ui.html("<h2>Canadian dollar</h2>").classes("bq-section-head")
        with ui.element("div").classes("bq-grid"):
            _card(
                "US dollar in Canadian dollars",
                "CAD per USD. Higher means a weaker Canadian dollar.",
                {
                    "tooltip": {**TOOLTIP, "trigger": "axis", ":valueFormatter": "v => v.toFixed(4)"},
                    "grid": {"left": 48, "right": 16, "top": 16, "bottom": 56},
                    "xAxis": {"type": "time", **AXIS, "splitLine": {"show": False}},
                    "yAxis": {"type": "value", "scale": True, **AXIS},
                    "dataZoom": _zoom(_five_years_before(data["last_date"])),
                    "series": [_line("USD/CAD", points, BLUE, areaStyle={"color": {
                        "type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1,
                        "colorStops": [{"offset": 0, "color": "rgba(47, 123, 245, 0.28)"},
                                       {"offset": 1, "color": "rgba(47, 123, 245, 0)"}],
                    }})],
                },
                wide=True,
            )


def _pipeline(data: dict) -> None:
    load = data.get("last_load") or {}
    loaded = load.get("finished_at")
    load_line = (
        f"Last load {escape(_day(loaded.date()))}: {escape(str(load.get('status')))}, "
        f"{load.get('rows_inserted') or 0} new and {load.get('rows_updated') or 0} revised rows."
        if loaded else "No finished load recorded yet."
    )
    with ui.element("section").classes("bq-section"):
        ui.html(
            "<h2>How this page is built</h2>"
            "<p>A small version of what a bank's data team runs: extract, keep the raw data, "
            "model it in SQL, test it, then publish one table for reporting.</p>"
        ).classes("bq-section-head")
        ui.html(
            "<div class='bq-flow'>"
            "<div class='bq-step'><div class='bq-step-title'>Extract</div>"
            "<p>Python reads six series from the Bank of Canada Valet API.</p></div>"
            "<div class='bq-step'><div class='bq-step-title'>Raw</div>"
            f"<p>Stored exactly as published in <code>raw</code>. {load_line}</p></div>"
            "<div class='bq-step'><div class='bq-step-title'>Model and test</div>"
            "<p>dbt cleans and types the data, then checks keys, ranges and freshness.</p></div>"
            "<div class='bq-step'><div class='bq-step-title'>Publish</div>"
            f"<p><code>marts.mart_canada_rates_daily</code>: {len(data['rows']):,} days from "
            f"{escape(_day(data['first_date']))}.</p></div>"
            "</div>"
        )


@ui.page("/markets")
@with_layout
def markets_page():
    ui.page_title("Canada Rates · Bizqlab")
    ui.add_head_html(f'<link rel="stylesheet" href="{THEME_STYLESHEET_URL}">')
    data = load_rates()
    available = data.get("available")

    with ui.element("div").classes("bq-page"):
        _hero(data if available else None)
        with ui.element("div").classes("bq-wrap"):
            if not available:
                ui.html(
                    "<div class='bq-empty' style='margin-top:-56px;position:relative'>"
                    "The rates data isn't published here yet. It arrives with the reporting "
                    "database in the next stage of the data platform.</div>"
                )
            else:
                _kpis(data)
                _history(data)
                _policy(data)
                _currency(data)
                _pipeline(data)
            ui.html(
                "<p class='bq-foot'>Source: Bank of Canada Valet API. Rates are as published; "
                "the Bank's terms of use apply.</p>"
            )
    enable_viewport_chart_animations()
