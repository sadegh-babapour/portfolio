"""/contact: a plain HTML form plus a small script that talks to /api/contact/*.

The form is native HTML rather than NiceGUI inputs so it works like any web form and the
submit logic stays in one script: fetch a CSRF token, solve Turnstile, POST the message.
"""
from __future__ import annotations

import json
import logging

from nicegui import ui

from app.auth.service import SESSION_COOKIE, current_session
from app.components.navbar import with_layout
from app.contact.config import ContactSettings


log = logging.getLogger(__name__)


@ui.page("/contact")
@with_layout
def contact():
    settings = ContactSettings.from_env()
    request = ui.context.client.request
    requested_topic = request.query_params.get("topic") if request else None
    account_request = requested_topic == "account-deletion"
    signed_in_user = None
    try:
        signed_in_user = current_session(request.cookies.get(SESSION_COOKIE))
    except Exception:
        log.exception("Unable to prefill the contact identity")
    if settings.turnstile_site_key:
        ui.add_head_html(
            '<script src="https://challenges.cloudflare.com/turnstile/v0/api.js'
            '?render=explicit" async defer></script>'
        )

    with ui.column().classes("w-full max-w-7xl mx-auto px-4 py-8 sm:px-8 gap-8"):
        with ui.column().classes("gap-3 max-w-3xl"):
            ui.label("Let’s build something useful").classes("text-4xl sm:text-5xl font-bold")
            ui.label(
                "A role, a data problem or a project idea? Send the details and I’ll reply by email."
            ).classes("text-lg text-grey-7")

        with ui.element("div").classes(
            "grid w-full grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]"
        ):
            with ui.card().classes("w-full min-w-0 p-5 sm:p-8 gap-5"):
                ui.label("Send a message").classes("text-2xl font-semibold")
                ui.label(
                    "You’ll get a link to confirm your email; the message is sent once you click it."
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
                    <option value="account-privacy">Account or privacy request</option>
                    <option value="other">Other</option>
                  </select></label>
                  <label>Subject<input id="contact-subject" maxlength="120" required></label>
                  <label>Message<textarea id="contact-message" rows="8" maxlength="5000" required></textarea></label>
                  <label class="contact-honeypot" aria-hidden="true">Website
                    <input id="contact-website" tabindex="-1" autocomplete="off">
                  </label>
                  <div id="contact-turnstile"></div>
                  <p id="contact-status" role="status" aria-live="polite"></p>
                  <button id="contact-submit" type="submit">Send</button>
                </form>
                """
                ui.html(form_html).classes("w-full min-w-0")

            with ui.card().classes("w-full p-5 gap-3 self-start"):
                ui.label("Good to know").classes("text-xl font-semibold")
                for line in (
                    "I reply within three business days.",
                    "Your email is only used to confirm and reply.",
                    "Please don’t send passwords or private data.",
                ):
                    ui.label(line).classes("text-sm text-grey-7")

        if not settings.configured:
            ui.label(
                "The form is switched off while message delivery is being set up."
            ).classes("text-warning text-sm")

    site_key = json.dumps(settings.turnstile_site_key)
    prefill_name = json.dumps(signed_in_user.display_name if signed_in_user else "")
    prefill_email = json.dumps(signed_in_user.email if signed_in_user else "")
    prefill_account_request = "true" if account_request else "false"
    enabled = "true" if settings.configured else "false"
    ui.add_css("""
      .contact-native-form { display:grid; gap:1rem; width:100%; min-width:0; }
      .contact-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:1rem; }
      .contact-native-form label { display:grid; min-width:0; gap:.4rem; font-weight:600; }
      .contact-native-form > *, .contact-grid > * { min-width:0; max-width:100%; }
      .contact-native-form input,.contact-native-form select,.contact-native-form textarea {
        box-sizing:border-box; width:100%; border:1px solid var(--bq-field); border-radius:.6rem;
        padding:.72rem .85rem; color:var(--bq-ink); background:var(--bq-panel); font:inherit;
        transition:border-color .15s ease,box-shadow .15s ease;
      }
      .contact-native-form input:hover,.contact-native-form select:hover,
      .contact-native-form textarea:hover { border-color:var(--bq-muted); }
      .contact-native-form input:focus,.contact-native-form select:focus,
      .contact-native-form textarea:focus { border-color:var(--q-primary); outline:none;
        box-shadow:0 0 0 3px rgba(31,111,235,.2); }
      .contact-native-form button { justify-self:start; border:0; border-radius:10px;
        padding:.75rem 1.4rem; background:var(--q-primary); color:#fff; font:inherit; font-weight:600; cursor:pointer; }
      .contact-native-form button:disabled { opacity:.55; cursor:not-allowed; }
      .contact-honeypot { position:absolute!important; left:-10000px!important; width:1px!important; overflow:hidden; }
      #contact-status { min-height:1.5rem; margin:0; }
      #contact-turnstile { width:300px; max-width:100%; min-height:65px; }
      @media(max-width:640px){.contact-grid{grid-template-columns:1fr}}
    """)
    ui.run_javascript(f"""
      (() => {{
        const configured = {enabled};
        const siteKey = {site_key};
        const accountRequest = {prefill_account_request};
        const prefillName = {prefill_name};
        const prefillEmail = {prefill_email};
        const form = document.getElementById('portfolio-contact-form');
        const button = document.getElementById('contact-submit');
        const status = document.getElementById('contact-status');
        let widgetId = null;
        let csrfToken = '';
        let turnstileToken = '';
        if (!form || form.dataset.bound === 'true') return;
        form.dataset.bound = 'true';
        document.getElementById('contact-name').value = prefillName;
        document.getElementById('contact-email').value = prefillEmail;
        if (accountRequest) {{
          document.getElementById('contact-category').value = 'account-privacy';
          document.getElementById('contact-subject').value = 'Account deletion request';
          document.getElementById('contact-message').value =
            'Please delete my local Bizqlab account and its saved transit stops. ' +
            'I understand you will verify the request before completing it.';
          if (prefillEmail) {{
            document.getElementById('contact-name').readOnly = true;
            document.getElementById('contact-email').readOnly = true;
          }}
        }}
        if (!configured) {{ button.disabled = true; return; }}

        const resetSubmission = () => {{
          csrfToken = '';
          turnstileToken = '';
          if (widgetId !== null) window.turnstile.reset(widgetId);
          button.disabled = false;
        }};

        const submitContact = async (turnstileToken) => {{
          status.textContent = 'Submitting securely…';
          try {{
            const response = await fetch('/api/contact/messages', {{
              method:'POST', credentials:'same-origin',
              headers:{{'Content-Type':'application/json','X-CSRF-Token':csrfToken}},
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
            document.getElementById('contact-name').value = prefillName;
            document.getElementById('contact-email').value = prefillEmail;
          }} catch (error) {{ status.textContent = error.message; }}
          finally {{ resetSubmission(); }}
        }};

        const renderWidget = () => {{
          if (window.turnstile && widgetId === null) {{
            widgetId = window.turnstile.render('#contact-turnstile', {{
              sitekey: siteKey, action: 'contact',
              theme: document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light',
              size: form.clientWidth < 300 ? 'compact' : 'normal',
              appearance: 'always',
              'response-field': false,
              callback: (token) => {{
                turnstileToken = token;
                status.textContent = 'Check complete. You can send.';
              }},
              'error-callback': () => {{
                status.textContent = 'The security check could not load. Refresh and try again.';
                resetSubmission();
                return true;
              }},
              'expired-callback': () => {{
                turnstileToken = '';
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
          if (widgetId === null) {{ status.textContent = 'The security check is still loading.'; return; }}
          if (!turnstileToken) {{
            status.textContent = 'Please complete the visible security check first.';
            return;
          }}
          button.disabled = true;
          status.textContent = 'Sending…';
          try {{
            const csrfResponse = await fetch('/api/contact/csrf', {{credentials:'same-origin'}});
            const csrf = await csrfResponse.json();
            if (!csrfResponse.ok) throw new Error(csrf.detail || 'Contact service is unavailable.');
            csrfToken = csrf.csrf_token;
            await submitContact(turnstileToken);
          }} catch (error) {{
            status.textContent = error.message;
            resetSubmission();
          }}
        }});
      }})();
    """)
