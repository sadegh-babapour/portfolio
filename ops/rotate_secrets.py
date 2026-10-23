#!/usr/bin/env python3
"""Rotate the secrets kept in Railway variables, without ever showing a value.

Written after Railway's 2026-10-21 disclosure that customer variables may have been
read. Run by the owner, signed in to the Railway CLI (`railway login`, then
`railway link` to this project). Standard library only.

  make secrets-plan         the ordered runbook (offline; no Railway needed)
  make secrets-inventory    live variable names per service, classified (names only)
  make rotate-secrets       walk the runbook and stage new values (a dry run)
  make rotate-secrets APPLY=1   the same, writing to Railway

What it never does:
- print a value, or pass one on a command line (values go to the CLI on stdin);
- create a variable that a service does not already have;
- deploy: every write uses --skip-deploys, so all services are redeployed once, together;
- connect to a database: you run the ALTER ROLE yourself, inside the Postgres service.
"""
from __future__ import annotations

import argparse
import getpass
import json
import re
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

# The live Railway services (sec-research-refresh was deleted on 2026-10-21).
SERVICES = ("Postgres", "portfolio", "transit-api", "transit-poller")
SECRET_NAME = re.compile(
    r"(SECRET|PASSWORD|PASSWD|TOKEN|PEPPER|API_KEY|PRIVATE_KEY|_KEY$|CREDENTIAL|DATABASE_URL|DATABASE_PUBLIC_URL|_DSN$)")
# Look secret by name, but are public by design: sent to every visitor's browser.
PUBLIC = {"TURNSTILE_SITE_KEY", "GOOGLE_OIDC_CLIENT_ID"}


@dataclass(frozen=True)
class Secret:
    name: str
    kind: str      # generated | provider | database | derived
    impact: str    # what changes for users once the new value is live
    how: str       # where the new value comes from


# In the order to handle them: worst exposure first.
REGISTRY = (
    Secret("POSTGRES_PASSWORD", "database",
           "Every service reconnects with the new password after the redeploy.",
           "Handled last, just before the redeploy. The tool copies an ALTER ROLE statement to your "
           "clipboard; you run it inside the database (`railway ssh --service Postgres`, then `psql -n`), "
           "and the tool stages the same value. It then checks every service will connect with it."),
    Secret("RESEND_API_KEY", "provider",
           "Contact-form email stops between revoking the old key and the redeploy.",
           "resend.com → API Keys: create a new key (sending access, your domain), then delete the old one."),
    Secret("GOOGLE_OIDC_CLIENT_SECRET", "provider",
           "Google sign-in fails between disabling the old secret and the redeploy.",
           "console.cloud.google.com → APIs & Services → Credentials → the OAuth client → "
           "Add secret; disable and delete the old one after the redeploy."),
    Secret("TURNSTILE_SECRET_KEY", "provider",
           "The contact form's bot check fails between rotating and the redeploy.",
           "dash.cloudflare.com → Turnstile → the widget → Rotate secret key."),
    Secret("SMTP_PASSWORD", "provider",
           "Email over SMTP stops until the redeploy.",
           "Your mail provider's SMTP or app-password page."),
    Secret("CONTACT_TOKEN_PEPPER", "generated",
           "Unconfirmed contact-form verification links and open form tokens stop working; "
           "people resubmit.", "Generated here."),
    Secret("CONTACT_IP_HASH_KEY", "generated",
           "Rate-limit and duplicate checks start fresh (old hashes no longer match).",
           "Generated here."),
)
KNOWN = {s.name: s for s in REGISTRY}
DERIVED = ("DATABASE_URL", "DATABASE_PUBLIC_URL", "PGPASSWORD", "PGUSER", "PGHOST", "PGPORT", "PGDATABASE")
# The connection values that carry the password. Other services should take them from the
# Postgres service by reference (${{Postgres.PGPASSWORD}}), so a new password reaches them too;
# a pasted copy keeps the old password and fails after the redeploy.
LINKED = ("DATABASE_URL", "PGPASSWORD")


