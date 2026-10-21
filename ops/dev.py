#!/usr/bin/env python3
"""Local Bizqlab environment preflight and process launcher.

A thin consumer of the shared runtime gate (app/runtime_state.py): the strict
root .env.local profile and the root-owned approval policy are parsed and
validated there, never here. Inherited or command-line database settings that
differ from the approved target are refused, not erased. The launched process
bootstraps again on its own, so this launcher is not the only safety boundary.
No package install, no database mutation, no Git mutations.

Examples:
  python ops/dev.py check --expected-db portfolio_dev
  python ops/dev.py run --expected-db portfolio_dev -- python -m app.main
  python ops/dev.py run --expected-db portfolio_dev -- npm start --prefix backend/transit_api
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    # `python ops/dev.py` puts ops/ first on sys.path; the gate lives in the app package.
    sys.path.insert(0, str(ROOT))

from app import runtime_db, runtime_env as rt, runtime_state  # noqa: E402

PURPOSE = "launcher"
FRONTEND_PROFILE = ROOT / "frontend" / ".env.development.local"
LOCAL_API_BASE = "http://localhost:4000/api"


def output(command, *args):
    try:
        result = subprocess.run([command, *args], cwd=ROOT, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=5, check=False)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def resolve(expected_db):
    """Bootstrap through the shared gate; a refusal exits 2 before any connection."""
    state = runtime_state.bootstrap_entry_point(PURPOSE)
    if state.mode != "development":
        raise RuntimeError("ops/dev.py is a workstation launcher; it refuses production mode.")
    target = state.development.target
    if target.database != expected_db:
        raise RuntimeError(f"Database mismatch: approved target '{target.database}' != explicitly expected "
                           f"'{expected_db}'. No connection attempted.")
    print(f"Database profile: host={target.host}, port={target.port}, database={target.database}, "
          f"role={target.user}, sslmode={target.sslmode} (secrets hidden; approved by the root policy)")
    return state


def verify_identity():
    """Open one verified connection: the identity query is its only statement."""
    conn = runtime_db.connect_verified()
    conn.close()
    print("PC PostgreSQL: identity verified (database, role, server address and port match the policy).")


def git_info():
    sha = output("git", "rev-parse", "--short", "HEAD")
    branch = output("git", "branch", "--show-current")
    if sha:
        print(f"Git: branch={branch or '(detached)'}, SHA={sha}")
    else:
        print("WARN: This directory is not a Git checkout")
    state = output("git", "status", "--porcelain")
    if state is None:
        print("WARN: Git working-tree status unavailable")
    elif state:
        # Never print a diff that might contain secrets; filenames alone matter.
        print(f"Git: {len(state.splitlines())} changed/untracked entry(s); review with git status before any commit")
    else:
        print("Git: clean working tree")
    for name in ("origin", "upstream"):
        url = output("git", "remote", "get-url", name)
        if url:
            # Avoid reporting credentials embedded in an HTTPS remote.
            from urllib.parse import urlsplit
            clean = url
            if url.startswith("https://"):
                u = urlsplit(url)
                clean = f"https://{u.hostname}{u.path}"
            print(f"Remote {name}: {clean}")
        else:
            print(f"Remote {name}: not configured")
    try:
        d = subprocess.run(["git", "status", "--porcelain", "--", ".env.example"], cwd=ROOT,
                           capture_output=True, text=True, timeout=5)
        if d.stdout.strip():
            print("WARN: tracked .env.example was modified; inspect privately for accidental credentials before committing")
    except (OSError, subprocess.TimeoutExpired):
        pass


def frontend_api_target():
    """The local Vite API target, read with the strict profile grammar (no dotenv)."""
    try:
        data, _info = rt.read_nofollow(FRONTEND_PROFILE, rt.PROFILE_MAX_BYTES)
        return rt.parse_profile(data).get("VITE_TRANSIT_API_BASE_URL")
    except rt.FileReadError as exc:
        return "missing" if exc.reason == "missing" else "unreadable"
    except rt.RuntimeConfigError:
        return "unparseable"
    except Exception:  # noqa: BLE001 - a warning-only check never stops the preflight
        return "unreadable"


def version_checks():
    print("Python:", sys.version.split()[0], f"({sys.executable})")
    if sys.version_info[:2] != (3, 13):
        print("WARN: project runtime is Python 3.13; activate its venv")
    for command, arg in (("node", "--version"), ("npm", "--version"), ("psql", "--version")):
        ver = output(command, arg)
        print(f"{command}: {ver or 'not found'}")
    for dirname in ("frontend", "backend/transit_api"):
        good = (ROOT / dirname / "node_modules").is_dir()
        print(f"{dirname}/node_modules: {'present' if good else 'missing (only install if needed)'}")
    target = frontend_api_target()
    if target == LOCAL_API_BASE:
        print("frontend Vite API target: localhost:4000/api")
    elif target == "missing":
        print("WARN: frontend/.env.development.local missing; the Vite dev server refuses to start without "
              f"VITE_TRANSIT_API_BASE_URL={LOCAL_API_BASE}")
    else:
        print(f"WARN: frontend Vite API target is not the expected local {LOCAL_API_BASE} ({target or 'unset'})")
    for dirname in (".claude", ".codex", ".agents"):
        if (ROOT / dirname).exists():
            print(f"Existing agent directory {dirname}: preserve; inspect rather than overwrite")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("check", "run"):
        p = sub.add_parser(name)
        p.add_argument("--expected-db", required=True, help="Exact dedicated PC portfolio database name")
        if name == "run":
            p.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if Path.cwd().resolve() != ROOT:
            raise RuntimeError("Run from the Git repository root (cd portfolio first)")
        if not (ROOT / ".git").exists():
            raise RuntimeError("Not in the Git clone; do not run from the transferred ZIP")
        cmd = list(getattr(args, "command", None) or [])
        if cmd and cmd[0] == "--":
            cmd.pop(0)
        if args.action == "run" and not cmd:
            raise RuntimeError("Provide a command after --, for example -- python -m app.main")
        resolve(args.expected_db)
        if args.action == "check":
            version_checks()
            git_info()
            verify_identity()
            print("PREFLIGHT PASS: active tooling and PC database identity verified. No data was changed.")
            return 0
        verify_identity()
        # The child inherits only values equal to the approved target and bootstraps again itself.
        print("Starting process with the approved development target ...", flush=True)
        return subprocess.call(cmd, cwd=ROOT)
    except (rt.RuntimeConfigError, RuntimeError, OSError, ValueError) as exc:
        print(f"PREFLIGHT ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
