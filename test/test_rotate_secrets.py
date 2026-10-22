"""Secret rotation tool: no value is ever printed or put on a command line.

A fake Railway CLI stands in for the real one; nothing here reaches Railway.
"""
from __future__ import annotations

import json
import re
import subprocess
import unittest

from ops import rotate_secrets as rs

DB_PASSWORD = "old-db-password-SYNTHETIC"
RESEND = "SYNTHETIC-old-resend-value"
NEW_KEY = "SYNTHETIC-new-provider-value"
# Stored the way Railway stores them: the Postgres template's own values reference
# POSTGRES_PASSWORD; portfolio references Postgres; transit-api holds a pasted copy.
PROJECT = {
    "Postgres": {"POSTGRES_PASSWORD": DB_PASSWORD, "PGPASSWORD": "${{POSTGRES_PASSWORD}}", "PGUSER": "postgres",
                 "DATABASE_URL": "postgresql://postgres:${{POSTGRES_PASSWORD}}@postgres.railway.internal:5432/railway",
                 "DATABASE_PUBLIC_URL": "postgresql://postgres:${{POSTGRES_PASSWORD}}@shuttle.proxy.rlwy.net:41234/railway",
                 "RAILWAY_PRIVATE_DOMAIN": "postgres.railway.internal"},
    "portfolio": {"DATABASE_URL": "${{Postgres.DATABASE_URL}}",
                  "RESEND_API_KEY": RESEND, "CONTACT_TOKEN_PEPPER": "old-pepper-SYNTHETIC",
                  "CONTACT_IP_HASH_KEY": "old-hash-SYNTHETIC", "ANTHROPIC_API_KEY": "sk-ant-SYNTHETIC",
                  "CONTACT_TO_EMAIL": "owner@example.com", "TURNSTILE_SITE_KEY": "0x-site-SYNTHETIC"},
    "transit-api": {"PGPASSWORD": DB_PASSWORD, "PGHOST": "postgres.railway.internal"},
}
VALUES = [v for variables in PROJECT.values() for v in variables.values() if "SYNTHETIC" in v]
REFERENCE = re.compile(r"\$\{\{(?:([\w-]+)\.)?(\w+)\}\}")


class FakeRailway:
    """Lists rendered values (references resolved), like `railway variable list --json`."""

    def __init__(self, project=PROJECT, proxies=("proxy",)):
        self.project = {service: dict(variables) for service, variables in project.items()}
        self.proxies, self.calls = list(proxies), []

    def render(self, service, value):
        return REFERENCE.sub(lambda m: self.render(m[1] or service, self.project[m[1] or service][m[2]]), value)

    def __call__(self, args, stdin=None):
        self.calls.append((list(args), stdin))
        if args[:2] == ["variable", "list"]:
            service = args[args.index("--service") + 1]
            if service not in self.project:
                return subprocess.CompletedProcess(args, 1, "", "service not found")
            rendered = {k: self.render(service, v) for k, v in self.project[service].items()}
            return subprocess.CompletedProcess(args, 0, json.dumps(rendered), "")
        if args[:2] == ["tcp-proxy", "list"]:
            return subprocess.CompletedProcess(args, 0, json.dumps(self.proxies), "")
        if args[:2] == ["variable", "set"]:
            self.project[args[args.index("--service") + 1]][args[2]] = stdin
            return subprocess.CompletedProcess(args, 0, "{}", "")
        return subprocess.CompletedProcess(args, 1, "", "unexpected")

    def sets(self):
        return [(args, stdin) for args, stdin in self.calls if args[:2] == ["variable", "set"]]


class Collect(list):
    def __call__(self, line=""):
        self.append(str(line))

    def text(self):
        return "\n".join(self)


