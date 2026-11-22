#!/usr/bin/env python3
"""The local stack: production's images and start commands, on the approved dev database.

    make dev                  # preflight, build, start (web, transit-api, dagster, frontend)
    make dev POLLER=1         # also the realtime poller (writes to the shared dev database)
    make dev-logs / dev-down  # follow the logs / stop (volumes kept)
    make dev-migrate          # alembic + transit schema on the dev database (asks first)

What `build` does, in order:
1. Preflight on the host: `ops/dev.py check` (which database, role and server; no writes).
2. Export the source the way Railway sees it: tracked files plus new, not-ignored ones, from
   the working tree. Ignored files (.env.local, docs/, venvs, node_modules) never reach an
   image. Railway builds from git, so nothing is lost.
3. Build the base images like Railway: Railpack for the repository root (portfolio, poller)
   and backend/transit_api; orchestration/Dockerfile for dagster.
4. Build the thin development layers (ops/local-stack/*.Dockerfile): the root-owned DB policy
   copied in, an unprivileged user. The password never enters an image: each container
   copies the read-only mounted .env.local at start (ops/local-stack/bizqlab-dev-start).

Images are native to this machine (arm64 on the Mac); Railway builds amd64.
Requires Docker (Colima on the Mac), Docker Compose, buildx, and Railpack RAILPACK_VERSION.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / ".local-stack"
SRC = WORK / "src"
PLANS = WORK / "plans"
DEVLAYER = WORK / "devlayer"
STACK_FILES = ROOT / "ops" / "local-stack"
COMPOSE_FILE = ROOT / "compose.local.yaml"
PROJECT = "bizqlab-local"

# Railway builds with Railpack; the CLI and its BuildKit frontend must be the same version.
RAILPACK_VERSION = "0.43.0"
RAILPACK_FRONTEND = f"ghcr.io/railwayapp/railpack-frontend:v{RAILPACK_VERSION}"
BASE_IMAGES = {
    "portfolio": ("bizqlab-local/portfolio-base", ""),            # repo root (also the poller)
    "transit-api": ("bizqlab-local/transit-api-base", "backend/transit_api"),
}
DAGSTER_BASE = "bizqlab-local/dagster-base"
# orchestration/Dockerfile writes a build attestation bound to Railway's IDs and fails without
# them. Local IDs make a local attestation, which development mode ignores.
DAGSTER_BUILD_ARGS = {"RAILWAY_SERVICE_ID": "local-service", "RAILWAY_ENVIRONMENT_ID": "local-env"}
DEVLAYER_FILES = ("python.Dockerfile", "node.Dockerfile", "dagster.Dockerfile", "bizqlab-dev-start")
SENTINEL = Path("scripts") / "bootstrap_transit_db.py"
DEFAULT_SERVICES = ["web", "transit-api", "dagster", "frontend"]
# What "started" means for each service (urls on 127.0.0.1, as published by Compose).
CHECKS = {
    "web": "http://127.0.0.1:8086/terms",
    "transit-api": "http://127.0.0.1:4000/api/health",
    "dagster": "http://127.0.0.1:3000/server_info",
    "frontend": "http://127.0.0.1:5173/",
}


class StackError(RuntimeError):
    pass


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    print("+ " + " ".join(command), flush=True)
    return subprocess.run(command, check=True, env=stack_env(), **kwargs)


def stack_env(env=os.environ) -> dict:
    """The environment for every command: BIZQLAB_UID is the host user's uid, which the dev
    layers give the container user so a mode-600 .env.local mount is readable on Linux."""
    uid = os.getuid()
    if uid == 0:
        raise StackError("run the local stack as your own user, not root")
    return {**env, "BIZQLAB_UID": str(uid)}


# --------------------------------------------------------------------------- source export

def is_secret_path(relative: str) -> bool:
    """Environment files never go into a build context, even if git would accept them."""
    name = relative.rsplit("/", 1)[-1]
    return name == ".env" or (name.startswith(".env.") and not name.endswith(".example"))


def export_list(root: Path = ROOT) -> list[str]:
    """Tracked files plus untracked, not-ignored ones, as they are in the working tree."""
    output = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            cwd=root, check=True, stdout=subprocess.PIPE).stdout
    paths = sorted({p for p in output.decode().split("\0") if p})
    return [p for p in paths if not is_secret_path(p) and (root / p).is_file()]


def export_source(root: Path = ROOT, dest: Path = SRC) -> int:
    """A fresh copy of the export list in `dest` (deleted files and old builds don't linger)."""
    if dest.exists():
        shutil.rmtree(dest)
    files = export_list(root)
    for relative in files:
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / relative, target, follow_symlinks=False)
    return len(files)


