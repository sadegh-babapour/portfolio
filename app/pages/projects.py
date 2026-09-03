import logging
from urllib.parse import urlencode

from nicegui import ui

from app.auth.config import AuthSettings
from app.auth.service import SESSION_COOKIE, SessionUser, current_session
from app.components.navbar import with_layout
from app.content import ContentValidationError, ProjectCaseStudy, load_projects


log = logging.getLogger(__name__)


def _bullet_list(items: tuple[str, ...]) -> None:
    with ui.column().classes('gap-2'):
        for item in items:
            with ui.row().classes('items-start gap-2 no-wrap'):
                ui.icon('arrow_right', size='xs').classes('mt-1 text-primary')
                ui.label(item).classes('text-sm')


def _project_lab(
    project: ProjectCaseStudy,
    session_user: SessionUser | None,
    auth_configured: bool,
) -> None:
    if project.lab is None:
        return
    if session_user is not None and "registered" in session_user.roles:
        with ui.expansion(project.lab.heading, icon='science').classes('w-full'):
            ui.label(project.lab.intro).classes('text-sm p-2')
            with ui.column().classes('w-full gap-3 p-2'):
                for technique in project.lab.techniques:
                    with ui.card().classes('w-full p-4 gap-2 border'):
                        ui.label(technique.title).classes('text-lg font-semibold')
                        ui.label(f'Concept — {technique.concept}').classes('text-sm')
                        ui.label(f'Implementation — {technique.implementation}').classes('text-sm')
                        ui.label(f'Trade-off — {technique.tradeoff}').classes('text-sm text-grey-7')
                with ui.card().classes('portfolio-development-note w-full p-4 gap-2').style(
                    'background: #eff6ff; border: 1px solid #93c5fd; color: #1e3a5f;'
                ):
                    ui.label('Development note').classes('font-semibold')
                    ui.label(project.lab.working_method).classes('text-sm')
        return

    with ui.card().classes('w-full p-4 gap-3 border border-dashed'):
        with ui.row().classes('items-center gap-2'):
            ui.icon('lock', color='primary')
            ui.label(project.lab.heading).classes('text-lg font-semibold')
        ui.label(
            'The public case study stays open. Sign in to view the technique notes, '
            'implementation reasoning, trade-offs, and a concise development note.'
        ).classes('text-sm text-grey-7')
        if auth_configured:
            query = urlencode({'return_to': f'/projects#project-{project.id}'})
            ui.link('Continue with Google', f'/api/auth/google/login?{query}').classes(
                'text-primary font-semibold no-underline hover:underline'
            )
        else:
            ui.label('Google sign-in is being configured.').classes('text-sm text-grey-7')


def _project_card(
    project: ProjectCaseStudy,
    session_user: SessionUser | None,
    auth_configured: bool,
) -> None:
    member = session_user is not None and "registered" in session_user.roles
    with ui.card().classes('w-full h-full p-5 gap-4'):
        with ui.row().classes('w-full items-start justify-between gap-3 flex-wrap'):
            with ui.column().classes('gap-1'):
                ui.label(project.title).classes('text-2xl font-semibold')
                ui.label(project.summary).classes('text-base text-grey-7')
            ui.badge(project.status, color='primary' if project.featured else 'grey')

        with ui.row().classes('gap-2 flex-wrap'):
            ui.chip(project.data_mode.replace('_', ' ').title(), icon='database').props('outline')
            if project.lab is not None:
                ui.chip(
                    'Member Lab active' if member else 'Member Lab',
                    icon='lock_open' if member else 'lock',
                ).props('outline')

        if project.outcomes:
            with ui.column().classes('w-full gap-2'):
                ui.label('What this demonstrates').classes('text-sm font-semibold text-grey-7')
                _bullet_list(project.outcomes[:3])

        with ui.expansion('Explore the full case study', icon='unfold_more').classes('w-full'):
            with ui.column().classes('w-full gap-4 p-2'):
                ui.label('Business problem').classes('text-lg font-semibold')
                ui.label(project.problem).classes('text-sm')
                ui.label('Architecture').classes('text-lg font-semibold')
                ui.label(project.architecture).classes('text-sm')
                ui.label('Data sources').classes('text-lg font-semibold')
                _bullet_list(project.data_sources)
                ui.label('Pipeline').classes('text-lg font-semibold')
                _bullet_list(project.pipeline)
                if project.limitations:
                    ui.label('Honest limitations').classes('text-lg font-semibold')
                    _bullet_list(project.limitations)
                with ui.row().classes('gap-2 flex-wrap'):
                    for technology in project.stack:
                        ui.chip(technology).props('dense outline')

                _project_lab(project, session_user, auth_configured)

        if project.links:
            with ui.row().classes('gap-3 mt-auto'):
                for link in project.links:
                    ui.link(link.label, link.url).classes(
                        'text-primary font-semibold no-underline hover:underline'
                    )


