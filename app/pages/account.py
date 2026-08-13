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

    with ui.column().classes('w-full max-w-5xl mx-auto px-4 py-8 sm:px-8 gap-6'):
        ui.label('Account').classes('text-4xl')
        if user is None:
            with ui.card().classes('w-full p-6 sm:p-8 gap-4 border'):
                with ui.row().classes('items-center gap-3 flex-wrap'):
                    ui.icon('public', size='md').classes('text-primary')
                    ui.label('Guest access').classes('text-2xl font-semibold')
                    ui.badge('Signed out', color='grey').props('outline')
                ui.label(
                    'You can browse the public portfolio, case studies, dashboard, and live '
                    'transit demonstration without an account.'
                ).classes('text-base text-grey-7 leading-relaxed')
                ui.label(
                    'Google sign-in creates a local registered account and unlocks the '
                    'Project Lab technique notes attached to selected case studies.'
                ).classes('text-sm text-grey-7 leading-relaxed')
                if settings.configured:
                    query = urlencode({'return_to': '/account'})
                    ui.link('Continue with Google', f'/api/auth/google/login?{query}').classes(
                        'text-primary font-semibold no-underline hover:underline'
                    )
                else:
                    ui.label('Google sign-in is being configured.').classes('text-sm text-grey-7')
            return

        with ui.card().classes('w-full p-6 sm:p-8 gap-4 border'):
            with ui.row().classes('items-center gap-3 flex-wrap'):
                ui.icon('verified_user', size='md').classes('text-positive')
                ui.label(f'Welcome, {user.display_name}').classes('text-2xl font-semibold')
                ui.badge('Signed in with Google', color='positive').props('outline')
            ui.label(user.email).classes('text-base text-grey-7')
            with ui.row().classes('items-center gap-2 flex-wrap'):
                ui.label('Local access:').classes('text-sm text-grey-7')
                for role in sorted(user.roles):
                    ui.chip(role.title()).props('dense outline')

        with ui.element('section').classes('grid w-full grid-cols-1 gap-5 md:grid-cols-2'):
            with ui.card().classes('w-full h-full p-5 gap-3'):
                ui.icon('science', size='md').classes('text-primary')
                ui.label('Member access is active').classes('text-xl font-semibold')
                ui.label(
                    'Your registered role unlocks the Calgary Transit Project Lab, including '
                    'implementation techniques, engineering trade-offs, and the development note.'
                ).classes('text-sm text-grey-7 leading-relaxed')
                ui.link('Open the Project Lab', '/projects#project-calgary-transit-live').classes(
                    'text-primary font-semibold no-underline hover:underline'
                )

            with ui.card().classes('w-full h-full p-5 gap-3'):
                ui.icon('privacy_tip', size='md').classes('text-primary')
                ui.label('Account and privacy').classes('text-xl font-semibold')
                ui.label(
                    'Bizqlab stores your Google stable identifier, verified email, display '
                    'name, local roles, and bounded session/login records. It never stores '
                    'your Google password or Google access and refresh tokens.'
                ).classes('text-sm text-grey-7 leading-relaxed')
                ui.link('Read the privacy notice', '/privacy').classes(
                    'text-primary font-semibold no-underline hover:underline'
                )

        ui.label('Account controls').classes('text-xl font-semibold mt-2')
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