# --------------------------------------------------------------------------- policy

def policy_source() -> Path:
    sys.path.insert(0, str(ROOT))
    from app import runtime_env

    return Path(runtime_env.policy_path())


def policy_problem(info: os.stat_result) -> str | None:
    """A quick host-side check; each container's gate checks the copy again, strictly."""
    if not stat.S_ISREG(info.st_mode):
        return "not a regular file"
    if info.st_uid != 0:
        return "not owned by root"
    if info.st_mode & 0o022:
        return "writable by group or others"
    return None


def stage_devlayer(policy: Path, root: Path = ROOT, dest: Path = DEVLAYER) -> None:
    """The development layers' build context: their Dockerfiles, the start script, the policy."""
    problem = policy_problem(os.lstat(policy))
    if problem:
        raise StackError(f"DB policy {policy}: {problem}")
    data = json.loads(policy.read_bytes())
    if "password" in json.dumps(data).lower():
        raise StackError(f"DB policy {policy} mentions a password; it must not hold one")
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name in DEVLAYER_FILES:
        shutil.copy2(root / "ops" / "local-stack" / name, dest / name)
    shutil.copyfile(policy, dest / "db-policy.json")
    shutil.copyfile(root / SENTINEL, dest / SENTINEL.name)


# --------------------------------------------------------------------------- builds