@ui.page('/projects')
@with_layout
def projects():
    with ui.column().classes('w-full max-w-7xl mx-auto px-4 py-8 sm:px-8 gap-5'):
        try:
            collection = load_projects()
        except ContentValidationError as exc:
            log.error('Unable to load project content: %s', exc)
            ui.label('Projects are temporarily unavailable.').classes('text-negative')
            return

        ui.label(collection.heading).classes('text-4xl')
        ui.label(collection.intro).classes('text-lg text-grey-7 max-w-4xl')

        settings = AuthSettings.from_env()
        session_user = None
        if settings.configured:
            try:
                request = ui.context.client.request
                session_user = current_session(request.cookies.get(SESSION_COOKIE))
            except Exception:
                log.exception('Unable to read the current authentication session')

        request = ui.context.client.request
        auth_result = request.query_params.get('auth') if request else None
        if auth_result == 'cancelled':
            ui.label('Google sign-in was cancelled. The public case studies remain available.').classes(
                'text-sm text-grey-7'
            )
        elif auth_result == 'failed':
            ui.label('Sign-in could not be completed. Please try again.').classes(
                'text-sm text-negative'
            )

        member = session_user is not None and "registered" in session_user.roles
        with ui.card().classes('w-full p-5 sm:p-6 gap-4 border'):
            with ui.row().classes('w-full items-start justify-between gap-3 flex-wrap'):
                with ui.column().classes('gap-1'):
                    ui.label(
                        'Member extras are active' if member else 'What signing in adds'
                    ).classes('text-2xl font-semibold')
                    ui.label(
                        'Everything needed to assess the projects remains public. A free '
                        'member account adds the deeper implementation layer and saved '
                        'Calgary transit stops.'
                    ).classes('text-sm text-grey-7 max-w-4xl leading-relaxed')
                ui.badge('Signed in' if member else 'Optional', color='positive' if member else 'primary')
            with ui.element('div').classes('grid w-full grid-cols-1 gap-4 md:grid-cols-2'):
                with ui.column().classes('gap-2'):
                    ui.label('Public access').classes('font-semibold')
                    _bullet_list((
                        'Complete project summaries, architecture, pipeline, and limitations',
                        'The live Calgary map and the public analytical dashboard',
                        'Contact and résumé access without an account',
                    ))
                with ui.column().classes('gap-2'):
                    ui.label('Signed-in extras').classes('font-semibold')
                    _bullet_list((
                        'Project Lab implementation techniques and engineering trade-offs',
                        'Concise reviewed development notes for selected projects',
                        'Saved Calgary stop shortcuts tied to your local account',
                    ))
            if not member and settings.configured:
                query = urlencode({'return_to': '/projects'})
                ui.link('Continue with Google', f'/api/auth/google/login?{query}').classes(
                    'text-primary font-semibold no-underline hover:underline'
                )

        with ui.element('div').classes('grid w-full grid-cols-1 gap-5 lg:grid-cols-2'):
            for project in sorted(
                collection.projects,
                key=lambda item: (not item.featured, item.title.lower()),
            ):
                with ui.element('article').props(f'id=project-{project.id}').classes('h-full'):
                    _project_card(project, session_user, settings.configured)

        with ui.card().classes('w-full p-5 border border-dashed'):
            ui.label('How this content is maintained').classes('text-xl font-semibold')
            ui.label(
                'Case-study copy is validated from content/projects.json. '
                'Live service health and account/contact records use PostgreSQL rather '
                'than rewriting deployed JSON files.'
            ).classes('text-sm text-grey-7')
