"""Test-only isolation guards, loaded through PYTHONPATH by test/run_isolated.py.

Installed before any test module is imported:
- psycopg2 connections are refused at every Python-visible entry point;
- IPv4/IPv6 socket connections are refused (local AF_UNIX pairs still work);
- python-dotenv discovery and loading are disabled;
- opening the real profile, root .env files or the root policy is refused.
Production code contains none of this.
"""
from __future__ import annotations

import builtins
import io
import os
import socket
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PROTECTED = {
    os.path.join(_REPO, ".env.local"),
    os.path.join(_REPO, ".env"),
    os.path.join(_REPO, "frontend", ".env.development.local"),
    "/Library/Application Support/Bizqlab/db-policy.json",
    "/etc/bizqlab/db-policy.json",
}


class IsolationViolation(RuntimeError):
    pass


def _refuse(*_args, **_kwargs):
    raise IsolationViolation("blocked by test isolation")


try:
    import psycopg2
    import psycopg2._psycopg as _psycopg

    psycopg2.connect = _refuse
    psycopg2._connect = _refuse
    _psycopg._connect = _refuse
except ImportError:
    pass

_INET = (socket.AF_INET, socket.AF_INET6)
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _guarded_connect(self, address):
    if self.family in _INET:
        raise IsolationViolation("network connection blocked by test isolation")
    return _real_connect(self, address)


def _guarded_connect_ex(self, address):
    if self.family in _INET:
        raise IsolationViolation("network connection blocked by test isolation")
    return _real_connect_ex(self, address)


socket.socket.connect = _guarded_connect
socket.socket.connect_ex = _guarded_connect_ex
socket.create_connection = _refuse

try:
    import dotenv

    dotenv.load_dotenv = lambda *a, **k: False
    dotenv.find_dotenv = lambda *a, **k: ""
    dotenv.dotenv_values = lambda *a, **k: {}
except ImportError:
    pass


def _is_protected(path, dir_fd=None) -> bool:
    if dir_fd is not None or isinstance(path, int):
        return False
    try:
        return os.path.abspath(os.fspath(path)) in _PROTECTED
    except TypeError:
        return False


_real_os_open = os.open
_real_open = builtins.open


def _guarded_os_open(path, flags, mode=0o777, *, dir_fd=None):
    if _is_protected(path, dir_fd):
        raise IsolationViolation("real configuration read blocked by test isolation")
    return _real_os_open(path, flags, mode, dir_fd=dir_fd)


def _guarded_open(file, *args, **kwargs):
    if _is_protected(file):
        raise IsolationViolation("real configuration read blocked by test isolation")
    return _real_open(file, *args, **kwargs)


os.open = _guarded_os_open
builtins.open = _guarded_open
io.open = _guarded_open
sys.bizqlab_test_isolation = True

if os.environ.get("BQ_ENTRYPOINT_SCENARIO"):
    import entrypoint_harness

    entrypoint_harness.install(os.environ["BQ_ENTRYPOINT_SCENARIO"])
