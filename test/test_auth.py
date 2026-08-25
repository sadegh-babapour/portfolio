import os
import unittest
import uuid
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from unittest.mock import MagicMock, patch

from app.auth.api import _uses_public_host, google_login
from app.auth.config import AuthSettings
from app.auth.models import (
    AuthEvent,
    AuthSession,
    ExternalIdentity,
    FavoriteStop,
    OidcLoginState,
    User,
    UserRole,
)
from app.auth.security import new_opaque_token, safe_return_path, token_digest
from app.auth.service import (
    AuthenticationError,
    SessionUser,
    begin_google_login,
    add_favorite_stop,
    consume_login_state,
    require_mutation_session,
    verify_google_identity,
    utc_now,
)


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

    @staticmethod
    def _settings() -> AuthSettings:
        return AuthSettings(
            database_url="postgresql+psycopg2://example",
            public_base_url="https://bizqlab.com",
            google_client_id="client.apps.googleusercontent.com",
            google_client_secret=uuid.uuid4().hex,
            admin_google_subjects=(),
            admin_emails=(),
            session_ttl_hours=12,
            login_state_ttl_minutes=10,
            event_retention_days=90,
        )

    def test_login_start_persists_only_state_nonce_and_browser_digests(self):
        database = MagicMock()
        context = MagicMock()
        context.__enter__.return_value = database
        context.__exit__.return_value = False

        settings = self._settings()
        with patch("app.auth.service.session_scope", return_value=context):
            login = begin_google_login(settings, "/projects#project-calgary")

        query = parse_qs(urlsplit(login.authorization_url).query)
        state = query["state"][0]
        nonce = query["nonce"][0]
        persisted = next(
            call.args[0]
            for call in database.add.call_args_list
            if isinstance(call.args[0], OidcLoginState)
        )
        self.assertEqual(persisted.state_digest, token_digest(state))
        self.assertEqual(persisted.nonce_digest, token_digest(nonce))
        self.assertEqual(persisted.browser_digest, token_digest(login.browser_token))
        self.assertNotIn(settings.google_client_secret, login.authorization_url)
        self.assertEqual(persisted.return_path, "/projects#project-calgary")

    def test_login_start_canonicalizes_origin_before_setting_browser_cookie(self):
        request = MagicMock()
        request.url = "https://www.bizqlab.com/api/auth/google/login"

        with (
            patch("app.auth.api._settings", return_value=self._settings()),
            patch("app.auth.api.begin_google_login") as begin_login,
        ):
            response = google_login(request, "/account")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "https://bizqlab.com/api/auth/google/login?return_to=%2Faccount",
        )
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn("set-cookie", response.headers)
        begin_login.assert_not_called()

        request.url = "http://bizqlab.com/api/auth/google/login"
        self.assertTrue(_uses_public_host(request, self._settings()))

    def test_login_state_is_browser_bound_and_single_use(self):
        now = utc_now()
        login_state = MagicMock(
            state_digest=token_digest("state"),
            nonce_digest=token_digest("nonce"),
            browser_digest=token_digest("browser"),
            return_path="/account",
            expires_at=now + timedelta(minutes=5),
            consumed_at=None,
        )
        database = MagicMock()
        database.scalar.return_value = login_state
        context = MagicMock()
        context.__enter__.return_value = database
        context.__exit__.return_value = False

        with (
            patch("app.auth.service.session_scope", return_value=context),
            patch("app.auth.service.utc_now", return_value=now),
        ):
            consumed = consume_login_state("state", "browser")

        self.assertEqual(consumed.return_path, "/account")
        self.assertEqual(consumed.nonce_digest, token_digest("nonce"))
        self.assertEqual(login_state.consumed_at, now)
        database.commit.assert_called_once_with()

        login_state.consumed_at = now
        with (
            patch("app.auth.service.session_scope", return_value=context),
            patch("app.auth.service.utc_now", return_value=now),
        ):
            with self.assertRaisesRegex(AuthenticationError, "invalid or expired"):
                consume_login_state("state", "browser")

        login_state.consumed_at = None
        with (
            patch("app.auth.service.session_scope", return_value=context),
            patch("app.auth.service.utc_now", return_value=now),
        ):
            with self.assertRaisesRegex(AuthenticationError, "invalid or expired"):
                consume_login_state("state", "different-browser")

    @patch("app.auth.service.google_id_token.verify_oauth2_token")
    def test_google_identity_requires_matching_nonce_and_verified_email(self, verify):
        nonce = new_opaque_token()
        verify.return_value = {
            "sub": "stable-subject",
            "email": "visitor@example.com",
            "email_verified": True,
            "nonce": nonce,
        }
        claims = verify_google_identity(
            "encoded-token", token_digest(nonce), self._settings()
        )
        self.assertEqual(claims["sub"], "stable-subject")

        verify.return_value["email_verified"] = False
        with self.assertRaisesRegex(AuthenticationError, "not verified"):
            verify_google_identity("encoded-token", token_digest(nonce), self._settings())

        verify.return_value["email_verified"] = True
        with self.assertRaisesRegex(AuthenticationError, "nonce"):
            verify_google_identity("encoded-token", token_digest("other"), self._settings())

    def test_auth_mutations_require_matching_session_bound_csrf(self):
        user = SessionUser(
            user_id=uuid.uuid4(),
            display_name="Visitor",
            email="visitor@example.com",
            roles=frozenset({"registered"}),
            session_id=uuid.uuid4(),
            csrf_digest=token_digest("csrf-value"),
        )
        with patch("app.auth.service.current_session", return_value=user):
            self.assertEqual(
                require_mutation_session("session", "csrf-value", "csrf-value"),
                user,
            )
            with self.assertRaises(AuthenticationError):
                require_mutation_session("session", "csrf-value", "different")


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
                FavoriteStop.__table__.fullname,
            },
            {
                "portfolio.users",
                "portfolio.external_identities",
                "portfolio.user_roles",
                "portfolio.auth_sessions",
                "portfolio.oidc_login_states",
                "portfolio.auth_events",
                "portfolio.favorite_stops",
            },
        )

    def test_favorite_stops_store_only_user_and_stop_identifiers(self):
        columns = set(FavoriteStop.__table__.columns.keys())
        self.assertEqual(columns, {"user_id", "stop_id", "created_at"})
        self.assertFalse(any("lat" in column or "lon" in column for column in columns))

        user = SessionUser(
            user_id=uuid.uuid4(),
            display_name="Visitor",
            email="visitor@example.com",
            roles=frozenset({"registered"}),
            session_id=uuid.uuid4(),
            csrf_digest=token_digest("csrf"),
        )
        with self.assertRaisesRegex(ValueError, "invalid"):
            add_favorite_stop(user, "invalid/stop")

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
