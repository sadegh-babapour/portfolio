"""Dagster in the local stack (compose.local.yaml): production's process model, plus the UI.

The same supervision as orchestration/production.py (one `dagster api grpc` code server,
then the daemon pointed at it, both with the repository on PYTHONPATH; if one exits, all
stop), with `dagster-webserver` added on the same code server. What differs, on purpose:

- **Development only.** The runtime gate must say "development", and the approved database
  must prove its identity before anything starts; production is refused (it has its own
  start command). Each run checks again (definitions.ApprovedDatabase).
- **Local history.** DAGSTER_HOME gets orchestration/dagster.yaml: SQLite run history on this
  machine, never the shared dev database, so two machines can't share a run queue.
- **Nothing runs by itself.** Schedules and alert sensors default to off outside production
  (definitions.RUNNING), so starting the stack never loads data or sends email.
- **The UI binds to 127.0.0.1** unless DAGSTER_WEBSERVER_HOST says otherwise; the container
  sets 0.0.0.0 and Compose publishes the port on 127.0.0.1 only. Dagster has no login.
"""
import os
import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path

from orchestration import production

INSTANCE_CONFIG = Path(__file__).resolve().parent / "dagster.yaml"
WEBSERVER = production.BIN / "dagster-webserver"
DEFAULT_WEBSERVER_HOST = "127.0.0.1"
WEBSERVER_PORT = 3000


def webserver_command(host: str = DEFAULT_WEBSERVER_HOST, port: int = WEBSERVER_PORT) -> list[str]:
    """The UI, loading the definitions from the one code server (as the daemon does)."""
    return [str(WEBSERVER), "-w", str(production.WORKSPACE), "-h", host, "-p", str(port)]


def prepare_home(env=os.environ) -> Path:
    """DAGSTER_HOME with the development instance settings (telemetry off, one run at a time)."""
    home = env.get("DAGSTER_HOME")
    if not home:
        raise RuntimeError("DAGSTER_HOME is not set")
    path = Path(home)
    path.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(INSTANCE_CONFIG, path / "dagster.yaml")
    return path


def refusal(state_mode: str, verify) -> str | None:
    """Why the local stack must not start Dagster, or None. `verify` opens and closes one
    identity-checked connection; its errors are codes, never values."""
    if state_mode != "development":
        return "not_development"
    try:
        verify()
    except Exception as exc:  # RuntimeConfigError carries a code; others only their class name
        from app import runtime_env

        return str(exc) if isinstance(exc, runtime_env.RuntimeConfigError) else type(exc).__name__
    return None


def run_services(stop: threading.Event, host: str) -> int:
    """Code server first; once it listens, the daemon and the UI. All stop when one stops."""
    env = production.child_env()
    code_server = subprocess.Popen(production.CODE_SERVER, cwd=production.ROOT, env=env)
    if not production.wait_until_listening(code_server, production.CODE_SERVER_HOST, production.CODE_SERVER_PORT,
                                           production.CODE_SERVER_READY_SECONDS, stop):
        production.stop_all([code_server])
        if stop.is_set():
            return 0
        print("BIZQLAB DAGSTER STOPPED: code_server_not_ready", file=sys.stderr, flush=True)
        return 1
    print(f"bizqlab dagster (local): code server ready; starting dagster-daemon and the UI on {host}:{WEBSERVER_PORT}",
          flush=True)
    daemon = subprocess.Popen(production.DAEMON_RUN, cwd=production.ROOT, env=env)
    webserver = subprocess.Popen(webserver_command(host), cwd=production.ROOT, env=env)
    return production.watch({"code_server": code_server, "daemon": daemon, "webserver": webserver}, stop)


def main() -> int:
    from app import runtime_db, runtime_state

    state = runtime_state.bootstrap_entry_point("dagster")  # a refusal prints its code and exits 2
    failure = refusal(state.mode, lambda: runtime_db.connect_verified().close())
    if failure is not None:
        print(f"BIZQLAB DAGSTER LOCAL REFUSED: {failure}", file=sys.stderr, flush=True)
        return 2
    target = state.development.target
    print(f"bizqlab dagster (local): database {target.database} on {target.host} verified; "
          "schedules and alerts stay off", flush=True)
    prepare_home()
    stop = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    return run_services(stop, os.environ.get("DAGSTER_WEBSERVER_HOST", DEFAULT_WEBSERVER_HOST))


if __name__ == "__main__":
    raise SystemExit(main())
