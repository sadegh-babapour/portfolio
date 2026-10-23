import hashlib
import json
import logging
from functools import wraps
from html import escape
from pathlib import Path

from nicegui import ui

from app.auth.service import SESSION_COOKIE, current_session
from app.content import CONTENT_DIR
from .footer import footer


log = logging.getLogger(__name__)


# Shared with the Calgary Transit map header (frontend/src/PortfolioNav.jsx), so links
# and theme rules are edited in one place: content/navigation.json.
NAVIGATION = json.loads((CONTENT_DIR / 'navigation.json').read_text(encoding='utf-8'))
NAV_LINKS = [tuple(link) for link in NAVIGATION['links']]
ACCOUNT_LINK = tuple(NAVIGATION['account_link'])
# Inserted into the theme scripts below in place of __PORTFOLIO_THEME__.
THEME_JSON = json.dumps(NAVIGATION['theme'])
# Header styles, shared with the transit map (frontend/src/PortfolioNav.jsx imports the
# same file). The version changes with the content, so browsers fetch edits at once.
NAV_STYLESHEET = Path(__file__).resolve().parents[2] / 'static' / 'portfolio-nav.css'
NAV_STYLESHEET_URL = (
    '/static/portfolio-nav.css?v='
    + hashlib.sha256(NAV_STYLESHEET.read_bytes()).hexdigest()[:12]
)
# Palette tokens and Quasar overrides for every page.
SITE_STYLESHEET = NAV_STYLESHEET.with_name('site.css')
SITE_STYLESHEET_URL = (
    '/static/site.css?v='
    + hashlib.sha256(SITE_STYLESHEET.read_bytes()).hexdigest()[:12]
)


