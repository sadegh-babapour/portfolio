from contextlib import contextmanager

from nicegui import ui

from app.components.navbar import with_layout


@contextmanager
def _legal_shell(title: str, updated: str):
    with ui.column().classes('w-full max-w-4xl mx-auto px-4 py-8 sm:px-8 gap-5'):
        ui.label(title).classes('text-4xl')
        ui.label(f'Last updated: {updated}').classes('text-sm text-grey-7')
        yield


def _section(title: str, paragraphs: tuple[str, ...]) -> None:
    with ui.column().classes('w-full gap-2'):
        ui.label(title).classes('text-2xl font-semibold')
        for paragraph in paragraphs:
            ui.label(paragraph).classes('text-base leading-relaxed')


@ui.page('/privacy')
@with_layout
def privacy():
    with _legal_shell('Privacy', 'September 2, 2026'):
        _section(
            'What this site collects',
            (
                'Public browsing does not require an account. If you choose Google sign-in, '
                'the portfolio stores your Google account’s stable identifier, verified email '
                'address, display name, local roles, session records, and bounded login events.',
                'The portfolio does not store your Google password, Google access token, or '
                'Google refresh token. Session and login secrets are stored only as digests.',
                'If you use the contact form, the site processes the information you submit and '
                'short-lived anti-abuse data needed to verify and deliver the message.',
                'The site counts renders of a fixed list of public pages for operational '
                'reporting. These records contain only the page path and time. They do not '
                'contain an IP address, account or cookie identifier, device fingerprint, '
                'referrer, or query string, and they are not unique-visitor counts.',
                'The Calgary Transit page requests your location only after you choose '
                '“Near me.” Coordinates are used for that nearby-stop request and '
                'are not stored by Bizqlab. If you are signed in and save a stop, the site '
                'stores only that transit stop identifier with your local account.',
            ),
        )
        _section(
            'Why the data is used',
            (
                'Identity data creates and secures your local account, unlocks Project Lab '
                'material, supports sign-out and reviewed account-deletion requests, and helps investigate '
                'authentication failures or abuse.',
                'The site does not sell personal information or use Google identity data for '
                'advertising.',
            ),
        )
        _section(
            'Service providers and retention',
            (
                'Google provides authentication. Railway hosts the application and PostgreSQL. '
                'Cloudflare Turnstile provides contact-form bot defense, and Resend delivers '
                'contact email. Each provider processes limited data under its own terms.',
                'Login attempts expire after approximately 10 minutes, application sessions '
                'after approximately 12 hours, and bounded authentication events after '
                'approximately 90 days. Anonymous page-render records are also deleted after '
                'approximately 90 days. Account identity records remain until a verified '
                'removal request is completed. Saved stop identifiers remain until you remove '
                'them or the associated account is deleted.',
            ),
        )
        _section(
            'Your choices',
            (
                'You can browse the public portfolio without signing in. Signed-in users can '
                'sign out from the Account page. Account deletion and other privacy requests '
                'use the verified Contact workflow; Bizqlab responds within three business days.',
            ),
        )


@ui.page('/terms')
@with_layout
def terms():
    with _legal_shell('Terms', 'August 13, 2026'):
        _section(
            'Portfolio purpose',
            (
                'This site is an educational and professional portfolio. Project descriptions, '
                'demonstrations, datasets, and Project Lab notes are provided for informational '
                'purposes and may change as the work evolves.',
            ),
        )
        _section(
            'Accounts and acceptable use',
            (
                'Google sign-in creates a local registered-user account on first use. You are '
                'responsible for access to the Google account you use. Do not attempt to bypass '
                'access controls, disrupt the service, automate abusive traffic, or misuse '
                'contact and account features.',
                'Access may be limited or revoked to protect the portfolio, its users, or its '
                'infrastructure.',
            ),
        )
        _section(
            'Data and external services',
            (
                'Third-party and public data remains subject to its source licence and '
                'attribution. Live demonstrations can be delayed, incomplete, or unavailable '
                'and must not be relied on for travel, safety, financial, or legal decisions.',
                'Links and integrations operated by Google, Calgary, Railway, Cloudflare, '
                'Resend, map providers, or other third parties are governed by their own terms.',
            ),
        )
        _section(
            'No warranty',
            (
                'The site is provided as available without a promise that every demonstration '
                'will be uninterrupted or error-free. Nothing on the site creates a client, '
                'employment, advisory, or other professional relationship.',
            ),
        )
        _section(
            'Questions',
            ('Questions about these terms can be sent through the Contact page.',),
        )
