from html import escape
from urllib.parse import quote

from nicegui import ui


def create_pdf_viewer(pdf_url: str):
    """Render a same-origin PDF in a responsive browser frame."""
    safe_url = escape(pdf_url, quote=True)
    separator = '&amp;' if '?' in pdf_url else '?'
    download_url = f'{safe_url}{separator}download=true'
    viewer_url = (
        '/calgary-transit-live/pdf-viewer.html?file='
        f'{quote(pdf_url, safe="")}'
    )
    html = f"""
    <style>
      .resume-actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
        margin-bottom: 1rem;
      }}
      .resume-actions a {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 44px;
        padding: 0.65rem 1rem;
        border: 1px solid var(--bq-blue);
        border-radius: 10px;
        color: var(--bq-blue);
        font-weight: 600;
        text-decoration: none;
      }}
      .resume-actions a.primary {{
        background: var(--bq-blue);
        color: white;
      }}
      .resume-pdf-frame {{
        width: 100%;
        height: clamp(640px, 82vh, 1100px);
        overflow: hidden;
        border: 1px solid var(--bq-line);
        border-radius: var(--bq-radius);
        background: var(--bq-panel);
        box-shadow: var(--bq-shadow);
      }}
      .resume-pdf-frame iframe {{
        width: 100%;
        height: 100%;
        border: 0;
      }}
      @media (max-width: 700px) {{
        .resume-actions {{ flex-direction: column; }}
        .resume-actions a {{ width: 100%; }}
        .resume-pdf-frame {{
          width: 100%;
          height: calc(100dvh - 250px);
          min-height: 560px;
          border-radius: 0.5rem;
        }}
      }}
    </style>
    <div class="resume-actions">
      <a class="primary" href="{safe_url}" target="_blank" rel="noopener">
        Open full-screen PDF
      </a>
      <a href="{download_url}">Download PDF</a>
    </div>
    <div class="resume-pdf-frame">
      <iframe src="{viewer_url}" title="Résumé PDF viewer"
              loading="eager"></iframe>
    </div>
    """
    ui.html(html).classes('w-full')
