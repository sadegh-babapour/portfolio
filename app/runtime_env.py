"""Runtime mode and development database resolution (M1 local-db-isolation).

In plain words: before anything connects, decide "am I production or a developer's
machine?" and, on a developer machine, which single database is allowed. Production must
prove itself (Railway's ID variables plus a build attestation file written during the
Railway build); a laptop reads its target only from the strict .env.local profile and
must match the root-owned policy file. Anything ambiguous is refused. This is the fix for
the stray .env that once pointed the Mac at production (docs/lessons/02 and 04).

The three runtime_* modules split the job:
- runtime_env (this file): read and validate settings; pure, no I/O to databases;
- runtime_state: remember the decision for this process and revoke it if settings change;
- runtime_db: open connections that first ask the server "who are you?" and compare.


Batch 1 scope: pure classification, parsing and validation, mirrored exactly by
``backend/transit_api/config/runtimeEnv.js``. Nothing in this module connects to
a database, mutates ``os.environ``, or caches state. Callers pass the inherited
environment explicitly. See ``openspec/changes/local-db-isolation/design.md``.

Errors carry a code plus optional key name and line number. They never carry a
value, and sanitized errors are raised outside ``except`` blocks so that
``__cause__`` and ``__context__`` are both ``None``.
"""
from __future__ import annotations

import errno
import os
import re
import stat as stat_module
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping
from urllib.parse import quote

RUNTIME_KEY = "BIZQLAB_RUNTIME"
MARKER_KEYS = ("RAILWAY_PROJECT_ID", "RAILWAY_ENVIRONMENT_ID", "RAILWAY_SERVICE_ID")
COMMIT_KEY = "RAILWAY_GIT_COMMIT_SHA"
DATABASE_URL_KEY = "DATABASE_URL"

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = REPO_ROOT / ".env.local"
POLICY_PATHS = {
    "darwin": "/Library/Application Support/Bizqlab/db-policy.json",
    "linux": "/etc/bizqlab/db-policy.json",
}

BUILD_ROOT = "."
# One fixed file directly inside each trusted build root; no subdirectory, no legacy fallback.
ATTESTATION_FILENAME = ".bizqlab-build-attestation.json"
ATTESTATION_KIND = "bizqlab-railway-build"
ATTESTATION_KEYS = (
    "schema", "kind", "build_root", "railway_service_id",
    "railway_environment_id", "git_commit", "generated_at",
)

PROFILE_MAX_BYTES = 64 * 1024
PROFILE_LINE_MAX_BYTES = 4096
POLICY_MAX_BYTES = 4 * 1024
ATTESTATION_MAX_BYTES = 1024
JSON_MAX_DEPTH = 16
JSON_MAX_INT_DIGITS = 15

REQUIRED_DB_KEYS = ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGSSLMODE")
OPTIONAL_DB_KEYS = ("PGCONNECT_TIMEOUT", "PGAPPNAME")
NONDB_ALLOWLIST = frozenset({
    "APP_ENV", "RESUME_PDF_PATH",
    "CONTACT_PUBLIC_BASE_URL", "CONTACT_ALLOWED_ORIGINS", "CONTACT_TOKEN_PEPPER",
    "CONTACT_IP_HASH_KEY", "CONTACT_FROM_EMAIL", "CONTACT_TO_EMAIL",
    "TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY", "TURNSTILE_EXPECTED_HOSTNAMES",
    "RESEND_API_KEY",
    "AUTH_PUBLIC_BASE_URL", "GOOGLE_OIDC_CLIENT_ID", "GOOGLE_OIDC_CLIENT_SECRET",
    "AUTH_ADMIN_GOOGLE_SUBJECTS", "AUTH_ADMIN_EMAILS", "AUTH_SESSION_TTL_HOURS",
    "AUTH_LOGIN_STATE_TTL_MINUTES", "AUTH_EVENT_RETENTION_DAYS", "ANALYTICS_RETENTION_DAYS",
    "TRANSIT_API_PORT", "VITE_TRANSIT_API_BASE_URL",
    "POLL_INTERVAL_SECONDS", "POLL_ENABLED", "POLL_START_HOUR", "POLL_END_HOUR",
    "POLL_TIMEZONE", "ADMIN_KILL_SWITCH", "RAW_RETENTION_MINUTES",
})
RESERVED_KEY_PREFIXES = ("BIZQLAB_", "RAILWAY_")
PROCESS_CONTROL_KEYS = frozenset({
    "PATH", "HOME", "SHELL", "USER", "LOGNAME", "TMPDIR", "IFS", "ENV", "BASH_ENV",
    "PS4", "SHELLOPTS", "PROMPT_COMMAND", "LANG", "LC_ALL", "TZ",
})
PROCESS_CONTROL_PREFIXES = ("PYTHON", "NODE_", "NPM_CONFIG_", "LD_", "DYLD_", "PIP_", "UV_")
RESERVED_DATABASES = frozenset({"postgres", "template0", "template1", "trading", "railway"})
RAILWAY_HOST_SUFFIXES = ("railway.internal", "rlwy.net", "railway.app")

# CLI flag -> the profile key it must agree with (poller and static bootstrap).
CLI_DB_FLAGS = {
    "--database-url": DATABASE_URL_KEY,
    "--host": "PGHOST",
    "--port": "PGPORT",
    "--dbname": "PGDATABASE",
    "--user": "PGUSER",
    "--password": "PGPASSWORD",
}

DEFAULT_CONNECT_TIMEOUT = 10
SSLMODES = ("disable", "require")

_KEY_RE = re.compile(r"[A-Z][A-Z0-9_]*")
_IDENT_RE = re.compile(r"[A-Za-z0-9_.-]{1,63}")
_PORT_RE = re.compile(r"[1-9][0-9]{0,4}")
_TIMEOUT_RE = re.compile(r"[1-9][0-9]?")
_PURPOSE_RE = re.compile(r"[a-z0-9-]{1,20}")
_RAILWAY_ID_RE = re.compile(r"[A-Za-z0-9-]{1,64}")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_GENERATED_AT_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_LABEL_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_NUMERIC_LABEL_RE = re.compile(r"[0-9]+|0x[0-9a-f]*")
_IPV4_OCTET_RE = re.compile(r"0|[1-9][0-9]{0,2}")
_HEXTET_RE = re.compile(r"[0-9a-f]{1,4}")