def run_railway(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["railway", *args], input=stdin, capture_output=True, text=True, check=False, timeout=60)


def list_variables(service: str, runner=run_railway) -> dict[str, str | None] | None:
    """{name: value} for a service, or None if the service is not in the linked project.

    The values stay in this process: they are only inspected, never printed.
    """
    result = runner(["variable", "list", "--service", service, "--json"])
    if result.returncode != 0:
        return None
    data = json.loads(result.stdout or "{}")
    if isinstance(data, list):  # tolerate a [{name, value}] shape
        data = {item.get("name"): item.get("value") for item in data if isinstance(item, dict)}
    return {k: v for k, v in data.items() if isinstance(k, str)}


def classify(name: str, value: str | None) -> str:
    if name.startswith("RAILWAY_") and not re.search(r"TOKEN|SECRET|PASSWORD|KEY", name):
        return "railway-provided"  # set by Railway itself (domains, IDs); a RAILWAY_*_TOKEN you added is not
    if name in PUBLIC:
        return "setting (public by design)"
    if name in KNOWN:
        return f"secret ({KNOWN[name].kind})"
    if name in DERIVED:
        return "database connection" + _database_host_note(value)
    if SECRET_NAME.search(name):
        return "SECRET, NOT IN REGISTRY: rotate it at its provider"
    return "setting"


def _database_host_note(value: str | None) -> str:
    """Whether a connection value points inside Railway's private network. Never the host itself."""
    if not value or "://" not in value:
        return ""
    host = urlsplit(value).hostname or ""
    if host.endswith(".railway.internal"):
        return ": private network"
    return ": PUBLIC address (reachable from the internet)"


def tcp_proxy_state(runner=run_railway) -> str:
    result = runner(["tcp-proxy", "list", "--service", "Postgres", "--json"])
    if result.returncode != 0:
        return "unknown (could not list TCP proxies)"
    try:
        data = json.loads(result.stdout or "[]")
    except ValueError:
        return "unknown (unexpected output)"
    if isinstance(data, dict):
        data = data.get("proxies") or data.get("tcpProxies") or ([] if not data else [data])
    return ("ON: the database accepts connections from the internet" if data
            else "off: reachable only inside Railway")


def inventory(runner=run_railway, out=print) -> dict[str, dict[str, str | None]]:
    found = {}
    for service in SERVICES:
        variables = list_variables(service, runner)
        if variables is None:
            out(f"{service}: not found in the linked project (or not signed in)")
            continue
        found[service] = variables
        out(f"{service}:")
        for name in sorted(variables):
            out(f"  {name:<34} {classify(name, variables[name])}")
    out(f"Postgres public TCP proxy: {tcp_proxy_state(runner)}")
    return found


def stage(service: str, name: str, value: str, *, apply: bool, runner=run_railway, out=print) -> bool:
    if not apply:
        out(f"  [dry run] would set {name} on {service} (value hidden, --skip-deploys)")
        return True
    result = runner(["variable", "set", name, "--stdin", "--skip-deploys", "--service", service], stdin=value)
    if result.returncode == 0:
        out(f"  set {name} on {service} (not deployed yet)")
        return True
    message = (result.stderr or result.stdout or "").strip().splitlines()[:1]
    out(f"  FAILED to set {name} on {service}: {(message[0] if message else 'no message').replace(value, '***')}")
    return False


def link_to_postgres(found: dict[str, dict[str, str | None]], *, apply: bool, runner=run_railway,
                     out=print) -> int:
    """Replace pasted copies of the Postgres password values with references. Returns failed writes.

    Only where the current value equals the Postgres service's own, so nothing changes in
    behaviour until the password itself does.
    """
    postgres = found.get("Postgres", {})
    failures = 0
    for service, variables in found.items():
        if service == "Postgres":
            continue
        for name in LINKED:
            if name not in variables:
                continue
            if not postgres.get(name) or variables[name] != postgres[name]:
                out(f"  {name} on {service} differs from the Postgres service: left alone, check it by hand")
                continue
            if not stage(service, name, "${{Postgres.%s}}" % name, apply=apply, runner=runner, out=out):
                failures += 1
    return failures


