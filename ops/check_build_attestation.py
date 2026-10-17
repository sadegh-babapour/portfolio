#!/usr/bin/env python3
"""Classify the Python services' build attestation for the current environment (design §3.4).

Read-only and connects to nothing. Prints a non-secret classification, for
example `attestation: valid` or `attestation: invalid:service_mismatch`, and the
binding variables' presence (never their values). Exit 0 only when valid; use it
in staging and as the first step of the portfolio pre-deploy command.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    # `python ops/check_build_attestation.py` puts ops/ first on sys.path.
    sys.path.insert(0, str(ROOT))

from app import runtime_env as rt  # noqa: E402


def main(env=os.environ, root=ROOT) -> int:
    status = rt.read_attestation(root, build_root=rt.BUILD_ROOT, env=env)
    present = ", ".join(f"{key}={'set' if env.get(key) else 'unset'}"
                        for key in (rt.RUNTIME_KEY, *rt.MARKER_KEYS, rt.COMMIT_KEY))
    print(f"attestation: {status} (build_root={rt.BUILD_ROOT}, file={rt.ATTESTATION_FILENAME}; {present})")
    return 0 if status == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