class RuntimeConfigError(RuntimeError):
    """A configuration refusal. Carries a code, and optionally a key and line, never a value."""

    def __init__(self, code: str, *, key: str | None = None, line: int | None = None):
        self.code = code
        self.key = key
        self.line = line
        super().__init__(format_error(code, key, line))

    def __repr__(self) -> str:
        return f"RuntimeConfigError({str(self)!r})"


def format_error(code: str, key: str | None = None, line: int | None = None) -> str:
    message = code
    if key is not None:
        message += f" [key={key}]"
    if line is not None:
        message += f" [line={line}]"
    return message


# --------------------------------------------------------------------------- mode


def classify_markers(env: Mapping[str, str]) -> str:
    """``complete`` (all set and non-empty), ``absent`` (none set) or ``partial``."""
    present = [key in env for key in MARKER_KEYS]
    if not any(present):
        return "absent"
    if all(present) and all(env[key] != "" for key in MARKER_KEYS):
        return "complete"
    return "partial"


def decide_mode_row(
    env: Mapping[str, str],
    attestation: str | Callable[[], str],
    *,
    policy_present: bool,
    profile_present: bool,
) -> tuple[int, str]:
    """Apply design §3.2 in order. Returns ``(row, outcome)``.

    ``outcome`` is ``production``, ``development`` or an error code.
    ``attestation`` is a status (``valid``, ``absent``, ``invalid:<code>``) or a
    zero-argument callable returning one; it is evaluated only at row 4.
    """
    mode = env.get(RUNTIME_KEY)
    markers = classify_markers(env)
    if mode is not None and mode not in ("production", "development"):
        return 1, "invalid_mode"
    if markers == "partial":
        return 2, "incomplete_railway_context"
    if markers == "complete" and (policy_present or profile_present):
        return 3, "railway_context_on_workstation"
    if mode == "production":
        if markers == "complete":
            status = attestation() if callable(attestation) else attestation
            if status == "valid":
                return 4, "production"
        return 5, "production_not_attested"
    if markers == "complete":
        return 6, "railway_context_without_production_mode"
    return 7, "development"


def decide_mode(env, attestation, *, policy_present: bool, profile_present: bool) -> str:
    """Return ``production`` or ``development``; raise ``RuntimeConfigError`` otherwise."""
    _row, outcome = decide_mode_row(
        env, attestation, policy_present=policy_present, profile_present=profile_present
    )
    if outcome not in ("production", "development"):
        raise RuntimeConfigError(outcome)
    return outcome


def _present(fs, path) -> bool:
    """W indicator via the injected provider; unexpected errors count as present."""
    try:
        return fs.lstat(path) is not None
    except OSError:
        return True


def path_exists_nofollow(path, lstat=os.lstat) -> bool:
    """Existence by ``lstat``. Unexpected errors count as present (fail closed)."""
    absent = False
    try:
        lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        absent = True
    except OSError:
        return True
    return not absent


def workstation_indicators(policy_file: str, profile_file, lstat=os.lstat) -> tuple[bool, bool]:
    return path_exists_nofollow(policy_file, lstat), path_exists_nofollow(profile_file, lstat)


# ------------------------------------------------------------------- file reads


@dataclass(frozen=True)
class StatInfo:
    kind: str  # file | dir | symlink | other
    uid: int
    mode: int  # permission and special bits only
    size: int


def _stat_info(st) -> StatInfo:
    if stat_module.S_ISLNK(st.st_mode):
        kind = "symlink"
    elif stat_module.S_ISREG(st.st_mode):
        kind = "file"
    elif stat_module.S_ISDIR(st.st_mode):
        kind = "dir"
    else:
        kind = "other"
    return StatInfo(kind, st.st_uid, stat_module.S_IMODE(st.st_mode), st.st_size)


class FileReadError(Exception):
    def __init__(self, reason: str):
        self.reason = reason  # missing | symlink | not_regular | too_large | unreadable
        super().__init__(reason)


_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)


def read_nofollow(path, max_bytes: int, *, dir_fd: int | None = None) -> tuple[bytes, StatInfo]:
    """Open without following a final symlink, then ``fstat`` and read the same descriptor."""
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | _O_CLOEXEC
    reason = None
    try:
        fd = os.open(path, flags, dir_fd=dir_fd)
    except (FileNotFoundError, NotADirectoryError):
        reason = "missing"
    except OSError as exc:
        reason = "symlink" if exc.errno == errno.ELOOP else "unreadable"
    if reason is not None:
        raise FileReadError(reason)
    try:
        result = _read_descriptor(fd, max_bytes)
    except OSError:
        result = None
    finally:
        os.close(fd)
    if result is None:
        raise FileReadError("unreadable")
    return result


def read_in_root(root, name: str, max_bytes: int) -> tuple[bytes, StatInfo]:
    """Read the file ``name`` directly inside ``root``.

    The root (the trust anchor, derived from the module location) is opened as a
    directory, and the file is opened relative to that descriptor with no-follow,
    then checked and read through its own descriptor. There is no intermediate
    component to replace.
    """
    if not name or "/" in name or name in (".", ".."):
        raise ValueError("name must be a single path component")
    reason = None
    try:
        dir_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | _O_CLOEXEC)
    except (FileNotFoundError, NotADirectoryError):
        reason = "missing"
    except OSError:
        reason = "unreadable"
    if reason is not None:
        raise FileReadError(reason)
    try:
        return read_nofollow(name, max_bytes, dir_fd=dir_fd)
    finally:
        os.close(dir_fd)


def _read_descriptor(fd: int, max_bytes: int) -> tuple[bytes, StatInfo]:
    info = _stat_info(os.fstat(fd))
    if info.kind != "file":
        raise FileReadError("not_regular")
    if info.size > max_bytes:
        raise FileReadError("too_large")
    chunks = []
    total = 0
    while total <= max_bytes:
        chunk = os.read(fd, max_bytes + 1 - total)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    if total > max_bytes:
        raise FileReadError("too_large")
    return b"".join(chunks), info


# ---------------------------------------------------------------- strict JSON


class JsonFloat:
    """A non-integer JSON number. Valid JSON, but never a valid value for any field."""

    def __init__(self, text: str):
        self.text = text


class _JsonSyntaxError(Exception):
    pass


