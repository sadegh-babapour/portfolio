import logging

from nicegui import ui

from app.components.navbar import with_layout
from app.content import ContentValidationError, ProjectCaseStudy, load_projects


log = logging.getLogger(__name__)


def _bullet_list(items: tuple[str, ...]) -> None:
    with ui.column().classes('gap-2'):
        for item in items:
            with ui.row().classes('items-start gap-2 no-wrap'):
                ui.icon('arrow_right', size='xs').classes('mt-1 text-primary')
                ui.label(item).classes('text-sm')


def _project_card(project: ProjectCaseStudy) -> None:
    with ui.card().classes('w-full h-full p-5 gap-4'):
        with ui.row().classes('w-full items-start justify-between gap-3 no-wrap'):
            with ui.column().classes('gap-1'):
                ui.label(project.title).classes('text-2xl font-semibold')
                ui.label(project.summary).classes('text-base text-grey-7')
            ui.badge(project.status, color='primary' if project.featured else 'grey')

        with ui.row().classes('gap-2 flex-wrap'):
            ui.chip(project.data_mode.replace('_', ' ').title(), icon='database').props('outline')
            if project.visibility == 'registered':
                ui.chip('Sign-in content', icon='lock').props('outline')
            for technology in project.stack:
                ui.chip(technology).props('dense outline')

        with ui.expansion('Business problem', icon='target').classes('w-full'):
            ui.label(project.problem).classes('text-sm p-2')
        with ui.expansion('Architecture', icon='account_tree').classes('w-full'):
            ui.label(project.architecture).classes('text-sm p-2')
        with ui.expansion('Data sources', icon='source').classes('w-full'):
            _bullet_list(project.data_sources)
        with ui.expansion('Pipeline', icon='schema').classes('w-full'):
            _bullet_list(project.pipeline)
        if project.outcomes:
            with ui.expansion('Outcomes', icon='check_circle').classes('w-full'):
                _bullet_list(project.outcomes)
        if project.limitations:
            with ui.expansion('Limitations', icon='info').classes('w-full'):
                _bullet_list(project.limitations)

        if project.links:
            with ui.row().classes('gap-3 mt-auto'):
                for link in project.links:
                    ui.link(link.label, link.url).classes(
                        'text-primary font-semibold no-underline hover:underline'
                    )


@ui.page('/projects')
@with_layout
def projects():
    with ui.column().classes('w-full max-w-7xl mx-auto p-4 sm:p-8 gap-5'):
        try:
            collection = load_projects()
        except ContentValidationError as exc:
            log.error('Unable to load project content: %s', exc)
            ui.label('Projects are temporarily unavailable.').classes('text-negative')
            return

        ui.label(collection.heading).classes('text-4xl')
        ui.label(collection.intro).classes('text-lg text-grey-7 max-w-4xl')

        with ui.element('div').classes('grid w-full grid-cols-1 gap-5 lg:grid-cols-2'):
            for project in sorted(
                collection.projects,
                key=lambda item: (not item.featured, item.title.lower()),
            ):
                _project_card(project)

        with ui.card().classes('w-full p-5 border border-dashed'):
            ui.label('How this content is maintained').classes('text-xl font-semibold')
            ui.label(
                'Case-study copy is validated from content/projects.json. '
                'Live service health and editable admin records will use the future '
                'portfolio database schema instead of rewriting deployed JSON files.'
            ).classes('text-sm text-grey-7')
