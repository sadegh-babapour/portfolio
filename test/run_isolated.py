"""Run the Python test suite with isolation guards installed before any test import.

Usage: .venv/bin/python test/run_isolated.py [-v] [unittest discover options]

The child process gets a sanitized environment (no inherited DATABASE_URL, PG*,
RAILWAY_*, BIZQLAB_*, PYTHON* or NODE_* settings) and PYTHONPATH pointing at
test/shims, whose sitecustomize.py blocks database connections, network sockets,
dotenv discovery and reads of the real profile and policy. Node children get
NODE_OPTIONS loading backend/transit_api/test/shims/isolate.js, which blocks
outbound connections and the same real configuration reads.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIMS = ROOT / "test" / "shims"
NODE_SHIM = ROOT / "backend" / "transit_api" / "test" / "shims" / "isolate.js"
STRIP_KEYS = {"DATABASE_URL"}
STRIP_PREFIXES = ("PG", "RAILWAY_", "BIZQLAB_", "PYTHON", "NODE_")


def isolated_env(environ=os.environ) -> dict:
    env = {k: v for k, v in environ.items() if k not in STRIP_KEYS and not k.startswith(STRIP_PREFIXES)}
    env["PYTHONPATH"] = os.pathsep.join([str(SHIMS), str(ROOT)])
    # Node children (cross-language parity, generators) load the Node isolation shim.
    env["NODE_OPTIONS"] = f'--require "{NODE_SHIM}"'
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["BQ_TEST_ISOLATION"] = "1"
    return env


def main(argv: list[str]) -> int:
    command = [sys.executable, "-m", "unittest", "discover", "-s", "test", *argv]
    return subprocess.call(command, cwd=ROOT, env=isolated_env())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