def parse_strict_json(data: bytes):
    """Strict JSON identical to the Node implementation.

    Rejects duplicate keys, non-JSON constants, integers over 15 digits and
    nesting deeper than 16. Non-integer numbers become ``JsonFloat``.
    """
    text = data.decode("utf-8")  # strict; UnicodeDecodeError propagates
    parser = _JsonParser(text)
    parser.ws()
    value = parser.value(0)
    parser.ws()
    if parser.pos != len(text):
        raise _JsonSyntaxError()
    return value


class _JsonParser:
    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def ws(self):
        while self.pos < len(self.text) and self.text[self.pos] in " \t\n\r":
            self.pos += 1

    def peek(self):
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def expect(self, literal: str):
        if not self.text.startswith(literal, self.pos):
            raise _JsonSyntaxError()
        self.pos += len(literal)

    def value(self, depth: int):
        ch = self.peek()
        if ch == "{":
            return self.object(depth + 1)
        if ch == "[":
            return self.array(depth + 1)
        if ch == '"':
            return self.string()
        if ch == "t":
            self.expect("true")
            return True
        if ch == "f":
            self.expect("false")
            return False
        if ch == "n":
            self.expect("null")
            return None
        if ch == "-" or "0" <= ch <= "9":
            return self.number()
        raise _JsonSyntaxError()

    def object(self, depth: int):
        if depth > JSON_MAX_DEPTH:
            raise _JsonSyntaxError()
        self.pos += 1
        out: dict = {}
        self.ws()
        if self.peek() == "}":
            self.pos += 1
            return out
        while True:
            self.ws()
            if self.peek() != '"':
                raise _JsonSyntaxError()
            key = self.string()
            if key in out:
                raise _JsonSyntaxError()
            self.ws()
            self.expect(":")
            self.ws()
            out[key] = self.value(depth)
            self.ws()
            ch = self.peek()
            self.pos += 1
            if ch == "}":
                return out
            if ch != ",":
                raise _JsonSyntaxError()

    def array(self, depth: int):
        if depth > JSON_MAX_DEPTH:
            raise _JsonSyntaxError()
        self.pos += 1
        out: list = []
        self.ws()
        if self.peek() == "]":
            self.pos += 1
            return out
        while True:
            self.ws()
            out.append(self.value(depth))
            self.ws()
            ch = self.peek()
            self.pos += 1
            if ch == "]":
                return out
            if ch != ",":
                raise _JsonSyntaxError()

    def string(self) -> str:
        self.pos += 1
        units: list[int] = []  # UTF-16 code units, so surrogate handling matches JavaScript
        text = self.text
        while True:
            if self.pos >= len(text):
                raise _JsonSyntaxError()
            ch = text[self.pos]
            self.pos += 1
            if ch == '"':
                return _utf16_to_str(units)
            if ch == "\\":
                esc = self.peek()
                self.pos += 1
                simple = {'"': 0x22, "\\": 0x5C, "/": 0x2F, "b": 0x08, "f": 0x0C,
                          "n": 0x0A, "r": 0x0D, "t": 0x09}
                if esc in simple:
                    units.append(simple[esc])
                elif esc == "u":
                    digits = text[self.pos:self.pos + 4]
                    if len(digits) != 4 or not all(c in "0123456789abcdefABCDEF" for c in digits):
                        raise _JsonSyntaxError()
                    units.append(int(digits, 16))
                    self.pos += 4
                else:
                    raise _JsonSyntaxError()
            elif ord(ch) < 0x20:
                raise _JsonSyntaxError()
            else:
                code = ord(ch)
                if code > 0xFFFF:
                    code -= 0x10000
                    units.extend((0xD800 + (code >> 10), 0xDC00 + (code & 0x3FF)))
                else:
                    units.append(code)

    def number(self):
        start = self.pos
        text = self.text
        if self.peek() == "-":
            self.pos += 1
        if self.peek() == "0":
            self.pos += 1
        elif "1" <= self.peek() <= "9":
            while "0" <= self.peek() <= "9":
                self.pos += 1
        else:
            raise _JsonSyntaxError()
        is_float = False
        if self.peek() == ".":
            is_float = True
            self.pos += 1
            if not "0" <= self.peek() <= "9":
                raise _JsonSyntaxError()
            while "0" <= self.peek() <= "9":
                self.pos += 1
        if self.peek() in ("e", "E"):
            is_float = True
            self.pos += 1
            if self.peek() in ("+", "-"):
                self.pos += 1
            if not "0" <= self.peek() <= "9":
                raise _JsonSyntaxError()
            while "0" <= self.peek() <= "9":
                self.pos += 1
        literal = text[start:self.pos]
        if is_float:
            return JsonFloat(literal)
        if len(literal.lstrip("-")) > JSON_MAX_INT_DIGITS:
            raise _JsonSyntaxError()
        return int(literal)


def _utf16_to_str(units: list[int]) -> str:
    out = []
    i = 0
    while i < len(units):
        unit = units[i]
        if 0xD800 <= unit <= 0xDBFF and i + 1 < len(units) and 0xDC00 <= units[i + 1] <= 0xDFFF:
            out.append(chr(0x10000 + ((unit - 0xD800) << 10) + (units[i + 1] - 0xDC00)))
            i += 2
        else:
            out.append(chr(unit))
            i += 1
    return "".join(out)


def _is_int(value) -> bool:
    return type(value) is int


def _try_parse_json(data: bytes):
    """Return ``(True, value)`` or ``(False, None)`` without exposing the parser exception."""
    try:
        return True, parse_strict_json(data)
    except (UnicodeDecodeError, _JsonSyntaxError, ValueError):
        return False, None


# ---------------------------------------------------------------- attestation