def _password_in(name: str, value: str | None) -> str | None:
    if not value:
        return None
    if name == "PGPASSWORD":
        return value
    return unquote(urlsplit(value).password or "") or None if "://" in value else None


def check_database_password(password: str, *, runner=run_railway, out=print) -> int:
    """Re-read every service: does each connection value now carry the new password? Returns the misses."""
    misses = 0
    for service in SERVICES:
        variables = list_variables(service, runner) or {}
        for name in LINKED:
            if name not in variables:
                continue
            if _password_in(name, variables[name]) == password:
                out(f"  ok: {name} on {service} has the new password")
            else:
                misses += 1
                out(f"  STALE: {name} on {service} has a different password; it will fail after the redeploy")
    if misses:
        out("  If even the Postgres service's own values are STALE, Railway may show new values only after")
        out("  a deploy: open each service's Variables tab and confirm they reference the Postgres service.")
    return misses


def new_value() -> str:
    return secrets.token_urlsafe(48)


def copy_to_clipboard(text: str) -> bool:
    if not shutil.which("pbcopy"):
        return False
    return subprocess.run(["pbcopy"], input=text, text=True, check=False).returncode == 0


def rotate(*, apply: bool, runner=run_railway, out=print, ask=input, ask_secret=getpass.getpass,
           clipboard=copy_to_clipboard) -> int:
    out("Reading the current variable names (values are never shown) ...")
    found = inventory(runner, out)
    if not found:
        out("Nothing found. Run `railway login`, then `railway link` in this folder, and try again.")
        return 2
    out("")
    staged: list[tuple[str, str]] = []
    out("── Database connections: other services take them from the Postgres service by reference")
    failures = link_to_postgres(found, apply=apply, runner=runner, out=out)
    out("")
    # The database password goes last: once ALTER ROLE runs, new connections need the redeploy.
    database_password = None
    for secret in sorted(REGISTRY, key=lambda s: s.kind == "database"):
        holders = [svc for svc, variables in found.items() if secret.name in variables]
        if not holders:
            if secret.kind == "database" and "Postgres" in found:
                out(f"── {secret.name}: not found on the Postgres service; rotate the database password by hand.")
                out("")
            continue
        out(f"── {secret.name}  ({', '.join(holders)})")
        out(f"   Where the new value comes from: {secret.how}")
        out(f"   Effect: {secret.impact}")
        if secret.kind == "generated":
            value = new_value()
        elif secret.kind == "database":
            value = new_value()
            role = (found.get("Postgres", {}).get("PGUSER") or "postgres")
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", role):
                out("   The database role name is unusual; do this one by hand.")
                continue
            if not apply:
                out("  [dry run] would copy ALTER ROLE ... PASSWORD '<new>' to the clipboard, wait for you, then stage it")
                continue
            if not clipboard(f"ALTER ROLE {role} WITH PASSWORD '{value}';"):
                out("   Could not use the clipboard; do this one by hand.")
                continue
            out("   The ALTER ROLE statement is on your clipboard. In a second terminal, in this folder:")
            out("     railway ssh --service Postgres")
            out("     psql -n          (-n: the statement is not saved in psql's history)")
            out("   Paste, press Enter, expect ALTER ROLE, then \\q and exit. Come back here.")
            if ask("   Did it succeed? Type yes to stage the same password in Railway: ").strip() != "yes":
                out("   Skipped. The database password is unchanged unless you ran the statement.")
                clipboard("")
                continue
            clipboard("")
            database_password = value
        else:
            value = ask_secret("   Paste the new value (hidden), or press Enter to skip: ").strip()
            if not value:
                out("   Skipped.")
                continue
            if len(value) < 8 or any(c.isspace() for c in value):
                out("   That does not look like a key (too short or contains spaces). Skipped.")
                continue
        for service in holders:
            if stage(service, secret.name, value, apply=apply, runner=runner, out=out):
                staged.append((service, secret.name))
            else:
                failures += 1
        out("")

    if apply and database_password and ("Postgres", "POSTGRES_PASSWORD") in staged:
        out("── Check: every service connects with the new database password")
        failures += check_database_password(database_password, runner=runner, out=out)
        out("")

    out("Summary:")
    for service, name in staged:
        out(f"  {'staged' if apply else 'would stage'}: {name} on {service}")
    services = sorted({svc for svc, _ in staged} | {svc for svc, variables in found.items()
                                                    if any(name in variables for name in LINKED)})
    out("")
    out("Next, straight away" + (" (the database already uses the new password)" if database_password else "") + ":")
    out(f"  1. Redeploy, together: {', '.join(services) if staged else '(nothing staged)'}.")
    out("  2. Check: home page, /calgary-transit-live/, Google sign-in, a contact-form test message.")
    out("  3. At each provider, delete or disable the OLD keys you replaced.")
    return 1 if failures else 0


