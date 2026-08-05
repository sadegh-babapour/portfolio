from html import escape
from urllib.parse import quote

from nicegui import ui


def create_pdf_viewer(pdf_url: str):
    """Render a same-origin PDF in a responsive browser frame."""
    safe_url = escape(pdf_url, quote=True)
    download_url = f'{safe_url}?download=true'
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
        border: 1px solid #5898d4;
        border-radius: 0.5rem;
        color: #245d91;
        font-weight: 700;
        text-decoration: none;
      }}
      .resume-actions a.primary {{
        background: #5898d4;
        color: white;
      }}
      .resume-pdf-frame {{
        width: 100%;
        height: clamp(640px, 82vh, 1100px);
        overflow: hidden;
        border: 1px solid #d7dde5;
        border-radius: 0.75rem;
        background: #f3f4f6;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.1);
      }}
      .resume-pdf-frame iframe {{
        width: 100%;
        height: 100%;
        border: 0;
      }}
      html[data-theme="dark"] .resume-actions a {{
        border-color: #93c5fd;
        color: #bfdbfe;
      }}
      html[data-theme="dark"] .resume-actions a.primary {{
        background: #3b82f6;
        color: #fff;
      }}
      html[data-theme="dark"] .resume-pdf-frame {{
        border-color: #4b5563;
        background: #1f2937;
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
