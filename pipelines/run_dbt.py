"""Run dbt against the approved development database only.

dbt has its own connection settings (warehouse/profiles.yml) and knows nothing about
the runtime gate. This wrapper bootstraps the gate, opens one verified connection to
prove the database is the approved one, then starts dbt from the separate data
environment (.venv-data) with exactly that target and nothing inherited.

Usage:
  .venv/bin/python -m pipelines.run_dbt build
  .venv/bin/python -m pipelines.run_dbt source freshness
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_DIR = ROOT / "warehouse"
DBT = ROOT / ".venv-data" / "bin" / "dbt"
# Settings that could point dbt or libpq somewhere else are never passed through.
DROP_PREFIXES = ("PG", "DBT_", "DATABASE_URL")


def dbt_env(target, base=os.environ) -> dict:
    """The child environment: the inherited one minus database settings, plus the approved target."""
    env = {k: v for k, v in base.items() if not k.startswith(DROP_PREFIXES)}
    env.update({
        "DBT_PG_HOST": target.host,
        "DBT_PG_PORT": str(target.port),
        "DBT_PG_DBNAME": target.database,
        "DBT_PG_USER": target.user,
        "DBT_ENV_SECRET_PG_PASSWORD": target.password,
        "DBT_PG_SSLMODE": target.sslmode,
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
    })
    return env


def main(argv: list[str] | None = None) -> int:
    from app import runtime_db, runtime_state

    state = runtime_state.bootstrap_entry_point("dbt")
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: python -m pipelines.run_dbt <dbt command> [options]", file=sys.stderr)
        return 2
    if state.mode != "development":
        print("run_dbt: production has no reporting database yet (stage 2); refusing", file=sys.stderr)
        return 2

    runtime_db.connect_verified().close()  # identity check: refuses anything but the approved database
    if not DBT.exists():
        print("run_dbt: .venv-data is missing; create it with: python3.13 -m venv .venv-data && "
              ".venv-data/bin/pip install -r requirements-data.txt", file=sys.stderr)
        return 2
    command = [str(DBT), *args, "--project-dir", str(PROJECT_DIR), "--profiles-dir", str(PROJECT_DIR)]
    return subprocess.call(command, cwd=PROJECT_DIR, env=dbt_env(state.development.target))


if __name__ == "__main__":
    raise SystemExit(main())
