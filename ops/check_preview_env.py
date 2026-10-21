#!/usr/bin/env python3
"""Validate a preview service's own environment against owner-approved preview targets.

A valid build attestation proves which Railway service and environment an artifact
was built for; it does not prove that the service's database variables point at
the disposable preview database. Run this inside each preview service (for example
before its start or pre-deploy command), with an owner-written, non-secret file of
approved targets (see ops/preview-approved.example.json):

  python ops/check_preview_env.py --service portfolio --approved <approved.json>

Checks (names and codes only are printed, never values):
- the Railway environment is the approved preview environment, not production;
- the database target the service's driver would actually use names the approved
  preview host, port, database and role, and no public proxy host:
  - portfolio (web and its Alembic pre-deploy): DATABASE_URL, normalized as
    app/contact/config.py does, parsed strictly and confirmed by libpq's own
    parser (offline). Query parameters that could redirect libpq (host, hostaddr,
    port, dbname, user, service, options, ...), duplicates and malformed URLs are
    refused, and so is any PG* variable, which libpq would read as a fallback;
  - transit-api: PGHOST/PGPORT/PGDATABASE/PGUSER as db/pool.js passes them to pg
    (pg ignores DATABASE_URL); PG* variables pg would read beyond the allowed set
    are refused;
- services that write on startup are excluded from automatic preview startup: the
  poller (it applies migrations before reading its polling controls) and the SEC
  refresh. Deliberate preview runs of either need separately approved write scope;
- external email and sign-in side effects are not configured;
- the portfolio's browser bundle target is the approved preview API.
Missing approval information blocks the preview (exit 1). Read-only; connects to nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    # `python ops/check_preview_env.py` puts ops/ first on sys.path.
    sys.path.insert(0, str(ROOT))

from app import runtime_env as rt  # noqa: E402
from app.contact.config import normalize_database_url  # noqa: E402

SERVICES = ("portfolio", "transit-api", "transit-poller", "sec-research-refresh")
EXCLUDED = {
    "transit-poller": "poller_excluded_from_preview",
    "sec-research-refresh": "sec_refresh_excluded_from_preview",
}
# Variables pg reads for the transit API's connection; any other PG* is refused.
PG_ALLOWED = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGSSLMODE", "PGCONNECT_TIMEOUT", "PGAPPNAME")
APPROVED_KEYS = ("environment_id", "production_environment_id", "database", "api_base")
DATABASE_KEYS = ("host", "port", "name", "role")
SIDE_EFFECT_KEYS = ("RESEND_API_KEY", "GOOGLE_OIDC_CLIENT_ID", "GOOGLE_OIDC_CLIENT_SECRET", "SMTP_PASSWORD")
PUBLIC_PROXY_SUFFIXES = ("proxy.rlwy.net",)


def load_approved(path: Path) -> tuple[dict | None, list[str]]:
    """The owner's approved targets, or coded refusals. Shapes are checked before any field is used."""
    try:
        approved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return None, ["approved_targets_missing_or_unreadable"]
    if not isinstance(approved, dict):
        return None, ["approved_targets_not_an_object"]
    problems = []
    for key in ("environment_id", "production_environment_id", "api_base"):
        problems += _field_problems(approved.get(key), key)
    database = approved.get("database")
    if database is None or database == {}:
        problems.append("approved_key_missing [key=database]")
    elif not isinstance(database, dict):
        problems.append("approved_key_invalid_type [key=database]")
    else:
        for key in DATABASE_KEYS:
            problems += _field_problems(database.get(key), f"database.{key}", allow_int=key == "port")
    if not problems and approved["environment_id"] == approved["production_environment_id"]:
        problems.append("approved_environment_is_production")
    return (approved if not problems else None), problems


def _field_problems(value, key: str, *, allow_int: bool = False) -> list[str]:
    """A required non-empty string (or, for the port, a positive integer); never echoes the value."""
    if value is None or value == "":
        return [f"approved_key_missing [key={key}]"]
    if isinstance(value, str) or (allow_int and type(value) is int and value > 0):
        return []
    return [f"approved_key_invalid_type [key={key}]"]


def url_target(env) -> tuple[dict | None, list[str]]:
    """The portfolio's effective target: its DATABASE_URL as libpq would resolve it, or refusals."""
    problems = [f"inherited_driver_setting [key={k}]" for k in sorted(env) if k.startswith("PG")]
    url = env.get("DATABASE_URL")
    if not url:
        return None, problems + ["database_settings_missing [key=DATABASE_URL]"]
    normalized = normalize_database_url(url)
    parsed = rt.parse_database_url(normalized)
    agree = False
    if parsed is not None:
        try:
            agree = rt._parsers_agree(normalized, parsed)
        except Exception:  # noqa: BLE001 - parser messages may contain the URL
            agree = False
    if parsed is None or not agree:
        return None, problems + ["database_url_unsupported_or_malformed [key=DATABASE_URL]"]
    target = {"host": parsed["host"], "port": str(parsed["port"]), "name": parsed["database"], "role": parsed["user"]}
    return target, problems


def pg_target(env) -> tuple[dict | None, list[str]]:
    """The transit API's effective target: the PG* fields db/pool.js passes to pg, or refusals."""
    problems = [f"unsupported_driver_setting [key={k}]" for k in sorted(env)
                if k.startswith("PG") and k not in PG_ALLOWED]
    if not env.get("PGHOST"):
        return None, problems + ["database_settings_missing [key=PGHOST]"]
    target = {"host": env["PGHOST"], "port": env.get("PGPORT") or "5432",
              "name": env.get("PGDATABASE", ""), "role": env.get("PGUSER", "")}
    return target, problems


def check(service: str, env, approved: dict) -> list[str]:
    if service in EXCLUDED:
        return [EXCLUDED[service]]
    problems = []
    environment = env.get("RAILWAY_ENVIRONMENT_ID")
    if environment != approved["environment_id"]:
        problems.append("railway_environment_not_approved_preview [key=RAILWAY_ENVIRONMENT_ID]")
    if environment == approved["production_environment_id"]:
        problems.append("railway_environment_is_production [key=RAILWAY_ENVIRONMENT_ID]")
    if env.get("BIZQLAB_RUNTIME") != "production":
        problems.append("preview_must_run_attested_mode [key=BIZQLAB_RUNTIME]")
    database, refusals = (url_target if service == "portfolio" else pg_target)(env)
    problems += refusals
    if database is not None:
        for key in DATABASE_KEYS:
            if str(database[key]) != str(approved["database"][key]):
                problems.append(f"database_not_approved_preview [component={key}]")
        if database["host"].endswith(PUBLIC_PROXY_SUFFIXES):
            problems.append("database_public_proxy_host")
    problems += [f"external_side_effect_configured [key={k}]" for k in SIDE_EFFECT_KEYS if env.get(k)]
    if service == "portfolio" and env.get("VITE_TRANSIT_API_BASE_URL", "").rstrip("/") != approved["api_base"].rstrip("/"):
        problems.append("browser_api_not_approved_preview [key=VITE_TRANSIT_API_BASE_URL]")
    return problems


def main(argv=None, env=os.environ) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--service", required=True, choices=SERVICES)
    parser.add_argument("--approved", required=True, type=Path, help="owner-written approved preview targets (JSON)")
    args = parser.parse_args(argv)
    approved, problems = load_approved(args.approved)
    if approved is not None:
        problems = check(args.service, env, approved)
    for problem in problems:
        print(f"PREVIEW BLOCKED ({args.service}): {problem}", file=sys.stderr)
    if not problems:
        print(f"preview environment approved for {args.service}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
