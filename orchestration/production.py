"""Production database checks for the Railway `dagster` service, and its start command.

On Railway the service has its own DATABASE_URL, which must log in as bizqlab_dagster:
a role with no special powers and no access to the site's schemas, whose tables go to
the `dagster` schema (ops/sql/railway_dagster_role.sql). Every connection a run opens
checks this first, and so does the service before it starts Dagster at all: Dagster's
own storage connects with the same URL, so a wrong URL must stop the service before
Dagster creates anything.

Start command (orchestration/Dockerfile):
  .venv-data/bin/python -m orchestration.production
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
DAEMON = ROOT / ".venv-data" / "bin" / "dagster-daemon"
ROLE = "bizqlab_dagster"
SITE_SCHEMAS = ["portfolio", "transit"]
ROLE_SQL = """
    select current_user,
           r.rolsuper or r.rolcreaterole or r.rolbypassrls or r.rolreplication,
           current_setting('search_path'),
           exists (select 1 from pg_namespace n
                   where n.nspname = any(%s) and has_schema_privilege(n.oid, 'USAGE'))
    from pg_roles r where r.rolname = current_user
"""


class RoleRefused(Exception):
    """The production connection is not acceptable. The message is a code, never a value."""


def in_production(env=os.environ) -> bool:
    """Only decides what runs by default; the gate still decides what may connect."""
    return env.get("BIZQLAB_RUNTIME") == "production"


def role_problem(row) -> str | None:
    """Why a connection's role is unacceptable, as a code; None if it's fine."""
    user, privileged, search_path, site_access = row
    if user != ROLE:
        return "wrong_role"
    if privileged:
        return "privileged_role"
    if site_access:
        return "site_schema_access"
    if search_path != "dagster":
        return "search_path_not_dagster"
    return None


def database_url(env=os.environ) -> str:
    url = env.get("DATABASE_URL")
    if not url:
        raise RoleRefused("database_url_missing")
    return url


def connect(url: str):
    """A psycopg2 connection that has proved it is bizqlab_dagster and nothing more."""
    conn = psycopg2.connect(url, connect_timeout=10, application_name="bizqlab-dagster")
    try:
        with conn.cursor() as cur:
            cur.execute(ROLE_SQL, (SITE_SCHEMAS,))
            problem = role_problem(cur.fetchone())
        conn.rollback()
    except BaseException:
        conn.close()
        raise
    if problem is not None:
        conn.close()
        raise RoleRefused(problem)
    return conn


def target(url: str):
    """The URL's parts in the shape pipelines.run_dbt.dbt_env expects."""
    parts = psycopg2.extensions.parse_dsn(url)
    return SimpleNamespace(host=parts["host"], port=int(parts.get("port", 5432)), database=parts["dbname"],
                           user=parts["user"], password=parts.get("password", ""),
                           sslmode=parts.get("sslmode", "prefer"))


def main() -> int:
    """Check the gate and the role, then become dagster-daemon (same process, same environment)."""
    from app import runtime_state

    state = runtime_state.bootstrap_entry_point("dagster")  # a refusal prints its code and exits 2
    failure = None
    if state.mode != "production":
        failure = "not_production"
    else:
        try:
            connect(database_url()).close()
        except RoleRefused as exc:
            failure = str(exc)
        except psycopg2.Error as exc:  # the class name only: messages can name hosts
            failure = f"connect_failed ({type(exc).__name__})"
    if failure is not None:
        print(f"BIZQLAB DAGSTER REFUSED: {failure}", file=sys.stderr, flush=True)
        return 2
    print("bizqlab dagster: database role checked; starting dagster-daemon", flush=True)
    os.execv(DAEMON, [str(DAEMON), "run", "-m", "orchestration.definitions"])


if __name__ == "__main__":
    raise SystemExit(main())