def classify_attestation_bytes(data: bytes, *, build_root: str, env: Mapping[str, str]) -> str:
    """Classify attestation content as ``valid`` or ``invalid:<code>`` (design §3.4)."""
    ok, doc = _try_parse_json(data)
    if not ok:
        return "invalid:malformed"
    if not isinstance(doc, dict):
        return "invalid:not_object"
    for key in ATTESTATION_KEYS:
        if key not in doc:
            return "invalid:missing_key"
    for key in doc:
        if key not in ATTESTATION_KEYS:
            return "invalid:unknown_key"
    if not (_is_int(doc["schema"]) and doc["schema"] == 1):
        return "invalid:schema"
    if not isinstance(doc["kind"], str) or doc["kind"] != ATTESTATION_KIND:
        return "invalid:kind"
    if not isinstance(doc["build_root"], str) or doc["build_root"] != build_root:
        return "invalid:build_root"
    for field, label in (("railway_service_id", "service_id"),
                         ("railway_environment_id", "environment_id")):
        value = doc[field]
        if not isinstance(value, str):
            return f"invalid:{label}_type"
        if not _RAILWAY_ID_RE.fullmatch(value):
            return f"invalid:{label}_format"
    commit = doc["git_commit"]
    if commit is not None and not isinstance(commit, str):
        return "invalid:commit_type"
    if isinstance(commit, str) and not _COMMIT_RE.fullmatch(commit):
        return "invalid:commit_format"
    generated_at = doc["generated_at"]
    if not isinstance(generated_at, str) or not _GENERATED_AT_RE.fullmatch(generated_at):
        return "invalid:generated_at"
    if env.get("RAILWAY_SERVICE_ID") != doc["railway_service_id"]:
        return "invalid:service_mismatch"
    if env.get("RAILWAY_ENVIRONMENT_ID") != doc["railway_environment_id"]:
        return "invalid:environment_mismatch"
    if commit is not None:
        runtime_commit = env.get(COMMIT_KEY)
        if not runtime_commit:
            return "invalid:commit_missing"
        if runtime_commit != commit:
            return "invalid:commit_mismatch"
    return "valid"


def read_attestation(build_root_dir, *, build_root: str = BUILD_ROOT, env: Mapping[str, str],
                     reader=read_in_root) -> str:
    """Read ``<build_root_dir>/.bizqlab-build-attestation.json`` and classify it.

    The marker must be a regular file directly inside the build root; a symlink is refused.
    """
    reason = None
    try:
        data, _info = reader(os.fspath(build_root_dir), ATTESTATION_FILENAME, ATTESTATION_MAX_BYTES)
    except FileReadError as exc:
        reason = exc.reason
    if reason == "missing":
        return "absent"
    if reason is not None:
        return f"invalid:{reason}"
    return classify_attestation_bytes(data, build_root=build_root, env=env)


# ------------------------------------------------------------- profile grammar


def _has_control(text: str) -> bool:
    for ch in text:
        code = ord(ch)
        if (code < 0x20 and ch != "\t") or 0x7F <= code <= 0x9F:
            return True
    return False


def parse_profile(data: bytes) -> dict[str, str]:
    """Parse ``.env.local`` bytes per design §4.1. Raises ``RuntimeConfigError``."""
    if len(data) == 0:
        raise RuntimeConfigError("profile_empty")
    if data.startswith(b"\xef\xbb\xbf"):
        raise RuntimeConfigError("profile_bom", line=1)
    raw_lines = data.split(b"\n")
    terminated = [True] * (len(raw_lines) - 1) + [False]
    if raw_lines[-1] == b"":
        raw_lines.pop()
        terminated.pop()
    result: dict[str, str] = {}
    for index, raw in enumerate(raw_lines):
        number = index + 1
        if raw.endswith(b"\r") and terminated[index]:
            raw = raw[:-1]
        if b"\r" in raw:
            raise RuntimeConfigError("profile_lone_cr", line=number)
        if len(raw) > PROFILE_LINE_MAX_BYTES:
            raise RuntimeConfigError("profile_line_too_long", line=number)
        failed = False
        try:
            line = raw.decode("utf-8")
        except UnicodeDecodeError:
            failed = True
        if failed:
            raise RuntimeConfigError("profile_invalid_utf8", line=number)
        if _has_control(line):
            raise RuntimeConfigError("profile_control_char", line=number)
        stripped = line.lstrip(" \t")
        if stripped == "" or stripped.startswith("#"):
            continue
        if stripped != line:
            raise RuntimeConfigError("profile_leading_whitespace", line=number)
        if line.startswith("export ") or line.startswith("export\t"):
            raise RuntimeConfigError("profile_export", line=number)
        if "=" not in line:
            raise RuntimeConfigError("profile_missing_equals", line=number)
        key, value = line.split("=", 1)
        if key != key.rstrip(" \t"):
            raise RuntimeConfigError("profile_space_around_equals", line=number)
        if not _KEY_RE.fullmatch(key):
            raise RuntimeConfigError("profile_invalid_key", line=number)
        if value[:1] in (" ", "\t"):
            raise RuntimeConfigError("profile_space_around_equals", key=key, line=number)
        result_value = _parse_value(value, key, number)
        if key in result:
            raise RuntimeConfigError("profile_duplicate_key", key=key, line=number)
        result[key] = result_value
    return result


def _parse_value(value: str, key: str, number: int) -> str:
    if value[:1] in ('"', "'"):
        quote_char = value[0]
        inner = value[1:-1]
        if len(value) < 2 or value[-1] != quote_char or quote_char in inner:
            raise RuntimeConfigError("profile_mismatched_quotes", key=key, line=number)
    else:
        inner = value
        if inner != inner.rstrip(" \t"):
            raise RuntimeConfigError("profile_trailing_whitespace", key=key, line=number)
        if inner[-1:] in ('"', "'"):
            raise RuntimeConfigError("profile_mismatched_quotes", key=key, line=number)
        if " #" in inner:
            raise RuntimeConfigError("profile_unquoted_hash", key=key, line=number)
    if "${" in inner:
        raise RuntimeConfigError("profile_interpolation", key=key, line=number)
    return inner


def read_profile(path=PROFILE_PATH, reader=read_nofollow) -> dict[str, str]:
    reason = None
    try:
        data, _info = reader(path, PROFILE_MAX_BYTES)
    except FileReadError as exc:
        reason = exc.reason
    if reason is not None:
        raise RuntimeConfigError(f"profile_{reason}")
    return parse_profile(data)


def classify_key(key: str) -> str:
    """``db_required``, ``db_optional``, ``nondb``, or an error code."""
    if key == DATABASE_URL_KEY or key.startswith(RESERVED_KEY_PREFIXES):
        return "reserved_key"
    if key in PROCESS_CONTROL_KEYS or key.startswith(PROCESS_CONTROL_PREFIXES):
        return "reserved_key"
    if key in REQUIRED_DB_KEYS:
        return "db_required"
    if key in OPTIONAL_DB_KEYS:
        return "db_optional"
    if key.startswith("PG"):
        return "unsupported_pg_key"
    if key in NONDB_ALLOWLIST:
        return "nondb"
    return "unknown_key"