def check_tools() -> None:
    for tool in ("docker", "railpack", "git"):
        if shutil.which(tool) is None:
            raise StackError(f"{tool} not found (see docs/lessons/TOOLBOX.md, 'Containers')")
    version = subprocess.run(["railpack", "--version"], check=True, stdout=subprocess.PIPE, text=True).stdout
    if RAILPACK_VERSION not in version:
        raise StackError(f"railpack {RAILPACK_VERSION} required (Railway parity), found: {version.strip()}")
    for args in (["compose", "version"], ["buildx", "version"]):
        if subprocess.run(["docker", *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            raise StackError(f"docker {args[0]} is not available")


def plan_secrets(plan: Path) -> list[str]:
    """Railpack hands its `--env` values to BuildKit as secrets; the build must pass them."""
    return list(json.loads(plan.read_text()).get("secrets") or [])


def build_railpack(name: str, tag: str, subdir: str) -> None:
    context = SRC / subdir if subdir else SRC
    plan = PLANS / f"{name}.json"
    run(["railpack", "prepare", str(context), "--plan-out", str(plan), "--info-out", str(PLANS / f"{name}.info.json")])
    command = ["docker", "buildx", "build", "--build-arg", f"BUILDKIT_SYNTAX={RAILPACK_FRONTEND}",
               "-f", str(plan), "--load", "-t", tag]
    for secret in plan_secrets(plan):
        if secret not in os.environ:
            raise StackError(f"the {name} plan needs the build secret {secret}; set it in the environment")
        command += ["--secret", f"id={secret},env={secret}"]
    run(command + [str(context)])


def build_dagster() -> None:
    command = ["docker", "build", "-f", str(SRC / "orchestration" / "Dockerfile"), "-t", DAGSTER_BASE]
    for key, value in DAGSTER_BUILD_ARGS.items():
        command += ["--build-arg", f"{key}={value}"]
    run(command + [str(SRC)])


def compose(extra_files: list[str], *args: str, profiles: list[str] = ()) -> list[str]:
    command = ["docker", "compose", "-p", PROJECT, "-f", str(COMPOSE_FILE)]
    for path in extra_files:
        command += ["-f", str(ROOT / path)]
    for profile in profiles:
        command += ["--profile", profile]
    return command + list(args)


def preflight(expected_db: str) -> None:
    run([sys.executable, str(ROOT / "ops" / "dev.py"), "check", "--expected-db", expected_db], cwd=ROOT)
    if not (ROOT / ".env.local").is_file():
        raise StackError(".env.local is missing")


def build(args) -> None:
    check_tools()
    preflight(args.expected_db)
    print(f"exported {export_source()} files to {SRC.relative_to(ROOT)}", flush=True)
    PLANS.mkdir(parents=True, exist_ok=True)
    for name, (tag, subdir) in BASE_IMAGES.items():
        build_railpack(name, tag, subdir)
    build_dagster()
    stage_devlayer(policy_source())
    run(compose(args.with_files, "build", "web", "transit-api", "dagster"), cwd=ROOT)


# --------------------------------------------------------------------------- checks

def started(service: str, status: int, body: bytes) -> bool:
    """Did the service start and reach what it needs? transit-api answers 503 when its data
    is stale, which still proves it reached its tables; only `unavailable` means it didn't."""
    if service == "transit-api":
        try:
            return json.loads(body).get("status") not in (None, "unavailable")
        except ValueError:
            return False
    return status == 200


def fetch(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def wait_started(services: list[str], timeout: float) -> list[str]:
    """The services that didn't start within `timeout` seconds (empty = all good)."""
    pending = [s for s in services if s in CHECKS]
    deadline = time.monotonic() + timeout
    while pending and time.monotonic() < deadline:
        for service in list(pending):
            try:
                status, body = fetch(CHECKS[service])
            except (OSError, urllib.error.URLError):
                continue
            if started(service, status, body):
                print(f"started: {service} ({CHECKS[service]})", flush=True)
                pending.remove(service)
        if pending:
            time.sleep(3)
    return pending


# --------------------------------------------------------------------------- commands

def services_for(args) -> tuple[list[str], list[str]]:
    services = list(DEFAULT_SERVICES)
    profiles = []
    if args.poller:
        services.append("poller")
        profiles.append("poller")
    return services, profiles


def command_up(args) -> int:
    if not args.no_build:
        build(args)
    services, profiles = services_for(args)
    run(compose(args.with_files, "up", "-d", *services, profiles=profiles), cwd=ROOT)
    missing = wait_started(services, args.timeout)
    if missing:
        print(f"NOT STARTED within {args.timeout:.0f} s: {', '.join(missing)} (make dev-logs)", file=sys.stderr)
        return 1
    print("\nLocal stack up (127.0.0.1 only):\n  site       http://127.0.0.1:8086\n"
          "  map (dev)  http://127.0.0.1:5173  (local transit-api)\n  api        http://127.0.0.1:4000/api/health\n"
          "  dagster    http://127.0.0.1:3000  (schedules off; runs WRITE to the dev database)")
    return 0


def command_migrate(args) -> int:
    print("This applies Alembic migrations (schema portfolio) and the transit schema scripts\n"
          f"(scripts/db, no data load) to the database .env.local names ({args.expected_db}).\n"
          "It WRITES schema; the PC database is shared with the Railway VM.")
    if not args.yes:
        if input(f"Type the database name ({args.expected_db}) to continue: ").strip() != args.expected_db:
            print("Not confirmed; nothing changed.")
            return 1
    run(compose(args.with_files, "run", "--rm", "--no-deps", "web",
                "bizqlab-dev-start sh -c 'alembic upgrade head && python scripts/bootstrap_transit_db.py'"), cwd=ROOT)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["build", "up", "down", "logs", "migrate", "check"])
    parser.add_argument("--expected-db", default="portfolio_dev")
    parser.add_argument("--with", dest="with_files", action="append", default=[],
                        help="an extra compose file (CI: ops/local-stack/compose.ci.yaml)")
    parser.add_argument("--poller", action="store_true", help="also start the realtime poller")
    parser.add_argument("--no-build", action="store_true")
    parser.add_argument("--volumes", action="store_true", help="down: also delete Dagster history and node_modules")
    parser.add_argument("--no-follow", action="store_true")
    parser.add_argument("--yes", action="store_true", help="migrate: don't ask")
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            build(args)
            return 0
        if args.command == "up":
            return command_up(args)
        if args.command == "down":
            run(compose(args.with_files, "down", *(["--volumes"] if args.volumes else []), profiles=["poller"]),
                cwd=ROOT)
            return 0
        if args.command == "logs":
            run(compose(args.with_files, "logs", "--tail", "200", *([] if args.no_follow else ["-f"]),
                        profiles=["poller"]), cwd=ROOT)
            return 0
        if args.command == "migrate":
            return command_migrate(args)
        services, _ = services_for(args)
        missing = wait_started(services, args.timeout)
        return 1 if missing else 0
    except (StackError, subprocess.CalledProcessError) as exc:
        print(f"LOCAL STACK ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
