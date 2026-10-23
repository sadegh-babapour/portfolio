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
        ui.label('Account').classes('text-4xl sm:text-5xl font-bold')
        if user is None:
            with ui.card().classes('w-full max-w-xl p-6 sm:p-8 gap-4'):
                ui.label('Sign in').classes('text-2xl font-semibold')
                ui.label(
                    'Everything on the site is public. Sign in to read the build notes '
                    'and save transit stops.'
                ).classes('text-base text-grey-7 leading-relaxed')
                if settings.configured:
                    query = urlencode({'return_to': '/account'})
                    ui.button('Sign in with Google', icon='login').props(
                        f'unelevated no-caps href="/api/auth/google/login?{query}"'
                    )
                else:
                    ui.label('Sign-in is not available yet.').classes('text-sm text-grey-7')
                ui.link('How account data is used', '/privacy').classes(
                    'text-sm text-primary no-underline hover:underline'
                )
            return

        with ui.card().classes('w-full p-6 sm:p-8 gap-4 border'):
            with ui.row().classes('items-center gap-3 flex-wrap'):
                ui.icon('verified_user', size='md').classes('text-positive')
                ui.label(f'Welcome, {user.display_name}').classes('text-2xl font-semibold')
                ui.badge('Signed in with Google', color='positive').props('outline')
            ui.label(user.email).classes('text-base text-grey-7')
            with ui.row().classes('items-center gap-2 flex-wrap'):
                ui.label('Access:').classes('text-sm text-grey-7')
                for role in sorted(user.roles):
                    ui.chip(role.title()).props('dense outline')

        with ui.element('section').classes('grid w-full grid-cols-1 gap-5 md:grid-cols-2'):
            with ui.card().classes('w-full h-full p-5 gap-3'):
                ui.icon('science', size='md').classes('text-primary')
                ui.label('Build notes').classes('text-xl font-semibold')
                ui.label(
                    'Open under the Calgary Transit project.'
                ).classes('text-sm text-grey-7 leading-relaxed')
                ui.link('Read the build notes', '/projects#project-calgary-transit-live').classes(
                    'text-primary font-semibold no-underline hover:underline'
                )

            with ui.card().classes('w-full h-full p-5 gap-3'):
                ui.icon('privacy_tip', size='md').classes('text-primary')
                ui.label('Your data').classes('text-xl font-semibold')
                ui.label(
                    'Stored: your Google ID, verified email, name, roles and sign-in records. '
                    'Never your Google password or tokens.'
                ).classes('text-sm text-grey-7 leading-relaxed')
                ui.link('Read the privacy notice', '/privacy').classes(
                    'text-primary font-semibold no-underline hover:underline'
                )

            if 'admin' in user.roles:
                with ui.card().classes('w-full h-full p-5 gap-3'):
                    ui.icon('monitor_heart', size='md').classes('text-primary')
                    ui.label('Admin').classes('text-xl font-semibold')
                    ui.label(
                        'Traffic, accounts, messages and feed health.'
                    ).classes('text-sm text-grey-7 leading-relaxed')
                    ui.link('Open admin', '/admin').classes(
                        'text-primary font-semibold no-underline hover:underline'
                    )

        ui.button('Sign out', icon='logout').props('no-caps id=portfolio-sign-out')
        with ui.expansion('Delete my account', icon='manage_accounts').classes('w-full'):
            with ui.column().classes('w-full gap-3 p-3'):
                ui.label(
                    'Send a request through Contact. I confirm it with you first and reply '
                    'within three business days.'
                ).classes('text-sm text-grey-7 leading-relaxed')
                ui.link(
                    'Request account deletion',
                    '/contact?topic=account-deletion',
                ).classes('text-primary font-semibold no-underline hover:underline')
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
      })();
    ''')
