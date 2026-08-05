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


def navbar():
    """Render the portfolio header shared with the React transit frontend."""
    request = ui.context.client.request
    current_path = request.url.path.rstrip('/') or '/' if request else ''
    links = ''.join(
        f'<a href="{escape(path, quote=True)}"'
        f'{" aria-current=\"page\"" if (path.rstrip("/") or "/") == current_path else ""}'
        f'>{escape(label)}</a>'
        for label, path in NAV_LINKS
    )
    ui.html(
        f'''
        <style>
          .nicegui-portfolio-nav {{
            position: sticky;
            top: 0;
            z-index: 1400;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 24px;
            width: 100%;
            min-height: 64px;
            padding: 10px 24px;
            background: #5898d4;
            color: #fff;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.18);
            font-family: Arial, sans-serif;
          }}
          .nicegui-portfolio-nav a {{ color: inherit; text-decoration: none; }}
          .nicegui-portfolio-brand {{
            font-size: 22px;
            font-weight: 700;
            white-space: nowrap;
          }}
          .nicegui-portfolio-links {{
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 20px;
          }}
          .nicegui-nav-actions {{
            display: flex;
            align-items: center;
            gap: 12px;
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
          .nicegui-portfolio-links a,
          .nicegui-mobile-links a {{ font-size: 14px; font-weight: 600; }}
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
          body.portfolio-dark {{
            color-scheme: dark;
            background: #111827;
            color: #e5e7eb;
          }}
          body.portfolio-dark .q-page,
          body.portfolio-dark .q-page-container,
          body.portfolio-dark .nicegui-content {{
            background: #111827;
            color: #e5e7eb;
          }}
          body.portfolio-dark .q-card,
          body.portfolio-dark .q-timeline__content {{
            background: #1f2937;
            color: #e5e7eb;
          }}
          body.portfolio-dark .q-separator {{ background: #374151; }}
          body.portfolio-dark .nicegui-mobile-links {{
            border-color: #4b5563;
            background: #1f2937;
            color: #f9fafb;
          }}
          body.portfolio-dark .nicegui-mobile-links a {{ border-color: #374151; }}
          body.portfolio-dark .nicegui-mobile-links a[aria-current="page"] {{
            background: #27364a;
            color: #bfdbfe;
          }}
          @media (max-width: 900px) {{
            .nicegui-portfolio-nav {{ min-height: 56px; padding: 8px 16px; }}
            .nicegui-portfolio-brand {{ font-size: 19px; }}
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
          }}
        </style>
        <header class="nicegui-portfolio-nav">
          <a class="nicegui-portfolio-brand" href="/">My Portfolio</a>
          <nav class="nicegui-portfolio-links" aria-label="Portfolio navigation">
            {links}
          </nav>
          <div class="nicegui-nav-actions">
            <button class="portfolio-theme-toggle" type="button"
                    aria-label="Switch to dark theme" title="Switch theme">
              <span aria-hidden="true">🌙</span>
            </button>
            <details class="nicegui-mobile-menu">
              <summary aria-label="Open portfolio navigation">Menu</summary>
              <nav class="nicegui-mobile-links" aria-label="Mobile portfolio navigation">
                {links}
              </nav>
            </details>
          </div>
        </header>
        ''',
    ).classes('w-full').style('position: sticky; top: 0; z-index: 1400;')
    ui.run_javascript('''
      (() => {
        const storageKey = 'portfolio-theme';
        const body = document.body;
        const button = document.querySelector('.portfolio-theme-toggle');
        if (!button || button.dataset.themeReady === 'true') return;
        button.dataset.themeReady = 'true';

        const storedTheme = localStorage.getItem(storageKey);
        let theme = storedTheme ||
          (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');

        const applyTheme = (nextTheme) => {
          theme = nextTheme;
          const dark = theme === 'dark';
          body.classList.toggle('portfolio-dark', dark);
          button.querySelector('span').textContent = dark ? '☀️' : '🌙';
          button.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
          document.documentElement.style.colorScheme = theme;
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