class InventoryTests(unittest.TestCase):
    def test_never_prints_a_value_or_a_host(self):
        out = Collect()
        rs.inventory(FakeRailway(), out)
        for value in VALUES + ["shuttle.proxy.rlwy.net", "owner@example.com"]:
            self.assertNotIn(value, out.text())

    def test_classifies_secrets_exposure_and_unknown_keys(self):
        out = Collect()
        rs.inventory(FakeRailway(), out)
        text = out.text()
        self.assertRegex(text, r"DATABASE_PUBLIC_URL\s+database connection: PUBLIC address")
        self.assertRegex(text, r"DATABASE_URL\s+database connection: private network")
        self.assertRegex(text, r"ANTHROPIC_API_KEY\s+SECRET, NOT IN REGISTRY")
        self.assertRegex(text, r"RESEND_API_KEY\s+secret \(provider\)")
        self.assertRegex(text, r"CONTACT_TO_EMAIL\s+setting")
        self.assertRegex(text, r"TURNSTILE_SITE_KEY\s+setting \(public by design\)")
        self.assertIn("Postgres public TCP proxy: ON", text)
        self.assertIn("transit-poller: not found", text)

    def test_a_railway_token_you_added_is_still_a_secret(self):
        self.assertEqual(rs.classify("RAILWAY_PRIVATE_DOMAIN", "x.railway.internal"), "railway-provided")
        self.assertIn("SECRET", rs.classify("RAILWAY_API_TOKEN", "tok"))

    def test_no_proxy_reads_as_off(self):
        out = Collect()
        rs.inventory(FakeRailway(proxies=()), out)
        self.assertIn("Postgres public TCP proxy: off", out.text())


