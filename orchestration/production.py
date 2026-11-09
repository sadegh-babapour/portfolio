"""Production database checks for the Railway `dagster` service, and its start command.

On Railway the service has its own DATABASE_URL, which must log in as bizqlab_dagster:
a role with no special powers and no access to the site's schemas, whose tables go to
the `dagster` schema (ops/sql/railway_dagster_role.sql). Every connection a run opens
checks this first, and so does the service before it starts Dagster at all: Dagster's
own storage connects with the same URL, so a wrong URL must stop the service before
Dagster creates anything.

After the checks it runs two processes and stops both as soon as either stops, so
Railway restarts the service instead of leaving it half alive:
- one code server, which loads the definitions (and parses the dbt manifest) once;
- dagster-daemon, pointed at that server by workspace.production.yaml.
Left to itself, `dagster-daemon run -m` starts a fresh code server every 60 seconds,
and each one re-parses dbt. That cost ~0.15 vCPU around the clock, and its orphaned
children filled the container's 1000-process limit in about 8.5 hours, after which no
schedule could fire (2026-11-09). tini, PID 1 in the image, reaps any orphans left.

Start command (orchestration/Dockerfile, under tini):
  .venv-data/bin/python -m orchestration.production
"""
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / ".venv-data" / "bin"
DAEMON = BIN / "dagster-daemon"
WORKSPACE = Path(__file__).resolve().parent / "workspace.production.yaml"
# Loopback only, never the service's PORT: nothing outside the container may reach it.
CODE_SERVER_HOST, CODE_SERVER_PORT = "127.0.0.1", 4266
CODE_SERVER = [str(BIN / "dagster"), "api", "grpc", "-m", "orchestration.definitions", "-d", str(ROOT),
               "--host", CODE_SERVER_HOST, "--port", str(CODE_SERVER_PORT)]
DAEMON_RUN = [str(DAEMON), "run", "-w", str(WORKSPACE)]
# Loading the definitions parses the dbt manifest; give a slow start plenty of time.
CODE_SERVER_READY_SECONDS = 300
STOP_GRACE_SECONDS = 30
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


def listening(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def wait_until_listening(process, host: str, port: int, timeout: float, stop: threading.Event,
                         interval: float = 1.0) -> bool:
    """True once `process` accepts connections; False if it exits, time runs out, or we're told to stop."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not stop.is_set():
        if process.poll() is not None:
            return False
        if listening(host, port):
            return True
        stop.wait(interval)
    return False


def stop_all(processes) -> None:
    """SIGTERM every live process, then SIGKILL whatever hasn't exited after the grace period."""
    for process in processes:
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + STOP_GRACE_SECONDS
    for process in processes:
        try:
            process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def watch(processes: dict, stop: threading.Event, interval: float = 1.0) -> int:
    """Wait until one process exits or we're told to stop; then stop them all.

    Returns 0 for a requested stop (Railway's SIGTERM on redeploy), 1 when a process
    exited by itself: the service then fails and Railway restarts it.
    """
    exited = None
    while exited is None and not stop.is_set():
        exited = next((name for name, process in processes.items() if process.poll() is not None), None)
        if exited is None:
            stop.wait(interval)
    stop_all(list(processes.values()))
    if exited is None:
        return 0
    print(f"BIZQLAB DAGSTER STOPPED: {exited} exited with {processes[exited].returncode}",
          file=sys.stderr, flush=True)
    return 1


def run_services(stop: threading.Event) -> int:
    """The code server, then (once it listens) the daemon; both stop when either stops."""
    code_server = subprocess.Popen(CODE_SERVER, cwd=ROOT)
    if not wait_until_listening(code_server, CODE_SERVER_HOST, CODE_SERVER_PORT, CODE_SERVER_READY_SECONDS, stop):
        stop_all([code_server])
        if stop.is_set():
            return 0
        print("BIZQLAB DAGSTER STOPPED: code_server_not_ready", file=sys.stderr, flush=True)
        return 1
    print("bizqlab dagster: code server ready; starting dagster-daemon", flush=True)
    daemon = subprocess.Popen(DAEMON_RUN, cwd=ROOT)
    return watch({"code_server": code_server, "daemon": daemon}, stop)


def main() -> int:
    """Check the gate and the role, then run the code server and dagster-daemon."""
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
    print("bizqlab dagster: database role checked; starting the code server", flush=True)
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    return run_services(stop)


if __name__ == "__main__":
    raise SystemExit(main())
