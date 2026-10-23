"""Shared ECharts helpers: the chart palette and a chart that animates once it scrolls into view.
"""
from __future__ import annotations

from nicegui import ui


# Chart colours: the logo palette in static/site.css, as mid-tones that read on both
# the light and the dark theme (ECharts can't read CSS variables).
BLUE = "#2f7bf5"
AMBER = "#f2a93b"
CYAN = "#22b8cf"
VIOLET = "#8e7cf0"
RED = "#e5534b"
MUTED = "#8a99b8"
GRID = "rgba(138, 153, 184, 0.22)"
PALETTE = [BLUE, AMBER, CYAN, VIOLET, RED, MUTED]

AXIS = {
    "axisLabel": {"color": MUTED},
    "axisLine": {"lineStyle": {"color": GRID}},
    "axisTick": {"show": False},
    "splitLine": {"lineStyle": {"color": GRID}},
}
TOOLTIP = {
    "backgroundColor": "#0b1f4d",
    "borderColor": "#1f6feb",
    "textStyle": {"color": "#ffffff", "fontSize": 12},
}
LEGEND = {"icon": "roundRect", "itemWidth": 14, "itemHeight": 4, "textStyle": {"color": MUTED}}


def viewport_chart(options: dict, *, classes: str, aria_label: str):
    """Render once near the viewport so ECharts animation is visible on scroll."""
    initial_options = {"color": PALETTE, **options}
    initial_options["animation"] = False
    return (
        ui.echart(initial_options)
        .classes(f"viewport-animated-chart {classes}")
        .props(f'aria-label="{aria_label}" role="img"')
    )


def enable_viewport_chart_animations() -> None:
    """Arm current and subsequently mounted charts with an IntersectionObserver."""
    ui.run_javascript(
        """
        (() => {
          const selector = '.viewport-animated-chart';
          const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
          const locateChart = (element) => {
            if (!window.echarts) return null;
            const candidates = [element, ...element.querySelectorAll('div')];
            return candidates.map((candidate) => window.echarts.getInstanceByDom(candidate))
              .find(Boolean) || null;
          };
          const reveal = (element, attempt = 0) => {
            if (element.dataset.chartRevealed === 'true') return;
            const chart = locateChart(element);
            if (!chart && attempt < 20) {
              window.setTimeout(() => reveal(element, attempt + 1), 100);
              return;
            }
            element.dataset.chartRevealed = 'true';
            if (!chart || reducedMotion) return;
            const options = chart.getOption();
            chart.clear();
            chart.setOption({
              ...options,
              animation: true,
              animationDuration: 700,
              animationEasing: 'cubicOut',
            }, true);
          };
          if (!window.__bizqlabChartObserver) {
            window.__bizqlabChartObserver = new IntersectionObserver((entries, observer) => {
              entries.forEach((entry) => {
                if (!entry.isIntersecting) return;
                observer.unobserve(entry.target);
                reveal(entry.target);
              });
            }, {rootMargin: '160px 0px', threshold: 0.05});
          }
          const arm = (root = document) => root.querySelectorAll(selector).forEach((element) => {
            if (element.dataset.chartArmed === 'true') return;
            element.dataset.chartArmed = 'true';
            window.__bizqlabChartObserver.observe(element);
          });
          arm();
          if (!window.__bizqlabChartMutationObserver) {
            window.__bizqlabChartMutationObserver = new MutationObserver(() => arm());
            window.__bizqlabChartMutationObserver.observe(document.body, {childList: true, subtree: true});
          }
        })();
        """
    )