PLAN = """\
Secret rotation runbook (first written for Railway's 2026-10-21 disclosure). Run each step yourself.

CONTAIN FIRST (no redeploy needed)
 1. Sign in: `railway login`, then `railway link` in this folder.
 2. `make secrets-inventory`: names only. It shows every secret per service, any secret
    the registry does not know, and whether the database is reachable from the internet.
 3. If the Postgres public TCP proxy is ON and no service uses a PUBLIC database address,
    remove it (Postgres service → Settings → Networking). Anyone holding a leaked
    password is shut out at once.
 4. Revoke the keys a stranger could abuse today (Resend: email sent as your domain).
    Create the replacements now; the rotation asks for them.
 5. Look for misuse:
    - Resend logs: emails you did not send.
    - Google Cloud: OAuth client changes.
    - Postgres (`railway ssh --service Postgres`, then `psql -n`):
        select usename, client_addr, backend_start from pg_stat_activity;
        select rolname, rolcreaterole, rolsuper from pg_roles where rolname !~ '^pg_';
      Expect only your services, on private addresses, and the roles you know.
    - Postgres logs in the dashboard: search "authentication failed".

ROTATE (needs Railway deploys to work)
 6. `make rotate-secrets` (dry run), then `make rotate-secrets APPLY=1`. In order, it:
    - points other services' DATABASE_URL / PGPASSWORD at the Postgres service by reference;
    - asks for each new provider key (hidden) and generates the internal keys;
    - last, the database password: ALTER ROLE, stage, then check every service has it.
    Everything is staged without deploying.
 7. Redeploy the services it lists, at once, and run the checks it prints.
 8. Delete or disable the OLD keys at each provider.

OUTSIDE RAILWAY
 - AI agents: only keys that were stored in Railway were exposed. A browser (subscription)
   login lives on your own machine; re-login is optional hygiene (`/logout` + `/login`;
   `codex logout` + `codex login`).
 - GitHub: review Settings → Security log and Applications (Railway's GitHub app); revoke
   personal access tokens you don't recognise or no longer need.
 - Your PC's database password (.env.local) was never in Railway: not affected.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("plan")
    sub.add_parser("inventory")
    rotate_parser = sub.add_parser("rotate")
    rotate_parser.add_argument("--apply", action="store_true", help="write to Railway (default: dry run)")
    args = parser.parse_args(argv)
    if args.action == "plan":
        print(PLAN)
        return 0
    if not shutil.which("railway"):
        print("The Railway CLI is not installed (brew install railway).", file=sys.stderr)
        return 2
    if args.action == "inventory":
        return 0 if inventory() else 2
    return rotate(apply=args.apply)


if __name__ == "__main__":
    raise SystemExit(main())
