#!/usr/bin/env python3
"""CI only (.github/workflows/local-stack.yml): the database target a workstation would have.

    python3 ops/local-stack/ci_target.py profile          # writes .env.local (mode 600)
    python3 ops/local-stack/ci_target.py policy | sudo tee /etc/bizqlab/db-policy.json

The throwaway Postgres is ops/local-stack/compose.ci.yaml, at a fixed address on the stack's
network; its password is random per run and comes from the job's environment.
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOST, PORT, DATABASE, ROLE = "172.30.0.10", 5432, "stack_ci", "ci"


def policy() -> dict:
    """The root-owned DB policy's content (ops/db-policy.example.json); never a password."""
    return {"schema": 1, "development_target": {
        "host": HOST, "port": PORT, "database": DATABASE, "role": ROLE,
        "server_addresses": [HOST], "server_port": PORT}}


def profile(env=os.environ) -> str:
    values = {"PGHOST": HOST, "PGPORT": str(PORT), "PGDATABASE": DATABASE, "PGUSER": ROLE,
              "PGSSLMODE": "disable"}
    values["PGPASSWORD"] = env["POSTGRES_PASSWORD"]  # random per CI run (compose.ci.yaml)
    return "".join(f"{key}={value}\n" for key, value in values.items())


def main(argv=sys.argv[1:]) -> int:
    if argv == ["policy"]:
        print(json.dumps(policy()))
        return 0
    if argv == ["profile"]:
        path = ROOT / ".env.local"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(profile())
        os.chmod(path, 0o600)
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