def split_profile(profile: Mapping[str, str]) -> tuple[dict[str, str], dict[str, str]]:
    """Split into DB and allowlisted non-DB keys; reject everything else by name."""
    db: dict[str, str] = {}
    nondb: dict[str, str] = {}
    for key, value in profile.items():
        kind = classify_key(key)
        if kind in ("db_required", "db_optional"):
            db[key] = value
        elif kind == "nondb":
            nondb[key] = value
        else:
            raise RuntimeConfigError(kind, key=key)
    for key in REQUIRED_DB_KEYS:
        if key not in db:
            raise RuntimeConfigError("missing_key", key=key)
    return db, nondb


# ----------------------------------------------------------------- components


def parse_ipv4(text: str) -> tuple[int, int, int, int] | None:
    parts = text.split(".")
    if len(parts) != 4 or not all(_IPV4_OCTET_RE.fullmatch(p) for p in parts):
        return None
    octets = tuple(int(p) for p in parts)
    if any(o > 255 for o in octets):
        return None
    return octets  # type: ignore[return-value]


def parse_ipv6(text: str) -> tuple[int, ...] | None:
    """Parse lowercase hex IPv6 without zone or embedded IPv4. Returns 8 hextets."""
    if text.count("::") > 1:
        return None
    if "::" in text:
        head, tail = text.split("::")
        head_parts = head.split(":") if head else []
        tail_parts = tail.split(":") if tail else []
        if len(head_parts) + len(tail_parts) > 7:
            return None
        parts = head_parts + ["0"] * (8 - len(head_parts) - len(tail_parts)) + tail_parts
    else:
        parts = text.split(":")
        if len(parts) != 8:
            return None
    if not all(_HEXTET_RE.fullmatch(p) for p in parts):
        return None
    return tuple(int(p, 16) for p in parts)


def format_ipv6(hextets: tuple[int, ...]) -> str:
    """RFC 5952 canonical text: longest zero run (length >= 2, leftmost) becomes ``::``."""
    best_start, best_len = -1, 0
    i = 0
    while i < 8:
        if hextets[i] == 0:
            j = i
            while j < 8 and hextets[j] == 0:
                j += 1
            if j - i > best_len:
                best_start, best_len = i, j - i
            i = j
        else:
            i += 1
    words = [format(h, "x") for h in hextets]
    if best_len < 2:
        return ":".join(words)
    return ":".join(words[:best_start]) + "::" + ":".join(words[best_start + best_len:])


def _ipv4_allowed(o: tuple[int, int, int, int]) -> bool:
    return (
        o[0] == 10
        or (o[0] == 172 and 16 <= o[1] <= 31)
        or (o[0] == 192 and o[1] == 168)
        or (o[0] == 100 and 64 <= o[1] <= 127)
        or o[0] == 127
    )


def _ipv6_allowed(h: tuple[int, ...]) -> bool:
    return h == (0, 0, 0, 0, 0, 0, 0, 1) or (h[0] & 0xFE00) == 0xFC00


def classify_ip_literal(text: str) -> str:
    """``ipv4``/``ipv6`` (canonical and private), ``public_address``, ``invalid_host``, or ``hostname``."""
    if ":" in text:
        hextets = parse_ipv6(text)
        if hextets is None or format_ipv6(hextets) != text:
            return "invalid_host"
        return "ipv6" if _ipv6_allowed(hextets) else "public_address"
    if all(c in "0123456789." for c in text):
        octets = parse_ipv4(text)
        if octets is None:
            return "invalid_host"
        return "ipv4" if _ipv4_allowed(octets) else "public_address"
    return "hostname"


def validate_host(value: str, key: str = "PGHOST") -> str:
    if not value:
        raise RuntimeConfigError("invalid_host", key=key)
    kind = classify_ip_literal(value)
    if kind in ("invalid_host", "public_address"):
        raise RuntimeConfigError(kind, key=key)
    if kind == "hostname":
        if len(value) > 253:
            raise RuntimeConfigError("invalid_host", key=key)
        labels = value.split(".")
        if not all(_LABEL_RE.fullmatch(label) for label in labels):
            raise RuntimeConfigError("invalid_host", key=key)
        if _NUMERIC_LABEL_RE.fullmatch(labels[-1]):
            raise RuntimeConfigError("invalid_host", key=key)
        if "railway" in labels or any(
            value == suffix or value.endswith("." + suffix) for suffix in RAILWAY_HOST_SUFFIXES
        ):
            raise RuntimeConfigError("railway_host", key=key)
    return value


def validate_port_text(value: str, key: str = "PGPORT") -> int:
    if not _PORT_RE.fullmatch(value) or int(value) > 65535:
        raise RuntimeConfigError("invalid_port", key=key)
    return int(value)


def validate_identifier(value: str, key: str, *, database: bool) -> str:
    if not _IDENT_RE.fullmatch(value):
        raise RuntimeConfigError("invalid_identifier", key=key)
    if database and value.lower() in RESERVED_DATABASES:
        raise RuntimeConfigError("reserved_database", key=key)
    return value


def validate_password(value: str, key: str = "PGPASSWORD") -> str:
    if not 1 <= len(value) <= 1024 or "\x00" in value:
        raise RuntimeConfigError("invalid_password", key=key)
    return value


def validate_server_address(value) -> str:
    if not isinstance(value, str) or classify_ip_literal(value) not in ("ipv4", "ipv6"):
        raise RuntimeConfigError("policy_invalid_value", key="server_addresses")
    return value


# --------------------------------------------------------------------- policy


@dataclass(frozen=True)
class PolicyTarget:
    host: str
    port: int
    database: str
    role: str
    server_addresses: tuple[str, ...]
    server_port: int


POLICY_TOP_KEYS = ("schema", "development_target")
POLICY_TARGET_KEYS = ("host", "port", "database", "role", "server_addresses", "server_port")


class RealFs:
    """The real filesystem provider. Tests inject a fake with the same four methods."""

    def lstat(self, path) -> StatInfo | None:
        try:
            return _stat_info(os.lstat(path))
        except (FileNotFoundError, NotADirectoryError):
            return None

    def access_writable(self, path) -> bool:
        return os.access(path, os.W_OK)

    def realpath(self, path) -> str:
        return os.path.realpath(path)

    def read_nofollow(self, path, max_bytes: int) -> tuple[bytes, StatInfo]:
        return read_nofollow(path, max_bytes)

    def read_in_root(self, root, name: str, max_bytes: int) -> tuple[bytes, StatInfo]:
        return read_in_root(root, name, max_bytes)


