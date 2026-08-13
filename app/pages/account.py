import logging
from urllib.parse import urlencode

from nicegui import ui

from app.auth.config import AuthSettings
from app.auth.service import SESSION_COOKIE, current_session
from app.components.navbar import with_layout


log = logging.getLogger(__name__)


@ui.page('/account')
@with_layout
def account():
    settings = AuthSettings.from_env()
    request = ui.context.client.request
    user = None
    if settings.configured:
        try:
            user = current_session(request.cookies.get(SESSION_COOKIE))
        except Exception:
            log.exception('Unable to read the account session')

    with ui.column().classes('w-full max-w-3xl mx-auto px-4 py-8 sm:px-8 gap-5'):
        ui.label('Account').classes('text-4xl')
        if user is None:
            ui.label(
                'Public pages do not require an account. Sign in to open registered '
                'Project Lab material.'
            ).classes('text-lg text-grey-7')
            if settings.configured:
                query = urlencode({'return_to': '/account'})
                ui.link('Continue with Google', f'/api/auth/google/login?{query}').classes(
                    'text-primary font-semibold no-underline hover:underline'
                )
            else:
                ui.label('Google sign-in is being configured.').classes('text-sm text-grey-7')
            return

        with ui.card().classes('w-full p-5 gap-3'):
            ui.label(user.display_name).classes('text-2xl font-semibold')
            ui.label(user.email).classes('text-base text-grey-7')
            with ui.row().classes('gap-2'):
                for role in sorted(user.roles):
                    ui.chip(role.title()).props('dense outline')

        ui.label(
            'The portfolio stores your Google stable identifier, verified email, display '
            'name, local roles, and bounded session/login records. It does not store your '
            'Google password or Google access and refresh tokens.'
        ).classes('text-sm text-grey-7')

        with ui.row().classes('gap-3 flex-wrap'):
            ui.button('Sign out', icon='logout').props('id=portfolio-sign-out')
            ui.button('Delete local account', icon='delete', color='negative').props(
                'id=portfolio-delete-account outline'
            )
        ui.label('').props('id=portfolio-account-status').classes('text-sm text-negative')

    ui.run_javascript('''
      (() => {
        const cookie = (name) => document.cookie
          .split('; ')
          .find((entry) => entry.startsWith(`${name}=`))
          ?.split('=')
          .slice(1)
          .join('=');
        const status = document.getElementById('portfolio-account-status');
        const mutate = async (url, method) => {
          const csrf = cookie('portfolio_auth_csrf');
          if (!csrf) throw new Error('Session expired; reload and try again.');
          const response = await fetch(url, {
            method,
            credentials: 'same-origin',
            headers: {'X-CSRF-Token': decodeURIComponent(csrf)},
          });
          if (!response.ok) {
            const body = await response.json().catch(() => ({}));
            throw new Error(body.detail || 'Unable to update the account.');
          }
          window.location.assign(response.url || '/');
        };
        document.getElementById('portfolio-sign-out')?.addEventListener('click', async () => {
          try { await mutate('/api/auth/logout', 'POST'); }
          catch (error) { status.textContent = error.message; }
        });
        document.getElementById('portfolio-delete-account')?.addEventListener('click', async () => {
          if (!window.confirm('Permanently delete your local portfolio account and sessions?')) return;
          try { await mutate('/api/auth/account', 'DELETE'); }
          catch (error) { status.textContent = error.message; }
        });
      })();
    ''')
