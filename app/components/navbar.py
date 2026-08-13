from functools import wraps
from html import escape

from nicegui import ui

from .footer import footer


NAV_LINKS = [
    ('Home', '/'),
    ('About', '/about'),
    ('Resume', '/resume'),
    ('Projects', '/projects'),
    ('Contact', '/contact'),
    ('Dashboard', '/dashboard'),
    ('Calgary Transit Live', '/calgary-transit-live/'),
]
ACCOUNT_LINK = ('Account', '/account')


def navbar():
    """Render the portfolio header shared with the React transit frontend."""
    ui.add_head_html('''
      <link rel="icon" type="image/png" href="/static/bizqlab_logo.png">
      <link rel="apple-touch-icon" href="/static/bizqlab_logo.png">
      <script>
        (() => {
          const stored = localStorage.getItem('portfolio-theme');
          const theme = stored === 'dark' || stored === 'light'
            ? stored
            : (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
          document.documentElement.dataset.theme = theme;
          document.documentElement.style.colorScheme = theme;
        })();
      </script>
      <style>
        html[data-theme="dark"],
        html[data-theme="dark"] body {
          background: #111827;
          color: #e5e7eb;
        }
      </style>
    ''')
    request = ui.context.client.request
    current_path = request.url.path.rstrip('/') or '/' if request else ''

    def render_links(items):
        return ''.join(
            f'<a href="{escape(path, quote=True)}"'
            f'{" class=\"portfolio-account-link\"" if path == "/account" else ""}'
            f'{" aria-current=\"page\"" if (path.rstrip("/") or "/") == current_path else ""}'
            f'>{escape(label)}</a>'
            for label, path in items
        )

    desktop_links = render_links([*NAV_LINKS, ACCOUNT_LINK])
    mobile_links = render_links([ACCOUNT_LINK, *NAV_LINKS])
    ui.html(
        f'''
        <style>
          .nicegui-portfolio-nav {{
            box-sizing: border-box;
            position: sticky;
            top: 0;
            z-index: 1400;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 24px;
            width: 100%;
            height: 64px;
            min-height: 64px;
            padding: 10px 24px;
            background: #5898d4;
            color: #fff;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.18);
            font-family: Arial, sans-serif;
          }}
          .nicegui-portfolio-nav a {{ color: inherit; text-decoration: none; }}
          .nicegui-portfolio-brand {{
            display: inline-flex;
            align-items: center;
            gap: 9px;
            font-size: 22px;
            font-weight: 700;
            white-space: nowrap;
          }}
          .nicegui-portfolio-brand-logo {{
            width: 42px;
            height: 42px;
            object-fit: cover;
            border: 2px solid rgba(255, 255, 255, 0.9);
            border-radius: 10px;
            background: #fff;
          }}
          .nicegui-portfolio-links {{
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 20px;
            margin-left: auto;
            min-width: 0;
          }}
          .nicegui-nav-actions {{
            display: flex;
            align-items: center;
            gap: 12px;
            flex: 0 0 auto;
          }}
          .portfolio-theme-toggle {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 44px;
            min-height: 40px;
            padding: 8px 10px;
            border: 1px solid rgba(255, 255, 255, 0.7);
            border-radius: 8px;
            background: transparent;
            color: inherit;
            cursor: pointer;
            font: inherit;
            font-size: 18px;
          }}
          .portfolio-theme-toggle:hover,
          .portfolio-theme-toggle:focus-visible {{
            background: rgba(255, 255, 255, 0.14);
          }}
          .theme-icon-dark {{ display: none; }}
          html[data-theme="dark"] .theme-icon-light {{ display: none; }}
          html[data-theme="dark"] .theme-icon-dark {{ display: inline; }}
          .nicegui-portfolio-links a,
          .nicegui-mobile-links a {{ font-size: 14px; font-weight: 600; }}
          .nicegui-portfolio-links .portfolio-account-link {{
            padding: 8px 11px;
            border: 1px solid rgba(255, 255, 255, 0.75);
            border-radius: 999px;
          }}
          .nicegui-portfolio-links a:hover,
          .nicegui-portfolio-links a:focus-visible,
          .nicegui-mobile-links a:hover,
          .nicegui-mobile-links a:focus-visible {{
            text-decoration: underline;
            text-underline-offset: 4px;
          }}
          .nicegui-portfolio-nav a[aria-current="page"] {{
            text-decoration: underline;
            text-decoration-thickness: 2px;
            text-underline-offset: 5px;
          }}
          .nicegui-mobile-menu {{ display: none; }}
          html[data-theme="dark"] body {{
            color-scheme: dark;
            background: #111827;
            color: #e5e7eb;
          }}
          html[data-theme="dark"] .q-layout,
          html[data-theme="dark"] .q-page,
          html[data-theme="dark"] .q-page-container,
          html[data-theme="dark"] .nicegui-content {{
            background: #111827;
            color: #e5e7eb;
          }}
          html[data-theme="dark"] .q-card,
          html[data-theme="dark"] .q-tab-panels,
          html[data-theme="dark"] .q-tab-panel,
          html[data-theme="dark"] .q-table__container,
          html[data-theme="dark"] .q-timeline__content {{
            background: #1f2937;
            color: #e5e7eb;
          }}
          html[data-theme="dark"] .q-field__control {{
            background: #1f2937;
            color: #f3f4f6;
          }}
          html[data-theme="dark"] .q-field__native,
          html[data-theme="dark"] .q-field__input,
          html[data-theme="dark"] .q-field__label,
          html[data-theme="dark"] .q-field__marginal,
          html[data-theme="dark"] .q-tab,
          html[data-theme="dark"] .q-table th,
          html[data-theme="dark"] .q-table td {{
            color: #e5e7eb;
          }}
          html[data-theme="dark"] .q-field--outlined .q-field__control::before {{
            border-color: #64748b;
          }}
          html[data-theme="dark"] .q-table thead,
          html[data-theme="dark"] .q-table tbody,
          html[data-theme="dark"] .q-table tr {{
            background: #1f2937;
          }}
          html[data-theme="dark"] .q-table th,
          html[data-theme="dark"] .q-table td,
          html[data-theme="dark"] .q-separator {{ border-color: #374151; }}
          html[data-theme="dark"] .q-separator {{ background: #374151; }}
          html[data-theme="dark"] .text-grey {{ color: #cbd5e1 !important; }}
          html[data-theme="dark"] .nicegui-echart {{
            border-radius: 8px;
            background: #1f2937;
            color: #e5e7eb;
          }}
          html[data-theme="dark"] .nicegui-mobile-links {{
            border-color: #4b5563;
            background: #1f2937;
            color: #f9fafb;
          }}
          html[data-theme="dark"] .nicegui-mobile-links a {{ border-color: #374151; }}
          html[data-theme="dark"] .nicegui-mobile-links a[aria-current="page"] {{
            background: #27364a;
            color: #bfdbfe;
          }}
          html[data-theme="dark"] .portfolio-development-note {{
            border-color: #3b82f6 !important;
            background: #172554 !important;
            color: #dbeafe !important;
          }}
          @media (max-width: 1050px) {{
            .nicegui-portfolio-nav {{ height: 56px; min-height: 56px; padding: 8px 16px; }}
            .nicegui-portfolio-brand {{ font-size: 19px; }}
            .nicegui-portfolio-brand-logo {{ width: 36px; height: 36px; }}
            .nicegui-portfolio-links {{ display: none; }}
            .nicegui-mobile-menu {{ display: block; }}
            .nicegui-mobile-menu summary {{
              padding: 8px 12px;
              border: 1px solid rgba(255, 255, 255, 0.7);
              border-radius: 8px;
              cursor: pointer;
              font-size: 14px;
              font-weight: 700;
              list-style: none;
            }}
            .nicegui-mobile-menu summary::-webkit-details-marker {{ display: none; }}
            .nicegui-mobile-links {{
              position: absolute;
              top: calc(100% - 4px);
              right: 12px;
              display: flex;
              flex-direction: column;
              min-width: 230px;
              overflow: hidden;
              border: 1px solid #dbe3ec;
              border-radius: 10px;
              background: #fff;
              color: #111827;
              box-shadow: 0 12px 24px rgba(15, 23, 42, 0.2);
            }}
            .nicegui-mobile-links a {{
              padding: 12px 16px;
              border-bottom: 1px solid #eef2f6;
            }}
            .nicegui-mobile-links a:last-child {{ border-bottom: 0; }}
            .nicegui-mobile-links a[aria-current="page"] {{
              background: #edf6ff;
              color: #245d91;
            }}
            .nicegui-mobile-links .portfolio-account-link {{
              background: #e8f3ff;
              color: #245d91;
              font-weight: 700;
            }}
          }}
        </style>
        <header class="nicegui-portfolio-nav">
          <a class="nicegui-portfolio-brand" href="/" aria-label="Bizqlab home">
            <img class="nicegui-portfolio-brand-logo"
                 src="/static/bizqlab_logo.png" alt="Bizqlab logo">
            <span>Bizqlab</span>
          </a>
          <nav class="nicegui-portfolio-links" aria-label="Portfolio navigation">
            {desktop_links}
          </nav>
          <div class="nicegui-nav-actions">
            <button class="portfolio-theme-toggle" type="button"
                    aria-label="Switch to dark theme" title="Switch theme">
              <span class="theme-icon-light" aria-hidden="true">🌙</span>
              <span class="theme-icon-dark" aria-hidden="true">☀️</span>
            </button>
            <details class="nicegui-mobile-menu">
              <summary aria-label="Open portfolio navigation">Menu</summary>
              <nav class="nicegui-mobile-links" aria-label="Mobile portfolio navigation">
                {mobile_links}
              </nav>
            </details>
          </div>
        </header>
        ''',
    ).classes('w-full').style('position: sticky; top: 0; z-index: 1400;')
    ui.run_javascript('''
      (() => {
        const storageKey = 'portfolio-theme';
        const button = document.querySelector('.portfolio-theme-toggle');
        if (!button || button.dataset.themeReady === 'true') return;
        button.dataset.themeReady = 'true';

        let theme = document.documentElement.dataset.theme || 'light';

        const applyChartTheme = () => {
          const dark = theme === 'dark';
          const text = dark ? '#e5e7eb' : '#374151';
          const muted = dark ? '#94a3b8' : '#9ca3af';
          const grid = dark ? '#374151' : '#e5e7eb';
          const tooltipBackground = dark ? '#111827' : '#ffffff';
          const tooltipBorder = dark ? '#64748b' : '#d1d5db';

          if (!window.echarts) return;
          document.querySelectorAll('.nicegui-echart, nicegui-echart').forEach((element) => {
            const chartHost = element.querySelector('div');
            const chart = window.echarts.getInstanceByDom(element) ||
              (chartHost ? window.echarts.getInstanceByDom(chartHost) : null);
            if (!chart) return;
            const current = chart.getOption();
            const update = {
              backgroundColor: 'transparent',
              textStyle: { color: text },
            };
            if (current.title?.length) {
              update.title = current.title.map(() => ({
                textStyle: { color: text }, subtextStyle: { color: muted },
              }));
            }
            if (current.legend?.length) {
              update.legend = current.legend.map(() => ({ textStyle: { color: text } }));
            }
            if (current.tooltip?.length) {
              update.tooltip = current.tooltip.map(() => ({
                backgroundColor: tooltipBackground,
                borderColor: tooltipBorder,
                textStyle: { color: text },
              }));
            }
            const axisTheme = () => ({
                axisLabel: { color: text },
                axisLine: { lineStyle: { color: muted } },
                splitLine: { lineStyle: { color: grid } },
                nameTextStyle: { color: text },
            });
            for (const axisName of ['xAxis', 'yAxis', 'angleAxis', 'radiusAxis']) {
              if (current[axisName]?.length) {
                update[axisName] = current[axisName].map(axisTheme);
              }
            }
            chart.setOption(update);
          });
        };

        const applyTheme = (nextTheme) => {
          theme = nextTheme;
          const dark = theme === 'dark';
          document.documentElement.dataset.theme = theme;
          button.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
          document.documentElement.style.colorScheme = theme;
          window.setTimeout(applyChartTheme, 0);
          window.setTimeout(applyChartTheme, 300);
          window.setTimeout(applyChartTheme, 1000);
        };

        applyTheme(theme);
        button.addEventListener('click', () => {
          const nextTheme = theme === 'dark' ? 'light' : 'dark';
          localStorage.setItem(storageKey, nextTheme);
          applyTheme(nextTheme);
        });

      })();
    ''')


def with_layout(page_func):
    @wraps(page_func)
    def wrapper(*args, **kwargs):
        navbar()
        result = page_func(*args, **kwargs)
        footer()
        return result

    return wrapper