def policy_path(platform: str | None = None) -> str:
    platform = sys.platform if platform is None else platform
    if platform not in POLICY_PATHS:
        raise RuntimeConfigError("policy_unsupported_platform")
    return POLICY_PATHS[platform]


def _check_owner_and_mode(info: StatInfo, writable: bool) -> str | None:
    if info.uid != 0:
        return "policy_not_root_owned"
    if info.mode & 0o022:
        return "policy_writable_mode"
    if writable:
        return "policy_writable_acl"
    return None


def load_policy(path: str | None = None, fs=None, *, platform: str | None = None) -> PolicyTarget:
    """Load and validate the root-owned policy (design §4.2). Raises ``RuntimeConfigError``."""
    path = policy_path(platform) if path is None else path
    fs = RealFs() if fs is None else fs
    code = None
    try:
        code = _policy_metadata_failure(path, fs)
    except OSError:
        code = "policy_unreadable"
    if code is not None:
        raise RuntimeConfigError(code)

    reason = None
    try:
        data, info = fs.read_nofollow(path, POLICY_MAX_BYTES)
    except FileReadError as exc:
        reason = exc.reason
    if reason is not None:
        raise RuntimeConfigError(f"policy_{reason}")
    code = _check_owner_and_mode(info, False)
    if code is not None:
        raise RuntimeConfigError(code)
    return parse_policy(data)


def _policy_metadata_failure(path: str, fs) -> str | None:
    pure = PurePosixPath(path)
    if not pure.is_absolute() or ".." in pure.parts:
        return "policy_symlink"
    chain = [str(p) for p in reversed(pure.parents)] + [path]
    for index, component in enumerate(chain):
        info = fs.lstat(component)
        if info is None:
            return "policy_missing"
        if info.kind == "symlink":
            return "policy_symlink"
        expected = "file" if index == len(chain) - 1 else "dir"
        if info.kind != expected:
            return "policy_not_regular" if expected == "file" else "policy_not_directory"
        code = _check_owner_and_mode(info, fs.access_writable(component))
        if code is not None:
            return code
    if fs.realpath(path) != path:
        return "policy_symlink"
    return None


