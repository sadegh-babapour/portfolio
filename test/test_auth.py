import os
import unittest
from unittest.mock import patch

from app.auth.config import AuthSettings
from app.auth.models import (
    AuthEvent,
    AuthSession,
    ExternalIdentity,
    OidcLoginState,
    User,
    UserRole,
)
from app.auth.security import new_opaque_token, safe_return_path, token_digest


class AuthConfigurationTests(unittest.TestCase):
    def test_auth_fails_closed_without_google_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = AuthSettings.from_env()

        self.assertFalse(settings.configured)
        self.assertIn("GOOGLE_OIDC_CLIENT_ID", settings.missing())
        self.assertIn("GOOGLE_OIDC_CLIENT_SECRET", settings.missing())

    def test_admin_allowlist_prefers_stable_subject_but_accepts_verified_email(self):
        with patch.dict(
            os.environ,
            {
                "AUTH_ADMIN_GOOGLE_SUBJECTS": "google-subject-1",
                "AUTH_ADMIN_EMAILS": "Owner@BizQLab.com",
            },
            clear=True,
        ):
            settings = AuthSettings.from_env()

        self.assertTrue(settings.is_admin_identity("google-subject-1", "other@example.com"))
        self.assertTrue(settings.is_admin_identity("other", "owner@bizqlab.com"))
        self.assertFalse(settings.is_admin_identity("other", "visitor@example.com"))


class AuthSecurityTests(unittest.TestCase):
    def test_tokens_are_random_and_only_digests_need_persistence(self):
        first = new_opaque_token()
        second = new_opaque_token()

        self.assertNotEqual(first, second)
        self.assertEqual(len(token_digest(first)), 64)
        self.assertNotEqual(first, token_digest(first))

    def test_return_path_rejects_external_and_protocol_relative_redirects(self):
        self.assertEqual(safe_return_path("/projects?open=case"), "/projects?open=case")
        self.assertEqual(safe_return_path("https://attacker.example"), "/projects")
        self.assertEqual(safe_return_path("//attacker.example/path"), "/projects")
        self.assertEqual(safe_return_path("/\\attacker.example"), "/projects")
        self.assertEqual(safe_return_path("/projects\r\nX-Test: bad"), "/projects")


class AuthModelTests(unittest.TestCase):
    def test_auth_tables_stay_in_portfolio_schema(self):
        self.assertEqual(
            {
                User.__table__.fullname,
                ExternalIdentity.__table__.fullname,
                UserRole.__table__.fullname,
                AuthSession.__table__.fullname,
                OidcLoginState.__table__.fullname,
                AuthEvent.__table__.fullname,
            },
            {
                "portfolio.users",
                "portfolio.external_identities",
                "portfolio.user_roles",
                "portfolio.auth_sessions",
                "portfolio.oidc_login_states",
                "portfolio.auth_events",
            },
        )

    def test_only_token_digests_are_modeled(self):
        session_columns = set(AuthSession.__table__.columns.keys())
        login_columns = set(OidcLoginState.__table__.columns.keys())

        self.assertIn("token_digest", session_columns)
        self.assertNotIn("token", session_columns)
        self.assertEqual(
            {"state_digest", "nonce_digest", "browser_digest"} & login_columns,
            {"state_digest", "nonce_digest", "browser_digest"},
        )


if __name__ == "__main__":
    unittest.main()
