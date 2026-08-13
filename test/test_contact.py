import asyncio
import os
import time
import unittest
from unittest.mock import Mock, patch

from app.contact.config import ContactSettings, normalize_database_url
from app.contact.models import Base
from app.contact.mail import deliver_contact_message
from app.contact.security import (
    ContactValidationError,
    clean_message,
    keyed_digest,
    new_csrf_token,
    normalize_email,
    verify_csrf_token,
)
from app.contact.service import (
    ContactInput,
    GENERIC_ACCEPTED_MESSAGE,
    accept_contact,
    validate_contact,
)
from app.contact.turnstile import verify_turnstile


class ContactConfigurationTests(unittest.TestCase):
    def test_railway_database_url_is_normalized_for_psycopg2(self):
        self.assertEqual(
            normalize_database_url("postgres://user:pass@db:5432/name"),
            "postgresql+psycopg2://user:pass@db:5432/name",
        )

    def test_missing_configuration_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = ContactSettings.from_env()
        self.assertFalse(settings.configured)
        self.assertIn("TURNSTILE_SECRET_KEY", settings.missing())
        self.assertIn("RESEND_API_KEY", settings.missing())

    def test_models_are_isolated_in_portfolio_schema(self):
        self.assertEqual(Base.metadata.schema, "portfolio")
        self.assertTrue(
            {
                "portfolio.contact_messages",
                "portfolio.contact_attempts",
                "portfolio.contact_audit_events",
            }
            <= set(Base.metadata.tables),
        )


class ContactSecurityTests(unittest.TestCase):
    def test_csrf_token_is_signed_expiring_and_secret_specific(self):
        token = new_csrf_token("correct-secret", now=int(time.time()))
        self.assertTrue(verify_csrf_token(token, "correct-secret"))
        self.assertFalse(verify_csrf_token(token, "wrong-secret"))
        old = new_csrf_token("correct-secret", now=int(time.time()) - 3601)
        self.assertFalse(verify_csrf_token(old, "correct-secret"))

    def test_keyed_hash_does_not_store_raw_identifier(self):
        digest = keyed_digest("203.0.113.5", "private-key")
        self.assertEqual(len(digest), 64)
        self.assertNotIn("203.0.113.5", digest)

    def test_contact_fields_are_normalized_and_bounded(self):
        clean = validate_contact(
            ContactInput(
                name="  Jane   Recruiter ",
                email=" Jane@Example.COM ",
                subject=" Data engineering role ",
                category="job-opportunity",
                message="Hello, I would like to discuss a data engineering opportunity.",
                website="",
                turnstile_token="token",
            )
        )
        self.assertEqual(clean.name, "Jane Recruiter")
        self.assertEqual(clean.email, "jane@example.com")

    def test_invalid_email_category_and_short_message_are_rejected(self):
        with self.assertRaises(ContactValidationError):
            normalize_email("not-an-email")
        with self.assertRaises(ContactValidationError):
            clean_message("too short")
        with self.assertRaises(ContactValidationError):
            validate_contact(
                ContactInput("Jane", "jane@example.com", "Hello", "invalid", "x" * 30, "", "token")
            )

    def test_generic_acceptance_copy_does_not_disclose_address_state(self):
        self.assertNotIn("exists", GENERIC_ACCEPTED_MESSAGE.lower())
        self.assertNotIn("registered", GENERIC_ACCEPTED_MESSAGE.lower())

    def test_honeypot_returns_generic_response_before_external_work(self):
        settings = Mock()
        result = asyncio.run(
            accept_contact(
                ContactInput("Bot", "bad", "x", "invalid", "x", "spam-site", ""),
                remote_ip="203.0.113.5",
                settings=settings,
            )
        )
        self.assertEqual(result, GENERIC_ACCEPTED_MESSAGE)


class ContactMailTests(unittest.TestCase):
    @patch("app.contact.mail.requests.post")
    def test_resend_api_receives_bearer_auth_and_reply_to(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        post.return_value = response
        settings = Mock(
            from_email="portfolio@bizqlab.com",
            to_email="owner@bizqlab.com",
            resend_api_key="re_private",
        )
        deliver_contact_message(
            settings,
            name="Jane Recruiter",
            verified_email="jane@example.com",
            category="job-opportunity",
            subject="Data engineering role",
            body="A sufficiently detailed message body.",
        )
        request = post.call_args
        self.assertEqual(request.kwargs["headers"]["Authorization"], "Bearer re_private")
        self.assertEqual(request.kwargs["json"]["from"], "portfolio@bizqlab.com")
        self.assertEqual(request.kwargs["json"]["reply_to"], "jane@example.com")
        self.assertEqual(request.kwargs["timeout"], 15)

    @patch("app.contact.mail._send")
    def test_verified_sender_is_reply_to_not_from(self, send):
        settings = Mock(
            from_email="portfolio@bizqlab.com",
            to_email="owner@bizqlab.com",
        )
        deliver_contact_message(
            settings,
            name="Jane Recruiter",
            verified_email="jane@example.com",
            category="job-opportunity",
            subject="Data engineering role",
            body="A sufficiently detailed message body.",
        )
        message = send.call_args.args[0]
        self.assertEqual(message["From"], "portfolio@bizqlab.com")
        self.assertEqual(message["Reply-To"], "jane@example.com")


class TurnstileTests(unittest.TestCase):
    @patch("app.contact.turnstile.requests.post")
    def test_requires_success_hostname_and_contact_action(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "success": True,
            "hostname": "bizqlab.com",
            "action": "contact",
        }
        post.return_value = response
        result = verify_turnstile(
            secret="secret",
            token="token",
            remote_ip="203.0.113.5",
            expected_hostnames=("bizqlab.com", "www.bizqlab.com"),
        )
        self.assertTrue(result.success)
        self.assertEqual(post.call_args.kwargs["timeout"], 10)

    @patch("app.contact.turnstile.requests.post")
    def test_rejects_valid_token_for_wrong_hostname(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "success": True,
            "hostname": "attacker.example",
            "action": "contact",
        }
        post.return_value = response
        result = verify_turnstile(
            secret="secret",
            token="token",
            remote_ip="203.0.113.5",
            expected_hostnames=("bizqlab.com", "www.bizqlab.com"),
        )
        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()
