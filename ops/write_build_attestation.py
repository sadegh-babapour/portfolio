#!/usr/bin/env python3
"""Write the Railway build attestation for the Python services' build root (design §3.4).

The repository root is the build root of portfolio and transit-poller. The
marker is `.bizqlab-build-attestation.json` directly inside it, bound to this
Railway service, environment and (when Railway supplies it) commit. It holds no secrets and is ignored by Git.

Inert until a Railway build command calls it (see the M1 deployment checklist).
It never runs on a workstation: it requires the Railway build identifiers and
refuses where the local profile or approval policy exists.

Exit 0: written, or an existing marker for exactly this service/environment/commit
was kept. Exit 2: refused; nothing was written and an existing marker was not changed.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    # `python ops/write_build_attestation.py` puts ops/ first on sys.path.
    sys.path.insert(0, str(ROOT))

from app import runtime_env as rt  # noqa: E402

BUILD_ROOT = rt.BUILD_ROOT  # "."
ID_KEYS = ("RAILWAY_SERVICE_ID", "RAILWAY_ENVIRONMENT_ID")


class AttestationRefused(Exception):
    def __init__(self, code: str, key: str | None = None):
        self.code, self.key = code, key
        super().__init__(rt.format_error(code, key))


def attestation_document(env, now: datetime, build_root: str = BUILD_ROOT) -> dict:
    """The document for this build, or ``AttestationRefused`` naming the key at fault (never a value)."""
    for key in ID_KEYS:
        value = env.get(key)
        if not value:
            raise AttestationRefused("missing_build_identifier", key)
        if not rt._RAILWAY_ID_RE.fullmatch(value):
            raise AttestationRefused("invalid_build_identifier", key)
    commit = env.get(rt.COMMIT_KEY) or None
    if commit is not None and not rt._COMMIT_RE.fullmatch(commit):
        raise AttestationRefused("invalid_build_identifier", rt.COMMIT_KEY)
    return {
        "schema": 1, "kind": rt.ATTESTATION_KIND, "build_root": build_root,
        "railway_service_id": env["RAILWAY_SERVICE_ID"], "railway_environment_id": env["RAILWAY_ENVIRONMENT_ID"],
        "git_commit": commit, "generated_at": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def render(doc: dict) -> bytes:
    return (json.dumps(doc, separators=(",", ":")) + "\n").encode("utf-8")


def _same_build(data: bytes, doc: dict) -> bool:
    """An existing marker is kept only if it is this exact build's document (``generated_at`` aside)."""
    ok, existing = rt._try_parse_json(data)
    if not ok or not isinstance(existing, dict) or set(existing) != set(doc):
        return False
    return all(existing[k] == doc[k] and type(existing[k]) is type(doc[k]) for k in doc if k != "generated_at")


def write_attestation(root, env, *, now: datetime | None = None, workstation=None,
                      build_root: str = BUILD_ROOT) -> str:
    """Write or keep the marker under ``root``. Returns ``written`` or ``unchanged``."""
    workstation = workstation or _workstation
    doc = attestation_document(env, now or datetime.now(timezone.utc), build_root)
    if any(workstation()):
        raise AttestationRefused("workstation_build_refused")
    reason = None
    data = None
    try:
        data, _info = rt.read_in_root(os.fspath(root), rt.ATTESTATION_FILENAME, rt.ATTESTATION_MAX_BYTES)
    except rt.FileReadError as exc:
        reason = exc.reason
    if reason is None:
        if not _same_build(data, doc):
            raise AttestationRefused("existing_marker_mismatch")
        outcome = "unchanged"
    elif reason == "missing":
        _create(root, render(doc))
        outcome = "written"
    else:
        raise AttestationRefused(f"existing_marker_{reason}")
    status = rt.read_attestation(root, build_root=build_root, env=env)
    if status != "valid":
        raise AttestationRefused(f"self_check_{status.replace(':', '_')}")
    return outcome


def _workstation() -> tuple[bool, bool]:
    """W1/W2 of design §3.1 by ``lstat``: the approval policy or the local profile exists."""
    try:
        policy = rt.policy_path()
    except rt.RuntimeConfigError:
        policy = None
    return (policy is not None and rt.path_exists_nofollow(policy), rt.path_exists_nofollow(rt.PROFILE_PATH))


def _create(root, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    dir_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fd = os.open(rt.ATTESTATION_FILENAME, flags, 0o444, dir_fd=dir_fd)
        try:
            os.write(fd, content)
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        os.close(dir_fd)


def main() -> int:
    failure = None
    try:
        outcome = write_attestation(ROOT, os.environ)
    except (AttestationRefused, rt.RuntimeConfigError, OSError) as exc:
        failure = getattr(exc, "code", None) or type(exc).__name__
        key = getattr(exc, "key", None)
        failure = rt.format_error(failure, key)
    if failure is not None:
        print(f"BIZQLAB ATTESTATION REFUSED (build_root={BUILD_ROOT}): {failure}", file=sys.stderr)
        return 2
    print(f"bizqlab build attestation {outcome}: build_root={BUILD_ROOT}, file={rt.ATTESTATION_FILENAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
