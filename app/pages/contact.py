from __future__ import annotations

import json

from nicegui import ui

from app.components.navbar import with_layout
from app.contact.config import ContactSettings


@ui.page("/contact")
@with_layout
def contact():
    settings = ContactSettings.from_env()
    if settings.turnstile_site_key:
        ui.add_head_html(
            '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js'
            '?render=explicit" async defer></script>'
        )

    with ui.column().classes("w-full max-w-7xl mx-auto px-4 py-8 sm:px-8 gap-8"):
        with ui.column().classes("gap-3 max-w-3xl"):
            ui.label("Let’s build something useful").classes("text-4xl sm:text-5xl font-bold")
            ui.label(
                "Have a data engineering role, analytics problem, or project worth "
                "discussing? Send the context and I’ll reply by email."
            ).classes("text-lg text-grey-7")

        with ui.element("div").classes(
            "grid w-full grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]"
        ):
            with ui.card().classes("w-full p-5 sm:p-8 gap-5"):
                ui.label("Send a message").classes("text-2xl font-semibold")
                ui.label(
                    "You’ll receive a verification link first. Your message is delivered "
                    "only after you confirm the address."
                ).classes("text-sm text-grey-7")

                form_html = """
                <form id="portfolio-contact-form" class="contact-native-form" novalidate>
                  <div class="contact-grid">
                    <label>Name<input id="contact-name" autocomplete="name" maxlength="100" required></label>
                    <label>Email<input id="contact-email" type="email" autocomplete="email" maxlength="254" required></label>
                  </div>
                  <label>Topic<select id="contact-category" required>
                    <option value="job-opportunity">Job opportunity</option>
                    <option value="project">Project collaboration</option>
                    <option value="networking">Professional networking</option>
                    <option value="other">Other</option>
                  </select></label>
                  <label>Subject<input id="contact-subject" maxlength="120" required></label>
                  <label>Message<textarea id="contact-message" rows="8" maxlength="5000" required></textarea></label>
                  <label class="contact-honeypot" aria-hidden="true">Website
                    <input id="contact-website" tabindex="-1" autocomplete="off">
                  </label>
                  <div id="contact-turnstile"></div>
                  <p id="contact-status" role="status" aria-live="polite"></p>
                  <button id="contact-submit" type="submit">Send verification email</button>
                </form>
                """
                ui.html(form_html).classes("w-full")

            with ui.column().classes("gap-4"):
                with ui.card().classes("w-full p-5 gap-3"):
                    ui.icon("schedule", size="md").classes("text-primary")
                    ui.label("What to expect").classes("text-xl font-semibold")
                    ui.label("Typical reply: within two business days.").classes("text-sm")
                    ui.label(
                        "Please don’t include passwords, private datasets, or other secrets."
                    ).classes("text-sm text-grey-7")
                with ui.card().classes("w-full p-5 gap-3"):
                    ui.icon("verified_user", size="md").classes("text-primary")
                    ui.label("Privacy & spam protection").classes("text-xl font-semibold")
                    ui.label(
                        "Your address is used to verify and reply to this message. "
                        "Turnstile, throttling, and a hidden bot field protect the form."
                    ).classes("text-sm text-grey-7")

        if not settings.configured:
            ui.label(
                "Secure message delivery is being configured. The form will remain "
                "disabled until its database, Turnstile, and mail settings are ready."
            ).classes("text-warning text-sm")

    site_key = json.dumps(settings.turnstile_site_key)
    enabled = "true" if settings.configured else "false"
    ui.add_css("""
      .contact-native-form { display:grid; gap:1rem; }
      .contact-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:1rem; }
      .contact-native-form label { display:grid; gap:.4rem; font-weight:600; }
      .contact-native-form input,.contact-native-form select,.contact-native-form textarea {
        width:100%; border:1px solid var(--q-separator-color); border-radius:.6rem;
        padding:.72rem .85rem; color:inherit; background:var(--q-dark-page, transparent);
      }
      body:not(.body--dark) .contact-native-form input,
      body:not(.body--dark) .contact-native-form select,
      body:not(.body--dark) .contact-native-form textarea { background:#fff; }
      .contact-native-form input:focus,.contact-native-form select:focus,
      .contact-native-form textarea:focus { outline:2px solid var(--q-primary); outline-offset:1px; }
      .contact-native-form button { justify-self:start; border:0; border-radius:.6rem;
        padding:.75rem 1.1rem; background:var(--q-primary); color:#fff; font-weight:700; cursor:pointer; }
      .contact-native-form button:disabled { opacity:.55; cursor:not-allowed; }
      .contact-honeypot { position:absolute!important; left:-10000px!important; width:1px!important; overflow:hidden; }
      #contact-status { min-height:1.5rem; margin:0; }
      @media(max-width:640px){.contact-grid{grid-template-columns:1fr}}
    """)
    ui.run_javascript(f"""
      (() => {{
        const configured = {enabled};
        const siteKey = {site_key};
        const form = document.getElementById('portfolio-contact-form');
        const button = document.getElementById('contact-submit');
        const status = document.getElementById('contact-status');
        let widgetId = null;
        if (!form || form.dataset.bound === 'true') return;
        form.dataset.bound = 'true';
        if (!configured) {{ button.disabled = true; return; }}

        const renderWidget = () => {{
          if (window.turnstile && widgetId === null) {{
            widgetId = window.turnstile.render('#contact-turnstile', {{
              sitekey: siteKey, action: 'contact', theme: 'auto',
              'error-callback': () => {{
                status.textContent = 'The security check could not load. Refresh and try again.';
                return true;
              }},
              'expired-callback': () => {{
                status.textContent = 'The security check expired. Please complete it again.';
              }}
            }});
          }} else if (widgetId === null) {{ setTimeout(renderWidget, 100); }}
        }};
        renderWidget();

        form.addEventListener('submit', async (event) => {{
          event.preventDefault();
          status.textContent = '';
          if (!form.reportValidity()) return;
          const turnstileToken = widgetId === null ? '' : window.turnstile.getResponse(widgetId);
          if (!turnstileToken) {{ status.textContent = 'Complete the bot check before sending.'; return; }}
          button.disabled = true;
          status.textContent = 'Submitting securely…';
          try {{
            const csrfResponse = await fetch('/api/contact/csrf', {{credentials:'same-origin'}});
            const csrf = await csrfResponse.json();
            if (!csrfResponse.ok) throw new Error(csrf.detail || 'Contact service is unavailable.');
            const response = await fetch('/api/contact/messages', {{
              method:'POST', credentials:'same-origin',
              headers:{{'Content-Type':'application/json','X-CSRF-Token':csrf.csrf_token}},
              body:JSON.stringify({{
                name:document.getElementById('contact-name').value,
                email:document.getElementById('contact-email').value,
                category:document.getElementById('contact-category').value,
                subject:document.getElementById('contact-subject').value,
                message:document.getElementById('contact-message').value,
                website:document.getElementById('contact-website').value,
                turnstile_token:turnstileToken
              }})
            }});
            const result = await response.json();
            if (!response.ok) throw new Error(result.detail || 'Unable to send the message.');
            status.textContent = result.message;
            form.reset();
          }} catch (error) {{ status.textContent = error.message; }}
          finally {{
            if (widgetId !== null) window.turnstile.reset(widgetId);
            button.disabled = false;
          }}
        }});
      }})();
    """)
