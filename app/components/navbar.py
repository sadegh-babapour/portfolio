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
            position: relative;
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
          <details class="nicegui-mobile-menu">
            <summary aria-label="Open portfolio navigation">Menu</summary>
            <nav class="nicegui-mobile-links" aria-label="Mobile portfolio navigation">
              {links}
            </nav>
          </details>
        </header>
        ''',
    ).classes('w-full')


def with_layout(page_func):
    @wraps(page_func)
    def wrapper(*args, **kwargs):
        navbar()
        result = page_func(*args, **kwargs)
        footer()
        return result

    return wrapper