class RotateTests(unittest.TestCase):
    def rotate(self, *, apply, railway=None, secret_answers=(), answers=("yes",), clipboard=None):
        railway = railway or FakeRailway()
        out = Collect()
        pasted = iter(secret_answers)
        replies = iter(answers)
        clipped = []
        code = rs.rotate(apply=apply, runner=railway, out=out, ask=lambda _p: next(replies, ""),
                         ask_secret=lambda _p: next(pasted, ""),
                         clipboard=clipboard or (lambda text: clipped.append(text) or True))
        return code, railway, out, clipped

    def test_dry_run_writes_nothing(self):
        code, railway, out, clipped = self.rotate(apply=False, secret_answers=[NEW_KEY])
        self.assertEqual(code, 0)
        self.assertEqual(railway.sets(), [])
        self.assertEqual(clipped, [])
        self.assertIn("[dry run] would set CONTACT_TOKEN_PEPPER on portfolio", out.text())

    def test_values_go_on_stdin_never_on_the_command_line_or_screen(self):
        new_key = NEW_KEY
        code, railway, out, clipped = self.rotate(apply=True, secret_answers=[new_key])
        self.assertEqual(code, 0, out.text())
        sets = railway.sets()
        self.assertTrue(sets)
        for args, stdin in sets:
            self.assertIn("--stdin", args)
            self.assertIn("--skip-deploys", args)
            self.assertTrue(stdin)
            self.assertNotIn(stdin, " ".join(args))
            self.assertNotIn(stdin, out.text())
        self.assertIn(("portfolio", "RESEND_API_KEY", new_key),
                      [(a[a.index("--service") + 1], a[2], s) for a, s in sets])

    def test_only_services_that_already_have_the_variable_are_written(self):
        _, railway, _, _ = self.rotate(apply=True, secret_answers=[NEW_KEY])
        written = {(a[a.index("--service") + 1], a[2]) for a, _ in railway.sets() if a[2] in rs.KNOWN}
        self.assertEqual(written, {("Postgres", "POSTGRES_PASSWORD"), ("portfolio", "RESEND_API_KEY"),
                                   ("portfolio", "CONTACT_TOKEN_PEPPER"), ("portfolio", "CONTACT_IP_HASH_KEY")})

    def test_database_password_matches_the_alter_role_and_clipboard_is_cleared(self):
        _, railway, _, clipped = self.rotate(apply=True)
        (staged,) = [s for a, s in railway.sets() if a[2] == "POSTGRES_PASSWORD"]
        self.assertEqual(clipped[0], f"ALTER ROLE postgres WITH PASSWORD '{staged}';")
        self.assertEqual(clipped[-1], "")
        self.assertNotEqual(staged, DB_PASSWORD)

    def test_pasted_copies_become_references_and_the_database_password_goes_last(self):
        code, railway, out, _ = self.rotate(apply=True, secret_answers=[NEW_KEY])
        self.assertEqual(code, 0, out.text())
        writes = [(a[a.index("--service") + 1], a[2], s) for a, s in railway.sets()]
        self.assertIn(("transit-api", "PGPASSWORD", "${{Postgres.PGPASSWORD}}"), writes)
        self.assertIn(("portfolio", "DATABASE_URL", "${{Postgres.DATABASE_URL}}"), writes)
        self.assertEqual(writes[-1][:2], ("Postgres", "POSTGRES_PASSWORD"))
        self.assertLess(writes.index(("transit-api", "PGPASSWORD", "${{Postgres.PGPASSWORD}}")), len(writes) - 1)

    def test_every_connection_is_checked_for_the_new_password(self):
        _, _, out, _ = self.rotate(apply=True)
        for line in ("ok: PGPASSWORD on Postgres", "ok: DATABASE_URL on Postgres",
                     "ok: DATABASE_URL on portfolio", "ok: PGPASSWORD on transit-api"):
            self.assertIn(line, out.text())
        self.assertNotIn("STALE", out.text())

    def test_a_connection_that_differs_is_left_alone_and_flagged(self):
        project = {**PROJECT, "transit-api": {"PGPASSWORD": "another-password-SYNTHETIC"}}
        code, railway, out, _ = self.rotate(apply=True, railway=FakeRailway(project))
        self.assertEqual(code, 1)
        self.assertNotIn("transit-api", [a[a.index("--service") + 1] for a, _ in railway.sets()])
        self.assertIn("PGPASSWORD on transit-api differs from the Postgres service", out.text())
        self.assertIn("STALE: PGPASSWORD on transit-api", out.text())
        self.assertNotIn("another-password-SYNTHETIC", out.text())

    def test_database_password_not_staged_unless_the_owner_confirms(self):
        _, railway, out, clipped = self.rotate(apply=True, answers=("no",))
        self.assertNotIn("POSTGRES_PASSWORD", [a[2] for a, _ in railway.sets()])
        self.assertEqual(clipped[-1], "")
        self.assertIn("database password is unchanged", out.text())

    def test_skipped_and_implausible_keys_are_not_written(self):
        for answer in ("", "short", "has a space in it"):
            with self.subTest(answer=answer):
                _, railway, _, _ = self.rotate(apply=True, secret_answers=[answer])
                self.assertNotIn("RESEND_API_KEY", [a[2] for a, _ in railway.sets()])

    def test_generated_values_are_new_and_long(self):
        _, railway, _, _ = self.rotate(apply=True)
        generated = [s for a, s in railway.sets() if a[2] in ("CONTACT_TOKEN_PEPPER", "CONTACT_IP_HASH_KEY")]
        self.assertEqual(len(set(generated)), 2)
        self.assertTrue(all(len(v) >= 60 for v in generated))

    def test_failed_write_is_reported_without_the_value(self):
        class Failing(FakeRailway):
            def __call__(self, args, stdin=None):
                if args[:2] == ["variable", "set"]:
                    self.calls.append((list(args), stdin))
                    return subprocess.CompletedProcess(args, 1, "", f"rejected value {stdin}")
                return super().__call__(args, stdin)

        code, railway, out, _ = self.rotate(apply=True, railway=Failing(), answers=("no",))
        self.assertEqual(code, 1)
        self.assertIn("FAILED to set CONTACT_TOKEN_PEPPER on portfolio: rejected value ***", out.text())
        for _, stdin in railway.sets():
            self.assertNotIn(stdin, out.text())

    def test_not_signed_in_stops_before_anything(self):
        code, railway, out, _ = self.rotate(apply=True, railway=FakeRailway(project={}))
        self.assertEqual(code, 2)
        self.assertEqual(railway.sets(), [])
        self.assertIn("railway login", out.text())


if __name__ == "__main__":
    unittest.main()