def _contains_password_key(value) -> bool:
    if isinstance(value, dict):
        return any(k.lower() == "password" or _contains_password_key(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_contains_password_key(v) for v in value)
    return False


def _exact_keys(doc: dict, keys: tuple[str, ...]) -> None:
    for key in keys:
        if key not in doc:
            raise RuntimeConfigError("policy_missing_key", key=key)
    for key in sorted(doc):  # sorted so the reported key matches Node, whose objects reorder keys
        if key not in keys:
            raise RuntimeConfigError("policy_unknown_key", key=key)


def parse_policy(data: bytes) -> PolicyTarget:
    ok, doc = _try_parse_json(data)
    if not ok or not isinstance(doc, dict):
        raise RuntimeConfigError("policy_malformed")
    if _contains_password_key(doc):
        raise RuntimeConfigError("policy_password_key")
    _exact_keys(doc, POLICY_TOP_KEYS)
    if not (_is_int(doc["schema"]) and doc["schema"] == 1):
        raise RuntimeConfigError("policy_invalid_value", key="schema")
    target = doc["development_target"]
    if not isinstance(target, dict):
        raise RuntimeConfigError("policy_invalid_value", key="development_target")
    _exact_keys(target, POLICY_TARGET_KEYS)
    for key in ("host", "database", "role"):
        if not isinstance(target[key], str):
            raise RuntimeConfigError("policy_invalid_value", key=key)
    for key in ("port", "server_port"):
        if not (_is_int(target[key]) and 1 <= target[key] <= 65535):
            raise RuntimeConfigError("policy_invalid_value", key=key)
    addresses = target["server_addresses"]
    if not isinstance(addresses, list) or not 1 <= len(addresses) <= 16:
        raise RuntimeConfigError("policy_invalid_value", key="server_addresses")
    addresses = tuple(validate_server_address(a) for a in addresses)
    if len(set(addresses)) != len(addresses):
        raise RuntimeConfigError("policy_invalid_value", key="server_addresses")
    validate_host(target["host"], key="host")
    validate_identifier(target["database"], "database", database=True)
    validate_identifier(target["role"], "role", database=False)
    return PolicyTarget(
        host=target["host"], port=target["port"], database=target["database"],
        role=target["role"], server_addresses=addresses, server_port=target["server_port"],
    )


# ----------------------------------------------------------------- resolution


@dataclass(frozen=True, repr=False)
class DevelopmentTarget:
    host: str
    port: int
    database: str
    user: str
    password: str
    sslmode: str
    connect_timeout: int
    application_name: str
    explicit_options: tuple[str, ...]  # optional keys present in the profile

    def __repr__(self) -> str:
        return (
            f"DevelopmentTarget(host={self.host!r}, port={self.port}, database={self.database!r}, "
            f"user={self.user!r}, password='***', sslmode={self.sslmode!r}, "
            f"connect_timeout={self.connect_timeout}, application_name={self.application_name!r})"
        )

    __str__ = __repr__

    def psycopg2_kwargs(self) -> dict:
        """Keyword arguments for ``psycopg2.connect`` per the design §4.1 mapping table."""
        return {
            "host": self.host, "port": self.port, "dbname": self.database,
            "user": self.user, "password": self.password, "sslmode": self.sslmode,
            "connect_timeout": self.connect_timeout, "application_name": self.application_name,
        }

    def url_query(self) -> dict[str, str]:
        query = {"sslmode": self.sslmode, "connect_timeout": str(self.connect_timeout)}
        if "PGAPPNAME" in self.explicit_options:
            query["application_name"] = self.application_name
        return query

    def database_url(self) -> str:
        return compose_database_url(self)

    def sqlalchemy_url(self):
        from sqlalchemy.engine import URL

        return URL.create(
            drivername="postgresql+psycopg2", username=self.user, password=self.password,
            host=self.host, port=self.port, database=self.database, query=self.url_query(),
        )


def _pct(value: str) -> str:
    return quote(value, safe="")


def compose_database_url(target: DevelopmentTarget) -> str:
    """Canonical exported URL. Every component is fully percent-encoded (RFC 3986 unreserved kept)."""
    host = f"[{target.host}]" if ":" in target.host else target.host
    query = "&".join(f"{k}={_pct(v)}" for k, v in target.url_query().items())
    return (
        f"postgresql+psycopg2://{_pct(target.user)}:{_pct(target.password)}@{host}:"
        f"{target.port}/{_pct(target.database)}?{query}"
    )


URL_SCHEMES = ("postgresql+psycopg2", "postgresql")
URL_QUERY_KEYS = ("sslmode", "connect_timeout", "application_name")
_URL_CHARS_RE = re.compile(r"[\x21-\x7e]*")
_PCT_TEXT_RE = re.compile(r"(?:[A-Za-z0-9._~-]|%[0-9A-Fa-f]{2})*")


def _pct_decode(text: str) -> str | None:
    """Strict percent-decoding: unreserved characters and %XX only, UTF-8 result."""
    if not _PCT_TEXT_RE.fullmatch(text):
        return None
    out = bytearray()
    i = 0
    while i < len(text):
        if text[i] == "%":
            out.append(int(text[i + 1:i + 3], 16))
            i += 3
        else:
            out.append(ord(text[i]))
            i += 1
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError:
        return None


def parse_database_url(url) -> dict | None:
    """Strictly parse an inherited or CLI database URL into components; ``None`` if not accepted.

    Accepted form: ``<scheme>://<user>:<password>@<host>:<port>/<database>[?<query>]`` with
    scheme in ``URL_SCHEMES``. User and password may be percent-encoded; host (IPv6 in
    brackets) and database must appear literally; the port is required. Query keys are
    limited to ``URL_QUERY_KEYS``, each at most once, in any order. Anything else (other
    libpq parameters such as ``host``/``hostaddr``/``options``, multiple hosts, fragments,
    ``+``, raw non-ASCII) is refused, so an equal-looking URL cannot redirect libpq.
    """
    if not isinstance(url, str) or not _URL_CHARS_RE.fullmatch(url) or "#" in url:
        return None
    scheme, sep, rest = url.partition("://")
    if not sep or scheme not in URL_SCHEMES:
        return None
    main, qsep, query = rest.partition("?")
    if qsep and not query:
        return None
    authority, slash, database = main.partition("/")
    if not slash or "/" in database or authority.count("@") != 1:
        return None
    userinfo, hostport = authority.split("@")
    if userinfo.count(":") != 1:
        return None
    user_text, password_text = userinfo.split(":")
    user, password = _pct_decode(user_text), _pct_decode(password_text)
    if user is None or password is None:
        return None
    if hostport.startswith("["):
        close = hostport.find("]")
        if close == -1 or ":" not in hostport[1:close] or not hostport[close + 1:].startswith(":"):
            return None
        host, port_text = hostport[1:close], hostport[close + 2:]
    else:
        if hostport.count(":") != 1:
            return None
        host, port_text = hostport.split(":")
    if not _PORT_RE.fullmatch(port_text) or int(port_text) > 65535:
        return None
    params: dict[str, str] = {}
    if qsep:
        for item in query.split("&"):
            if item.count("=") != 1:
                return None
            key, value_text = item.split("=")
            value = _pct_decode(value_text)
            if key not in URL_QUERY_KEYS or key in params or value is None:
                return None
            params[key] = value
    return {"scheme": scheme, "user": user, "password": password, "host": host,
            "port": int(port_text), "database": database, "query": params}


def database_url_matches(url, target: DevelopmentTarget) -> bool:
    """Component equality between a supplied URL and the resolved target (design §4.4).

    Requires ``sslmode`` and ``connect_timeout`` equal to the target's;
    ``application_name`` is optional but must be equal when present. In Python the
    URL must also parse to the same components through SQLAlchemy and libpq.
    """
    parsed = parse_database_url(url)
    if parsed is None:
        return False
    query = parsed["query"]
    if (parsed["user"], parsed["password"], parsed["host"], parsed["port"], parsed["database"]) != (
        target.user, target.password, target.host, target.port, target.database
    ):
        return False
    if query.get("sslmode") != target.sslmode or query.get("connect_timeout") != str(target.connect_timeout):
        return False
    if "application_name" in query and query["application_name"] != target.application_name:
        return False
    agree = False
    try:
        agree = _parsers_agree(url, parsed)
    except Exception:  # noqa: BLE001 - parser messages may contain the URL
        agree = False
    return agree


def _parsers_agree(url: str, parsed: dict) -> bool:
    from psycopg2.extensions import parse_dsn
    from sqlalchemy.engine import make_url

    sa = make_url(url)
    sqlalchemy_ok = (
        sa.drivername == parsed["scheme"] and sa.username == parsed["user"]
        and sa.password == parsed["password"] and sa.host == parsed["host"]
        and sa.port == parsed["port"] and sa.database == parsed["database"]
        and dict(sa.query) == parsed["query"]
    )
    libpq = parse_dsn("postgresql" + url[len(parsed["scheme"]):])
    expected = {"user": parsed["user"], "password": parsed["password"], "host": parsed["host"],
                "port": str(parsed["port"]), "dbname": parsed["database"], **parsed["query"]}
    return sqlalchemy_ok and libpq == expected


def verify_url_round_trip(target: DevelopmentTarget, url: str) -> None:
    """Both SQLAlchemy and libpq must recover every component exactly; values never surface."""
    ok = False
    try:
        ok = _round_trip_equal(target, url)
    except Exception:  # noqa: BLE001 - parser messages may contain the URL
        ok = False
    if not ok:
        raise RuntimeConfigError("url_round_trip_failed", key=DATABASE_URL_KEY)


def _round_trip_equal(target: DevelopmentTarget, url: str) -> bool:
    from psycopg2.extensions import parse_dsn
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    sqlalchemy_ok = (
        parsed.drivername == "postgresql+psycopg2"
        and parsed.username == target.user and parsed.password == target.password
        and parsed.host == target.host and parsed.port == target.port
        and parsed.database == target.database and dict(parsed.query) == target.url_query()
    )
    libpq = parse_dsn("postgresql" + url[len("postgresql+psycopg2"):])
    expected = {
        "user": target.user, "password": target.password, "host": target.host,
        "port": str(target.port), "dbname": target.database, **target.url_query(),
    }
    return sqlalchemy_ok and libpq == expected


def default_application_name(purpose: str) -> str:
    if not _PURPOSE_RE.fullmatch(purpose):
        raise RuntimeConfigError("invalid_purpose")
    return f"bizqlab-dev-{purpose}"


def _option_values(db: Mapping[str, str], purpose: str) -> tuple[str, int, str]:
    sslmode = db["PGSSLMODE"]
    if sslmode not in SSLMODES:
        raise RuntimeConfigError("invalid_value", key="PGSSLMODE")
    timeout = DEFAULT_CONNECT_TIMEOUT
    if "PGCONNECT_TIMEOUT" in db:
        text = db["PGCONNECT_TIMEOUT"]
        if not _TIMEOUT_RE.fullmatch(text) or not 1 <= int(text) <= 60:
            raise RuntimeConfigError("invalid_value", key="PGCONNECT_TIMEOUT")
        timeout = int(text)
    appname = default_application_name(purpose)
    if "PGAPPNAME" in db:
        appname = db["PGAPPNAME"]
        if not _IDENT_RE.fullmatch(appname):
            raise RuntimeConfigError("invalid_value", key="PGAPPNAME")
    return sslmode, timeout, appname


def _effective_option_text(target: DevelopmentTarget, key: str) -> str:
    return {
        "PGHOST": target.host, "PGPORT": str(target.port), "PGDATABASE": target.database,
        "PGUSER": target.user, "PGPASSWORD": target.password, "PGSSLMODE": target.sslmode,
        "PGCONNECT_TIMEOUT": str(target.connect_timeout), "PGAPPNAME": target.application_name,
    }[key]


@dataclass(frozen=True, repr=False)
class DevelopmentResolution:
    target: DevelopmentTarget
    database_url: str
    nondb: dict
    policy: PolicyTarget | None = None  # the approved identity, for connection verification

    def __repr__(self) -> str:
        return f"DevelopmentResolution(target={self.target!r}, nondb_keys={sorted(self.nondb)})"

    __str__ = __repr__


def resolve_development_target(
    profile: Mapping[str, str],
    policy: PolicyTarget,
    *,
    inherited_env: Mapping[str, str],
    purpose: str,
    cli: Mapping[str, object] | None = None,
    round_trip: bool = True,
) -> DevelopmentResolution:
    """Combine profile, policy, inherited environment and CLI flags into one identity.

    Pure: no I/O and no environment mutation. Raises ``RuntimeConfigError`` naming
    only the key at fault.
    """
    db, nondb = split_profile(profile)
    host = validate_host(db["PGHOST"])
    port = validate_port_text(db["PGPORT"])
    database = validate_identifier(db["PGDATABASE"], "PGDATABASE", database=True)
    user = validate_identifier(db["PGUSER"], "PGUSER", database=False)
    password = validate_password(db["PGPASSWORD"])
    sslmode, timeout, appname = _option_values(db, purpose)

    for key, profile_value, policy_value in (
        ("PGHOST", host, policy.host), ("PGPORT", port, policy.port),
        ("PGDATABASE", database, policy.database), ("PGUSER", user, policy.role),
    ):
        if profile_value != policy_value:
            raise RuntimeConfigError("policy_mismatch", key=key)

    target = DevelopmentTarget(
        host=host, port=port, database=database, user=user, password=password,
        sslmode=sslmode, connect_timeout=timeout, application_name=appname,
        explicit_options=tuple(k for k in OPTIONAL_DB_KEYS if k in db),
    )
    url = compose_database_url(target)

    for key in sorted(inherited_env):
        if key == DATABASE_URL_KEY:
            if not database_url_matches(inherited_env[key], target):
                raise RuntimeConfigError("inherited_conflict", key=key)
        elif key.startswith("PG"):
            if key not in REQUIRED_DB_KEYS and key not in OPTIONAL_DB_KEYS:
                raise RuntimeConfigError("inherited_pg_key", key=key)
            if inherited_env[key] != _effective_option_text(target, key):
                raise RuntimeConfigError("inherited_conflict", key=key)

    for flag, value in (cli or {}).items():
        if flag not in CLI_DB_FLAGS:
            raise RuntimeConfigError("unknown_cli_flag", key=flag)
        if value is None:
            continue
        mapped = CLI_DB_FLAGS[flag]
        if mapped == DATABASE_URL_KEY:
            equal = isinstance(value, str) and database_url_matches(value, target)
        else:
            equal = not isinstance(value, bool) and str(value) == _effective_option_text(target, mapped)
        if not equal:
            raise RuntimeConfigError("cli_conflict", key=flag)

    if round_trip:
        verify_url_round_trip(target, url)
    return DevelopmentResolution(target=target, database_url=url, nondb=dict(nondb), policy=policy)


# ------------------------------------------------------------------- combined


@dataclass(frozen=True, repr=False)
class RuntimeResolution:
    mode: str
    development: DevelopmentResolution | None

    def __repr__(self) -> str:
        return f"RuntimeResolution(mode={self.mode!r}, development={self.development!r})"

    __str__ = __repr__


def resolve_runtime(
    env: Mapping[str, str],
    *,
    purpose: str,
    cli: Mapping[str, object] | None = None,
    profile_path=PROFILE_PATH,
    policy_file: str | None = None,
    build_root_dir=REPO_ROOT,
    fs=None,
    platform: str | None = None,
) -> RuntimeResolution:
    """Classify the runtime and, in development, resolve the approved identity.

    Reads files only; never connects and never mutates ``env``. In production
    the target stays ``None``: production parameters are unchanged (design §5).
    """
    fs = RealFs() if fs is None else fs
    if policy_file is None:
        try:
            policy_file = policy_path(platform)
        except RuntimeConfigError:
            policy_file = None
    policy_present = policy_file is not None and _present(fs, policy_file)
    profile_present = _present(fs, profile_path)
    mode = decide_mode(
        env,
        lambda: read_attestation(build_root_dir, build_root=BUILD_ROOT, env=env,
                                 reader=fs.read_in_root),
        policy_present=policy_present,
        profile_present=profile_present,
    )
    if mode == "production":
        return RuntimeResolution(mode=mode, development=None)
    if policy_file is None:
        raise RuntimeConfigError("policy_unsupported_platform")
    profile = read_profile(profile_path, reader=fs.read_nofollow)
    policy = load_policy(policy_file, fs)
    development = resolve_development_target(profile, policy, inherited_env=env,
                                             purpose=purpose, cli=cli)
    return RuntimeResolution(mode=mode, development=development)
