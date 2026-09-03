from __future__ import annotations

from nicegui import ui

from app.admin.service import require_admin
from app.auth.service import SESSION_COOKIE
from app.components.navbar import with_layout


@ui.page("/admin/blog")
@with_layout
def admin_blog():
    request = ui.context.client.request
    require_admin(request.cookies.get(SESSION_COOKIE))
    ui.page_title("Blog publishing — Bizqlab")

    with ui.column().classes("w-full max-w-7xl mx-auto px-4 py-8 sm:px-8 gap-6"):
        with ui.row().classes("w-full items-start justify-between gap-3 flex-wrap"):
            with ui.column().classes("gap-2"):
                ui.label("Blog publishing").classes("text-4xl font-bold")
                ui.label(
                    "Owner-only drafts, sanitized preview, publishing, and revision history. "
                    "Publishing writes PostgreSQL immediately and does not rebuild Railway."
                ).classes("text-grey-7")
            ui.link("View public blog", "/blog").classes(
                "text-primary font-semibold no-underline hover:underline"
            )

        editor_html = """
        <div class="blog-admin-layout">
          <aside class="blog-admin-list-card">
            <div class="blog-admin-list-heading">
              <strong>Articles</strong>
              <button id="blog-new" type="button">New</button>
            </div>
            <div id="blog-post-list" class="blog-post-list">Loading…</div>
          </aside>
          <section class="blog-admin-editor-card">
            <form id="blog-editor-form">
              <input id="blog-post-id" type="hidden">
              <label>Title<input id="blog-title" maxlength="180" required></label>
              <div class="blog-slug-row">
                <label>Slug<input id="blog-slug" maxlength="120" pattern="[a-z0-9]+(?:-[a-z0-9]+)*" required></label>
                <button id="blog-generate-slug" type="button">From title</button>
              </div>
              <label>Summary<textarea id="blog-summary" rows="3" maxlength="320" required></textarea></label>
              <label>Markdown<textarea id="blog-body" rows="20" maxlength="50000" required placeholder="## Heading\n\nWrite the article in Markdown..."></textarea></label>
              <div class="blog-editor-actions">
                <button id="blog-preview" type="button">Preview</button>
                <button id="blog-save-draft" type="button">Save draft</button>
                <button id="blog-publish" class="primary" type="button">Publish</button>
              </div>
              <p id="blog-editor-status" role="status" aria-live="polite"></p>
            </form>
            <details id="blog-preview-panel">
              <summary>Sanitized preview</summary>
              <div id="blog-preview-output" class="blog-preview-output"></div>
            </details>
            <details>
              <summary>Revision history</summary>
              <div id="blog-revisions" class="blog-revisions">Save the article to create its first revision.</div>
            </details>
          </section>
        </div>
        """
        ui.html(editor_html).classes("w-full")

    ui.add_css("""
      .blog-admin-layout { display:grid; grid-template-columns:minmax(15rem,22rem) minmax(0,1fr); gap:1.25rem; }
      .blog-admin-list-card,.blog-admin-editor-card { border:1px solid #cbd5e1; border-radius:1rem; background:#fff; padding:1rem; }
      .blog-admin-list-heading { display:flex; align-items:center; justify-content:space-between; gap:.75rem; margin-bottom:.75rem; }
      .blog-post-list { display:grid; gap:.5rem; }
      .blog-post-list button { width:100%; text-align:left; border:1px solid #cbd5e1; border-radius:.65rem; background:#f8fafc; padding:.7rem; cursor:pointer; color:#0f172a; }
      .blog-post-list button.active { border-color:var(--q-primary); box-shadow:0 0 0 2px rgba(37,99,235,.15); }
      .blog-post-list small { display:block; color:#64748b; margin-top:.2rem; }
      #blog-editor-form { display:grid; gap:1rem; }
      #blog-editor-form label { display:grid; gap:.4rem; font-weight:600; }
      #blog-editor-form input,#blog-editor-form textarea { width:100%; border:1px solid #94a3b8; border-radius:.6rem; padding:.72rem .85rem; background:#fff; color:#111827; font:inherit; }
      #blog-body { font-family:ui-monospace,SFMono-Regular,Menlo,monospace!important; line-height:1.5; }
      .blog-slug-row { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:.75rem; align-items:end; }
      .blog-editor-actions { display:flex; flex-wrap:wrap; gap:.75rem; }
      .blog-admin-layout button { border:1px solid #94a3b8; border-radius:.55rem; padding:.6rem .85rem; background:#f8fafc; color:#0f172a; cursor:pointer; font-weight:700; }
      .blog-admin-layout button.primary { border-color:var(--q-primary); background:var(--q-primary); color:#fff; }
      #blog-editor-status { min-height:1.5rem; margin:0; }
      #blog-preview-panel,.blog-admin-editor-card>details { margin-top:1rem; }
      .blog-preview-output { padding:1rem 0; line-height:1.7; }
      .blog-preview-output pre { overflow:auto; padding:1rem; border-radius:.65rem; background:#0f172a; color:#e5e7eb; }
      .blog-revisions { padding:.75rem 0; color:#64748b; }
      html[data-theme="dark"] .blog-admin-list-card,html[data-theme="dark"] .blog-admin-editor-card { background:#1f2937; border-color:#475569; }
      html[data-theme="dark"] .blog-post-list button,html[data-theme="dark"] .blog-admin-layout button { background:#273449; border-color:#64748b; color:#f8fafc; }
      html[data-theme="dark"] #blog-editor-form input,html[data-theme="dark"] #blog-editor-form textarea { background:#111827; border-color:#64748b; color:#f8fafc; }
      @media(max-width:850px){.blog-admin-layout{grid-template-columns:1fr}.blog-slug-row{grid-template-columns:1fr}}
    """)
    ui.run_javascript("""
      (() => {
        const form = document.getElementById('blog-editor-form');
        if (!form || form.dataset.bound === 'true') return;
        form.dataset.bound = 'true';
        const field = (name) => document.getElementById(`blog-${name}`);
        const status = field('editor-status');
        const list = field('post-list');
        const revisions = field('revisions');
        const previewPanel = field('preview-panel');
        const previewOutput = field('preview-output');
        let selectedId = '';

        const cookie = (name) => document.cookie.split('; ')
          .find((entry) => entry.startsWith(`${name}=`))?.split('=').slice(1).join('=');
        const csrfHeaders = () => ({
          'Content-Type': 'application/json',
          'X-CSRF-Token': decodeURIComponent(cookie('portfolio_auth_csrf') || ''),
        });
        const slugify = (value) => value.toLowerCase().trim()
          .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 120);
        const requestJson = async (url, options = {}) => {
          const response = await fetch(url, {credentials:'same-origin', ...options});
          const body = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(body.detail || 'The blog request failed.');
          return body;
        };
        const payload = (nextStatus) => ({
          title: field('title').value,
          slug: field('slug').value,
          summary: field('summary').value,
          body_markdown: field('body').value,
          status: nextStatus,
        });
        const reset = () => {
          selectedId = '';
          form.reset();
          field('post-id').value = '';
          revisions.textContent = 'Save the article to create its first revision.';
          previewOutput.replaceChildren();
          previewPanel.open = false;
          status.textContent = 'New draft';
          document.querySelectorAll('.blog-post-list button').forEach((button) => button.classList.remove('active'));
        };
        const loadPost = async (id) => {
          status.textContent = 'Loading…';
          try {
            const post = await requestJson(`/api/admin/blog/posts/${id}`);
            selectedId = post.id;
            field('post-id').value = post.id;
            field('title').value = post.title;
            field('slug').value = post.slug;
            field('summary').value = post.summary;
            field('body').value = post.body_markdown;
            revisions.textContent = post.revisions.length
              ? post.revisions.map((item) => `v${item.version} · ${item.status} · ${new Date(item.created_at).toLocaleString()}`).join('\n')
              : 'No revisions yet.';
            revisions.style.whiteSpace = 'pre-line';
            status.textContent = `${post.status} · version ${post.version}`;
            document.querySelectorAll('.blog-post-list button').forEach((button) => button.classList.toggle('active', button.dataset.id === id));
          } catch (error) { status.textContent = error.message; }
        };
        const refreshList = async () => {
          try {
            const posts = await requestJson('/api/admin/blog/posts');
            list.replaceChildren();
            if (!posts.length) { list.textContent = 'No articles yet.'; return; }
            posts.forEach((post) => {
              const button = document.createElement('button');
              button.type = 'button';
              button.dataset.id = post.id;
              const title = document.createElement('strong');
              title.textContent = post.title;
              const note = document.createElement('small');
              note.textContent = `${post.status} · v${post.version}`;
              button.append(title, note);
              button.addEventListener('click', () => void loadPost(post.id));
              list.append(button);
            });
          } catch (error) { list.textContent = error.message; }
        };
        const save = async (nextStatus) => {
          if (!form.reportValidity()) return;
          status.textContent = nextStatus === 'published' ? 'Publishing…' : 'Saving draft…';
          try {
            const url = selectedId ? `/api/admin/blog/posts/${selectedId}` : '/api/admin/blog/posts';
            const post = await requestJson(url, {
              method: selectedId ? 'PUT' : 'POST', headers: csrfHeaders(),
              body: JSON.stringify(payload(nextStatus)),
            });
            selectedId = post.id;
            status.textContent = `${post.status} · version ${post.version} saved`;
            await refreshList();
            await loadPost(post.id);
          } catch (error) { status.textContent = error.message; }
        };

        field('new').addEventListener('click', reset);
        field('generate-slug').addEventListener('click', () => { field('slug').value = slugify(field('title').value); });
        field('save-draft').addEventListener('click', () => void save('draft'));
        field('publish').addEventListener('click', () => void save('published'));
        field('preview').addEventListener('click', async () => {
          status.textContent = 'Rendering safe preview…';
          try {
            const result = await requestJson('/api/admin/blog/preview', {
              method:'POST', headers:csrfHeaders(),
              body:JSON.stringify({body_markdown:field('body').value}),
            });
            previewOutput.innerHTML = result.html;
            previewPanel.open = true;
            status.textContent = 'Preview updated; it has not been saved.';
          } catch (error) { status.textContent = error.message; }
        });
        form.addEventListener('submit', (event) => event.preventDefault());
        void refreshList();
      })();
    """)
