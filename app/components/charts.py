from __future__ import annotations

from nicegui import ui


def viewport_chart(options: dict, *, classes: str, aria_label: str):
    """Render once near the viewport so ECharts animation is visible on scroll."""
    initial_options = dict(options)
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
