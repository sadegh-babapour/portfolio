# from nicegui import ui

# def create_pdf_viewer(pdf_url: str):
#     '''Render a responsive PDF viewer iframe.'''
#     html = f'''
#     <style>
#         .responsive-pdf {{
#             width: calc(100% - 2rem);
#             height: calc(100vh - 15rem);
#             min-height: 600px;
#             border: 1px solid #ddd;
#             border-radius: 8px;
#             margin: 0 auto;
#             display: block;
#             box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
#         }}
#         @media (min-width: 769px) {{
#             .responsive-pdf {{ width: calc(100% - 10rem); height: calc(100vh - 10rem); }}
#         }}
#     </style>
#     <iframe
#         src="https://mozilla.github.io/pdf.js/web/viewer.html?file={pdf_url}&zoom=page-width"
#         class="responsive-pdf"
#         loading="lazy">
#         <p>Your browser does not support iframes. <a href="{pdf_url}">Download the PDF</a>.</p>
#     </iframe>
#     '''
#     ui.html(html)
from nicegui import ui

def create_pdf_viewer(pdf_url: str):
    '''Responsive PDF iframe.'''
    html = f"""
    <style>
      .responsive-pdf {{width:calc(100%-2rem);height:calc(100vh-15rem);min-height:600px;border:1px solid #ddd;border-radius:8px;margin:0 auto;display:block;box-shadow:0 4px 6px rgba(0,0,0,0.1);}}
      @media (min-width:769px) {{.responsive-pdf {{width:calc(100%-10rem);height:calc(100vh-10rem);}}}}
    </style>
    <iframe src="https://mozilla.github.io/pdf.js/web/viewer.html?file={pdf_url}&zoom=page-width" class="responsive-pdf" loading="lazy">
      <p>Your browser does not support iframes. <a href="{pdf_url}">Download the PDF</a>.</p>
    </iframe>
    """
    ui.html(html)