def navbar():
    """Render the portfolio header shared with the React transit frontend."""
    ui.add_head_html('''
      <link rel="icon" type="image/png" href="/static/bizqlab_logo.png">
      <link rel="apple-touch-icon" href="/static/bizqlab_logo.png">
      <link rel="stylesheet" href="__SITE_STYLESHEET_URL__">
      <link rel="stylesheet" href="__NAV_STYLESHEET_URL__">
      <script>
        (() => {
          const config = __PORTFOLIO_THEME__;
          const mode = localStorage.getItem(config.mode_storage_key);
          const parts = new Intl.DateTimeFormat('en-CA', {
            timeZone: config.time_zone, hour: '2-digit', hourCycle: 'h23'
          }).formatToParts(new Date());
          const hour = Number(parts.find((part) => part.type === 'hour')?.value || 0);
          const automatic = hour >= config.light_from_hour && hour < config.dark_from_hour
            ? 'light' : 'dark';
          const theme = mode === 'light' || mode === 'dark' ? mode : automatic;
          document.documentElement.dataset.theme = theme;
          document.documentElement.style.colorScheme = theme;
        })();
      </script>
    '''.replace('__PORTFOLIO_THEME__', THEME_JSON)
       .replace('__NAV_STYLESHEET_URL__', NAV_STYLESHEET_URL)
       .replace('__SITE_STYLESHEET_URL__', SITE_STYLESHEET_URL))
    request = ui.context.client.request
    current_path = request.url.path.rstrip('/') or '/' if request else ''
    account_link = ACCOUNT_LINK
    if request:
        try:
            session_user = current_session(request.cookies.get(SESSION_COOKIE))
            if session_user:
                compact_name = session_user.display_name.strip().split()[0][:24]
                account_label, account_path = ACCOUNT_LINK
                account_link = (f'{account_label} · {compact_name}', account_path)
        except Exception:
            log.exception('Unable to personalize the account navigation label')

    def render_links(items):
        return ''.join(
            f'<a href="{escape(path, quote=True)}"'
            f'{" class=\"portfolio-account-link\"" if path == ACCOUNT_LINK[1] else ""}'
            f'{" aria-current=\"page\"" if (path.rstrip("/") or "/") == current_path else ""}'
            f'>{escape(label)}</a>'
            for label, path in items
        )

    desktop_links = render_links([*NAV_LINKS, account_link])
    mobile_links = render_links([account_link, *NAV_LINKS])
    ui.html(
        f'''
        <header class="portfolio-nav">
          <a class="portfolio-brand" href="/" aria-label="Bizqlab home">
            <img src="/static/bizqlab_logo.png" alt="Bizqlab logo">
            <span>Bizqlab</span>
          </a>
          <nav class="portfolio-nav-desktop" aria-label="Portfolio navigation">
            {desktop_links}
          </nav>
          <div class="portfolio-nav-actions">
            <time class="portfolio-mountain-clock">
              <span>Calgary</span>
              <strong>--:--</strong>
            </time>
            <button class="portfolio-theme-toggle" type="button"
                    aria-label="Theme: Auto" title="Theme: Auto">
              <span class="theme-mode-icon" aria-hidden="true">◐</span>
            </button>
            <details class="portfolio-nav-mobile">
              <summary aria-label="Open portfolio navigation">Menu</summary>
              <nav class="portfolio-nav-mobile-links" aria-label="Mobile portfolio navigation">
                {mobile_links}
              </nav>
            </details>
          </div>
        </header>
        ''',
    ).classes('w-full').style('position: sticky; top: 0; z-index: 1400;')
    ui.run_javascript('''
      (() => {
        const config = __PORTFOLIO_THEME__;
        const modeStorageKey = config.mode_storage_key;
        const resolvedStorageKey = config.resolved_storage_key;
        const button = document.querySelector('.portfolio-theme-toggle');
        const clock = document.querySelector('.portfolio-mountain-clock');
        if (!button || button.dataset.themeReady === 'true') return;
        button.dataset.themeReady = 'true';

        let mode = localStorage.getItem(modeStorageKey);
        if (!['auto', 'light', 'dark'].includes(mode)) mode = 'auto';
        let theme = document.documentElement.dataset.theme || 'light';

        const mountainHour = (date) => {
          const parts = new Intl.DateTimeFormat('en-CA', {
            timeZone: config.time_zone, hour: '2-digit', hourCycle: 'h23'
          }).formatToParts(date);
          return Number(parts.find((part) => part.type === 'hour')?.value || 0);
        };
        const resolveTheme = (date) => {
          if (mode === 'light' || mode === 'dark') return mode;
          const hour = mountainHour(date);
          return hour >= config.light_from_hour && hour < config.dark_from_hour
            ? 'light' : 'dark';
        };
        const modeLabel = () => mode === 'auto' ? 'Auto' : mode === 'light' ? 'Light' : 'Dark';
        const nextMode = () => mode === 'auto' ? 'light' : mode === 'light' ? 'dark' : 'auto';

        const applyChartTheme = () => {
          const dark = theme === 'dark';
          // The palette in static/site.css.
          const text = dark ? '#e8eef9' : '#0b1f4d';
          const muted = dark ? '#9aa9c6' : '#586b8f';
          const grid = dark ? '#24365e' : '#dbe3f1';
          const tooltipBackground = dark ? '#0d1730' : '#ffffff';
          const tooltipBorder = dark ? '#3a4f7a' : '#b7c3d9';

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
              update.legend = current.legend.map(() => ({ textStyle: { color: muted } }));
            }
            if (current.tooltip?.length) {
              update.tooltip = current.tooltip.map(() => ({
                backgroundColor: tooltipBackground,
                borderColor: tooltipBorder,
                textStyle: { color: text },
              }));
            }
            const axisTheme = () => ({
                axisLabel: { color: muted },
                axisLine: { lineStyle: { color: grid } },
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
          document.documentElement.dataset.theme = theme;
          document.documentElement.style.colorScheme = theme;
          localStorage.setItem(resolvedStorageKey, theme);
          localStorage.setItem(modeStorageKey, mode);
          const upcoming = nextMode();
          button.setAttribute('aria-label', `Theme: ${modeLabel()}. Switch to ${upcoming}.`);
          button.setAttribute('title', `Theme: ${modeLabel()}. Next: ${upcoming}.`);
          button.querySelector('.theme-mode-icon').textContent =
            mode === 'auto' ? '◐' : theme === 'dark' ? '☀️' : '🌙';
          window.setTimeout(applyChartTheme, 0);
          window.setTimeout(applyChartTheme, 300);
          window.setTimeout(applyChartTheme, 1000);
        };

        const updateClockAndAutomaticTheme = () => {
          const now = new Date();
          if (clock) {
            clock.dateTime = now.toISOString();
            clock.querySelector('strong').textContent = new Intl.DateTimeFormat('en-CA', {
              timeZone: config.time_zone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
            }).format(now);
          }
          const resolved = resolveTheme(now);
          if (resolved !== theme) applyTheme(resolved);
        };

        applyTheme(resolveTheme(new Date()));
        updateClockAndAutomaticTheme();
        window.setInterval(updateClockAndAutomaticTheme, 30000);
        button.addEventListener('click', () => {
          mode = nextMode();
          applyTheme(resolveTheme(new Date()));
        });

      })();
    '''.replace('__PORTFOLIO_THEME__', THEME_JSON))


def with_layout(page_func):
    @wraps(page_func)
    def wrapper(*args, **kwargs):
        navbar()
        result = page_func(*args, **kwargs)
        footer()
        return result

    return wrapper
