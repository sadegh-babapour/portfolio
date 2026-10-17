"use strict";
/**
 * Runtime mode and development database resolution (M1 local-db-isolation).
 *
 * Pure classification, parsing and validation, mirroring app/runtime_env.py
 * exactly (same check order, same error codes). Nothing here connects to a
 * database, mutates process.env, or caches state; config/runtimeState.js holds
 * the process state. Callers pass the inherited environment explicitly. Node 22
 * APIs only.
 *
 * Errors carry a code plus optional key name and line number, never a value, and
 * are always new Error objects with no `cause`.
 */
const fs = require("node:fs");
const path = require("node:path");
const util = require("node:util");

const RUNTIME_KEY = "BIZQLAB_RUNTIME";
const MARKER_KEYS = ["RAILWAY_PROJECT_ID", "RAILWAY_ENVIRONMENT_ID", "RAILWAY_SERVICE_ID"];
const COMMIT_KEY = "RAILWAY_GIT_COMMIT_SHA";
const DATABASE_URL_KEY = "DATABASE_URL";

const BUILD_ROOT_DIR = path.resolve(__dirname, "..");
const REPO_ROOT = path.resolve(BUILD_ROOT_DIR, "..", "..");
const PROFILE_PATH = path.join(REPO_ROOT, ".env.local");
const REPO_ROOT_SENTINEL = path.join(REPO_ROOT, "scripts", "bootstrap_transit_db.py");
const POLICY_PATHS = {
  darwin: "/Library/Application Support/Bizqlab/db-policy.json",
  linux: "/etc/bizqlab/db-policy.json",
};

const BUILD_ROOT = "backend/transit_api";
// One fixed file directly inside each trusted build root; no subdirectory, no legacy fallback.
const ATTESTATION_FILENAME = ".bizqlab-build-attestation.json";
const ATTESTATION_KIND = "bizqlab-railway-build";
const ATTESTATION_KEYS = [
  "schema", "kind", "build_root", "railway_service_id",
  "railway_environment_id", "git_commit", "generated_at",
];

const PROFILE_MAX_BYTES = 64 * 1024;
const PROFILE_LINE_MAX_BYTES = 4096;
const POLICY_MAX_BYTES = 4 * 1024;
const ATTESTATION_MAX_BYTES = 1024;
const JSON_MAX_DEPTH = 16;
const JSON_MAX_INT_DIGITS = 15;

const REQUIRED_DB_KEYS = ["PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGSSLMODE"];
const OPTIONAL_DB_KEYS = ["PGCONNECT_TIMEOUT", "PGAPPNAME"];
const NONDB_ALLOWLIST = new Set([
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
]);
const RESERVED_KEY_PREFIXES = ["BIZQLAB_", "RAILWAY_"];
const PROCESS_CONTROL_KEYS = new Set([
  "PATH", "HOME", "SHELL", "USER", "LOGNAME", "TMPDIR", "IFS", "ENV", "BASH_ENV",
  "PS4", "SHELLOPTS", "PROMPT_COMMAND", "LANG", "LC_ALL", "TZ",
]);
const PROCESS_CONTROL_PREFIXES = ["PYTHON", "NODE_", "NPM_CONFIG_", "LD_", "DYLD_", "PIP_", "UV_"];
const RESERVED_DATABASES = new Set(["postgres", "template0", "template1", "trading", "railway"]);
const RAILWAY_HOST_SUFFIXES = ["railway.internal", "rlwy.net", "railway.app"];

const CLI_DB_FLAGS = {
  "--database-url": DATABASE_URL_KEY,
  "--host": "PGHOST",
  "--port": "PGPORT",
  "--dbname": "PGDATABASE",
  "--user": "PGUSER",
  "--password": "PGPASSWORD",
};

const DEFAULT_CONNECT_TIMEOUT = 10;
const SSLMODES = ["disable", "require"];

const KEY_RE = /^[A-Z][A-Z0-9_]*$/;
const IDENT_RE = /^[A-Za-z0-9_.-]{1,63}$/;
const PORT_RE = /^[1-9][0-9]{0,4}$/;
const TIMEOUT_RE = /^[1-9][0-9]?$/;
const PURPOSE_RE = /^[a-z0-9-]{1,20}$/;
const RAILWAY_ID_RE = /^[A-Za-z0-9-]{1,64}$/;
const COMMIT_RE = /^[0-9a-f]{40}$/;
const GENERATED_AT_RE = /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/;
const LABEL_RE = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;
const NUMERIC_LABEL_RE = /^(?:[0-9]+|0x[0-9a-f]*)$/;
const IPV4_OCTET_RE = /^(?:0|[1-9][0-9]{0,2})$/;
const HEXTET_RE = /^[0-9a-f]{1,4}$/;

const hasOwn = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);

function formatError(code, key = null, line = null) {
  let message = code;
  if (key !== null && key !== undefined) message += ` [key=${key}]`;
  if (line !== null && line !== undefined) message += ` [line=${line}]`;
  return message;
}

/** A configuration refusal. Carries a code, and optionally a key and line, never a value. */
class RuntimeConfigError extends Error {
  constructor(code, { key = null, line = null } = {}) {
    super(formatError(code, key, line));
    this.name = "RuntimeConfigError";
    this.code = code;
    this.key = key;
    this.line = line;
  }
}

/** Code-point order, matching Python's sorted() on str. */
function compareCodePoints(a, b) {
  const x = Array.from(a);
  const y = Array.from(b);
  for (let i = 0; i < Math.min(x.length, y.length); i += 1) {
    const d = x[i].codePointAt(0) - y[i].codePointAt(0);
    if (d !== 0) return d;
  }
  return x.length - y.length;
}

const lstripWs = (s) => s.replace(/^[ \t]+/, "");
const rstripWs = (s) => s.replace(/[ \t]+$/, "");

// ------------------------------------------------------------------- mode

function classifyMarkers(env) {
  const present = MARKER_KEYS.map((key) => hasOwn(env, key));
  if (!present.some(Boolean)) return "absent";
  if (present.every(Boolean) && MARKER_KEYS.every((key) => env[key] !== "")) return "complete";
  return "partial";
}

/**
 * Apply design §3.2 in order. Returns [row, outcome]; outcome is "production",
 * "development" or an error code. `attestation` is a status or a zero-argument
 * function returning one; it is evaluated only at row 4.
 */
function decideModeRow(env, attestation, { policyPresent, profilePresent }) {
  const mode = hasOwn(env, RUNTIME_KEY) ? env[RUNTIME_KEY] : undefined;
  const markers = classifyMarkers(env);
  if (mode !== undefined && mode !== "production" && mode !== "development") return [1, "invalid_mode"];
  if (markers === "partial") return [2, "incomplete_railway_context"];
  if (markers === "complete" && (policyPresent || profilePresent)) return [3, "railway_context_on_workstation"];
  if (mode === "production") {
    if (markers === "complete") {
      const status = typeof attestation === "function" ? attestation() : attestation;
      if (status === "valid") return [4, "production"];
    }
    return [5, "production_not_attested"];
  }
  if (markers === "complete") return [6, "railway_context_without_production_mode"];
  return [7, "development"];
}

function decideMode(env, attestation, indicators) {
  const [, outcome] = decideModeRow(env, attestation, indicators);
  if (outcome !== "production" && outcome !== "development") throw new RuntimeConfigError(outcome);
  return outcome;
}

/** Existence by lstat. Unexpected errors count as present (fail closed). */
function pathExistsNoFollow(p) {
  try {
    fs.lstatSync(p);
    return true;
  } catch (error) {
    return !(error && (error.code === "ENOENT" || error.code === "ENOTDIR"));
  }
}

function workstationIndicators(policyFile, profileFile) {
  return [pathExistsNoFollow(policyFile), pathExistsNoFollow(profileFile)];
}

// -------------------------------------------------------------- file reads

function statInfo(st) {
  let kind = "other";
  if (st.isSymbolicLink()) kind = "symlink";
  else if (st.isFile()) kind = "file";
  else if (st.isDirectory()) kind = "dir";
  return { kind, uid: st.uid, mode: st.mode & 0o7777, size: st.size, dev: st.dev, ino: st.ino };
}

class FileReadError extends Error {
  constructor(reason) {
    super(reason);
    this.name = "FileReadError";
    this.reason = reason; // missing | symlink | not_regular | too_large | unreadable
  }
}

/** Open without following a final symlink, then fstat and read the same descriptor. */
function readNoFollow(p, maxBytes, fsImpl = fs) {
  const flags = fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK;
  let fd;
  let reason = null;
  try {
    fd = fsImpl.openSync(p, flags);
  } catch (error) {
    const code = error && error.code;
    if (code === "ENOENT" || code === "ENOTDIR") reason = "missing";
    else if (code === "ELOOP") reason = "symlink";
    else reason = "unreadable";
  }
  if (reason !== null) throw new FileReadError(reason);
  try {
    return readDescriptor(fd, maxBytes, fsImpl);
  } catch (error) {
    if (error instanceof FileReadError) throw error;
    throw new FileReadError("unreadable");
  } finally {
    fsImpl.closeSync(fd);
  }
}

function readDescriptor(fd, maxBytes, fsImpl) {
  const info = statInfo(fsImpl.fstatSync(fd));
  if (info.kind !== "file") throw new FileReadError("not_regular");
  if (info.size > maxBytes) throw new FileReadError("too_large");
  const buffer = Buffer.alloc(maxBytes + 1);
  let total = 0;
  while (total <= maxBytes) {
    const n = fsImpl.readSync(fd, buffer, total, maxBytes + 1 - total, null);
    if (n === 0) break;
    total += n;
  }
  if (total > maxBytes) throw new FileReadError("too_large");
  return [Buffer.from(buffer.subarray(0, total)), info];
}

/**
 * Read the file `name` directly inside `root`. The root is the trust anchor (derived
 * from the module location); like Python's O_DIRECTORY open, a root that is not a
 * directory counts as missing. The file is opened with O_NOFOLLOW and then checked and
 * read through that descriptor, so there is no intermediate component to replace.
 */
function readInRoot(root, name, maxBytes, fsImpl = fs) {
  if (!name || name.includes("/") || name === "." || name === "..") {
    throw new Error("name must be a single path component");
  }
  let rootIsDir = false;
  try {
    rootIsDir = fsImpl.statSync(root).isDirectory();
  } catch (error) {
    if (!(error && (error.code === "ENOENT" || error.code === "ENOTDIR"))) throw new FileReadError("unreadable");
  }
  if (!rootIsDir) throw new FileReadError("missing");
  return readNoFollow(path.join(root, name), maxBytes, fsImpl);
}

// ------------------------------------------------------------- strict JSON

/** A non-integer JSON number. Valid JSON, but never a valid value for any field. */
class JsonFloat {
  constructor(text) {
    this.text = text;
  }
}

class JsonSyntaxError extends Error {}

function decodeUtf8Strict(bytes) {
  return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
}

/** Strict JSON identical to the Python implementation. */
function parseStrictJson(bytes) {
  const text = decodeUtf8Strict(bytes);
  const parser = new JsonParser(text);
  parser.ws();
  const value = parser.value(0);
  parser.ws();
  if (parser.pos !== text.length) throw new JsonSyntaxError();
  return value;
}

const JSON_ESCAPES = { '"': 0x22, "\\": 0x5c, "/": 0x2f, b: 0x08, f: 0x0c, n: 0x0a, r: 0x0d, t: 0x09 };
const isDigit = (ch) => ch >= "0" && ch <= "9" && ch.length === 1;

class JsonParser {
  constructor(text) {
    this.text = text;
    this.pos = 0;
  }

  ws() {
    while (this.pos < this.text.length && " \t\n\r".includes(this.text[this.pos])) this.pos += 1;
  }

  peek() {
    return this.pos < this.text.length ? this.text[this.pos] : "";
  }

  expect(literal) {
    if (!this.text.startsWith(literal, this.pos)) throw new JsonSyntaxError();
    this.pos += literal.length;
  }

  value(depth) {
    const ch = this.peek();
    if (ch === "{") return this.object(depth + 1);
    if (ch === "[") return this.array(depth + 1);
    if (ch === '"') return this.string();
    if (ch === "t") { this.expect("true"); return true; }
    if (ch === "f") { this.expect("false"); return false; }
    if (ch === "n") { this.expect("null"); return null; }
    if (ch === "-" || isDigit(ch)) return this.number();
    throw new JsonSyntaxError();
  }

  object(depth) {
    if (depth > JSON_MAX_DEPTH) throw new JsonSyntaxError();
    this.pos += 1;
    const out = Object.create(null);
    this.ws();
    if (this.peek() === "}") { this.pos += 1; return out; }
    for (;;) {
      this.ws();
      if (this.peek() !== '"') throw new JsonSyntaxError();
      const key = this.string();
      if (hasOwn(out, key)) throw new JsonSyntaxError();
      this.ws();
      this.expect(":");
      this.ws();
      out[key] = this.value(depth);
      this.ws();
      const ch = this.peek();
      this.pos += 1;
      if (ch === "}") return out;
      if (ch !== ",") throw new JsonSyntaxError();
    }
  }

  array(depth) {
    if (depth > JSON_MAX_DEPTH) throw new JsonSyntaxError();
    this.pos += 1;
    const out = [];
    this.ws();
    if (this.peek() === "]") { this.pos += 1; return out; }
    for (;;) {
      this.ws();
      out.push(this.value(depth));
      this.ws();
      const ch = this.peek();
      this.pos += 1;
      if (ch === "]") return out;
      if (ch !== ",") throw new JsonSyntaxError();
    }
  }

  string() {
    this.pos += 1;
    const units = [];
    const { text } = this;
    for (;;) {
      if (this.pos >= text.length) throw new JsonSyntaxError();
      const ch = text[this.pos];
      this.pos += 1;
      if (ch === '"') {
        let out = "";
        for (let i = 0; i < units.length; i += 4096) out += String.fromCharCode(...units.slice(i, i + 4096));
        return out;
      }
      if (ch === "\\") {
        const esc = this.peek();
        this.pos += 1;
        if (hasOwn(JSON_ESCAPES, esc)) {
          units.push(JSON_ESCAPES[esc]);
        } else if (esc === "u") {
          const digits = text.slice(this.pos, this.pos + 4);
          if (!/^[0-9a-fA-F]{4}$/.test(digits)) throw new JsonSyntaxError();
          units.push(parseInt(digits, 16));
          this.pos += 4;
        } else {
          throw new JsonSyntaxError();
        }
      } else if (ch.charCodeAt(0) < 0x20) {
        throw new JsonSyntaxError();
      } else {
        units.push(ch.charCodeAt(0));
      }
    }
  }

  number() {
    const start = this.pos;
    if (this.peek() === "-") this.pos += 1;
    if (this.peek() === "0") {
      this.pos += 1;
    } else if (this.peek() >= "1" && this.peek() <= "9" && this.peek().length === 1) {
      while (isDigit(this.peek())) this.pos += 1;
    } else {
      throw new JsonSyntaxError();
    }
    let isFloat = false;
    if (this.peek() === ".") {
      isFloat = true;
      this.pos += 1;
      if (!isDigit(this.peek())) throw new JsonSyntaxError();
      while (isDigit(this.peek())) this.pos += 1;
    }
    if (this.peek() === "e" || this.peek() === "E") {
      isFloat = true;
      this.pos += 1;
      if (this.peek() === "+" || this.peek() === "-") this.pos += 1;
      if (!isDigit(this.peek())) throw new JsonSyntaxError();
      while (isDigit(this.peek())) this.pos += 1;
    }
    const literal = this.text.slice(start, this.pos);
    if (isFloat) return new JsonFloat(literal);
    if (literal.replace(/^-/, "").length > JSON_MAX_INT_DIGITS) throw new JsonSyntaxError();
    return Number(literal);
  }
}

const isInt = (v) => typeof v === "number" && Number.isInteger(v);
const isStr = (v) => typeof v === "string";
const isObject = (v) => v !== null && typeof v === "object" && !Array.isArray(v) && !(v instanceof JsonFloat);

/** Returns [true, value] or [false, null] without exposing the parser exception. */
function tryParseJson(bytes) {
  try {
    return [true, parseStrictJson(bytes)];
  } catch {
    return [false, null];
  }
}

// ------------------------------------------------------------- attestation

/** Classify attestation content as "valid" or "invalid:<code>" (design §3.4). */
function classifyAttestationBytes(bytes, { buildRoot, env }) {
  const [ok, doc] = tryParseJson(bytes);
  if (!ok) return "invalid:malformed";
  if (!isObject(doc)) return "invalid:not_object";
  for (const key of ATTESTATION_KEYS) if (!hasOwn(doc, key)) return "invalid:missing_key";
  for (const key of Object.keys(doc)) if (!ATTESTATION_KEYS.includes(key)) return "invalid:unknown_key";
  if (!(isInt(doc.schema) && doc.schema === 1)) return "invalid:schema";
  if (!isStr(doc.kind) || doc.kind !== ATTESTATION_KIND) return "invalid:kind";
  if (!isStr(doc.build_root) || doc.build_root !== buildRoot) return "invalid:build_root";
  for (const [field, label] of [["railway_service_id", "service_id"], ["railway_environment_id", "environment_id"]]) {
    const value = doc[field];
    if (!isStr(value)) return `invalid:${label}_type`;
    if (!RAILWAY_ID_RE.test(value)) return `invalid:${label}_format`;
  }
  const commit = doc.git_commit;
  if (commit !== null && !isStr(commit)) return "invalid:commit_type";
  if (isStr(commit) && !COMMIT_RE.test(commit)) return "invalid:commit_format";
  if (!isStr(doc.generated_at) || !GENERATED_AT_RE.test(doc.generated_at)) return "invalid:generated_at";
  const get = (key) => (hasOwn(env, key) ? env[key] : undefined);
  if (get("RAILWAY_SERVICE_ID") !== doc.railway_service_id) return "invalid:service_mismatch";
  if (get("RAILWAY_ENVIRONMENT_ID") !== doc.railway_environment_id) return "invalid:environment_mismatch";
  if (commit !== null) {
    const runtimeCommit = get(COMMIT_KEY);
    if (!runtimeCommit) return "invalid:commit_missing";
    if (runtimeCommit !== commit) return "invalid:commit_mismatch";
  }
  return "valid";
}

/** Read <buildRootDir>/.bizqlab-build-attestation.json; it must be a regular file, not a symlink. */
function readAttestation(buildRootDir, { buildRoot = BUILD_ROOT, env, reader = readInRoot }) {
  let reason = null;
  let bytes;
  try {
    [bytes] = reader(buildRootDir, ATTESTATION_FILENAME, ATTESTATION_MAX_BYTES);
  } catch (error) {
    reason = error instanceof FileReadError ? error.reason : "unreadable";
  }
  if (reason === "missing") return "absent";
  if (reason !== null) return `invalid:${reason}`;
  return classifyAttestationBytes(bytes, { buildRoot, env });
}

// --------------------------------------------------------- profile grammar

function hasControl(text) {
  for (const ch of text) {
    const code = ch.codePointAt(0);
    if ((code < 0x20 && ch !== "\t") || (code >= 0x7f && code <= 0x9f)) return true;
  }
  return false;
}

/** Parse .env.local bytes per design §4.1. Throws RuntimeConfigError. */
function parseProfile(bytes) {
  const data = Buffer.from(bytes);
  if (data.length === 0) throw new RuntimeConfigError("profile_empty");
  if (data.length >= 3 && data[0] === 0xef && data[1] === 0xbb && data[2] === 0xbf) {
    throw new RuntimeConfigError("profile_bom", { line: 1 });
  }
  const rawLines = [];
  let start = 0;
  for (let i = 0; i < data.length; i += 1) {
    if (data[i] === 0x0a) {
      rawLines.push([data.subarray(start, i), true]);
      start = i + 1;
    }
  }
  if (start < data.length) rawLines.push([data.subarray(start), false]);

  const result = Object.create(null);
  const order = [];
  rawLines.forEach(([rawLine, terminated], index) => {
    const number = index + 1;
    let raw = rawLine;
    if (terminated && raw.length > 0 && raw[raw.length - 1] === 0x0d) raw = raw.subarray(0, raw.length - 1);
    if (raw.includes(0x0d)) throw new RuntimeConfigError("profile_lone_cr", { line: number });
    if (raw.length > PROFILE_LINE_MAX_BYTES) throw new RuntimeConfigError("profile_line_too_long", { line: number });
    let line;
    let failed = false;
    try {
      line = decodeUtf8Strict(raw);
    } catch {
      failed = true;
    }
    if (failed) throw new RuntimeConfigError("profile_invalid_utf8", { line: number });
    if (hasControl(line)) throw new RuntimeConfigError("profile_control_char", { line: number });
    const stripped = lstripWs(line);
    if (stripped === "" || stripped.startsWith("#")) return;
    if (stripped !== line) throw new RuntimeConfigError("profile_leading_whitespace", { line: number });
    if (line.startsWith("export ") || line.startsWith("export\t")) {
      throw new RuntimeConfigError("profile_export", { line: number });
    }
    const eq = line.indexOf("=");
    if (eq === -1) throw new RuntimeConfigError("profile_missing_equals", { line: number });
    const key = line.slice(0, eq);
    const value = line.slice(eq + 1);
    if (key !== rstripWs(key)) throw new RuntimeConfigError("profile_space_around_equals", { line: number });
    if (!KEY_RE.test(key)) throw new RuntimeConfigError("profile_invalid_key", { line: number });
    if (value.startsWith(" ") || value.startsWith("\t")) {
      throw new RuntimeConfigError("profile_space_around_equals", { key, line: number });
    }
    const parsed = parseValue(value, key, number);
    if (hasOwn(result, key)) throw new RuntimeConfigError("profile_duplicate_key", { key, line: number });
    result[key] = parsed;
    order.push(key);
  });
  const ordered = {};
  for (const key of order) ordered[key] = result[key];
  return ordered;
}

function parseValue(value, key, number) {
  let inner;
  const first = value.slice(0, 1);
  if (first === '"' || first === "'") {
    inner = value.slice(1, -1);
    if (value.length < 2 || value[value.length - 1] !== first || inner.includes(first)) {
      throw new RuntimeConfigError("profile_mismatched_quotes", { key, line: number });
    }
  } else {
    inner = value;
    if (inner !== rstripWs(inner)) throw new RuntimeConfigError("profile_trailing_whitespace", { key, line: number });
    const last = inner.slice(-1);
    if (last === '"' || last === "'") throw new RuntimeConfigError("profile_mismatched_quotes", { key, line: number });
    if (inner.includes(" #")) {
      throw new RuntimeConfigError("profile_unquoted_hash", { key, line: number });
    }
  }
  if (inner.includes("${")) throw new RuntimeConfigError("profile_interpolation", { key, line: number });
  return inner;
}

function readProfile(p = PROFILE_PATH, reader = readNoFollow) {
  let reason = null;
  let bytes;
  try {
    [bytes] = reader(p, PROFILE_MAX_BYTES);
  } catch (error) {
    reason = error instanceof FileReadError ? error.reason : "unreadable";
  }
  if (reason !== null) throw new RuntimeConfigError(`profile_${reason}`);
  return parseProfile(bytes);
}

function classifyKey(key) {
  if (key === DATABASE_URL_KEY || RESERVED_KEY_PREFIXES.some((p) => key.startsWith(p))) return "reserved_key";
  if (PROCESS_CONTROL_KEYS.has(key) || PROCESS_CONTROL_PREFIXES.some((p) => key.startsWith(p))) return "reserved_key";
  if (REQUIRED_DB_KEYS.includes(key)) return "db_required";
  if (OPTIONAL_DB_KEYS.includes(key)) return "db_optional";
  if (key.startsWith("PG")) return "unsupported_pg_key";
  if (NONDB_ALLOWLIST.has(key)) return "nondb";
  return "unknown_key";
}

function splitProfile(profile) {
  const db = {};
  const nondb = {};
  for (const [key, value] of Object.entries(profile)) {
    const kind = classifyKey(key);
    if (kind === "db_required" || kind === "db_optional") db[key] = value;
    else if (kind === "nondb") nondb[key] = value;
    else throw new RuntimeConfigError(kind, { key });
  }
  for (const key of REQUIRED_DB_KEYS) if (!hasOwn(db, key)) throw new RuntimeConfigError("missing_key", { key });
  return [db, nondb];
}

// -------------------------------------------------------------- components

function parseIpv4(text) {
  const parts = text.split(".");
  if (parts.length !== 4 || !parts.every((p) => IPV4_OCTET_RE.test(p))) return null;
  const octets = parts.map(Number);
  if (octets.some((o) => o > 255)) return null;
  return octets;
}

/** Parse lowercase hex IPv6 without zone or embedded IPv4. Returns 8 hextets. */
function parseIpv6(text) {
  const doubles = text.split("::").length - 1;
  if (doubles > 1) return null;
  let parts;
  if (doubles === 1) {
    const [head, tail] = text.split("::");
    const headParts = head ? head.split(":") : [];
    const tailParts = tail ? tail.split(":") : [];
    if (headParts.length + tailParts.length > 7) return null;
    parts = [...headParts, ...Array(8 - headParts.length - tailParts.length).fill("0"), ...tailParts];
  } else {
    parts = text.split(":");
    if (parts.length !== 8) return null;
  }
  if (!parts.every((p) => HEXTET_RE.test(p))) return null;
  return parts.map((p) => parseInt(p, 16));
}

/** RFC 5952 canonical text: longest zero run (length >= 2, leftmost) becomes "::". */
function formatIpv6(hextets) {
  let bestStart = -1;
  let bestLen = 0;
  let i = 0;
  while (i < 8) {
    if (hextets[i] === 0) {
      let j = i;
      while (j < 8 && hextets[j] === 0) j += 1;
      if (j - i > bestLen) { bestStart = i; bestLen = j - i; }
      i = j;
    } else {
      i += 1;
    }
  }
  const words = hextets.map((h) => h.toString(16));
  if (bestLen < 2) return words.join(":");
  return `${words.slice(0, bestStart).join(":")}::${words.slice(bestStart + bestLen).join(":")}`;
}

function ipv4Allowed(o) {
  return o[0] === 10 || (o[0] === 172 && o[1] >= 16 && o[1] <= 31) || (o[0] === 192 && o[1] === 168)
    || (o[0] === 100 && o[1] >= 64 && o[1] <= 127) || o[0] === 127;
}

function ipv6Allowed(h) {
  const loopback = h.slice(0, 7).every((x) => x === 0) && h[7] === 1;
  return loopback || (h[0] & 0xfe00) === 0xfc00;
}

function classifyIpLiteral(text) {
  if (text.includes(":")) {
    const hextets = parseIpv6(text);
    if (hextets === null || formatIpv6(hextets) !== text) return "invalid_host";
    return ipv6Allowed(hextets) ? "ipv6" : "public_address";
  }
  if (/^[0-9.]*$/.test(text)) {
    const octets = parseIpv4(text);
    if (octets === null) return "invalid_host";
    return ipv4Allowed(octets) ? "ipv4" : "public_address";
  }
  return "hostname";
}

function validateHost(value, key = "PGHOST") {
  if (!value) throw new RuntimeConfigError("invalid_host", { key });
  const kind = classifyIpLiteral(value);
  if (kind === "invalid_host" || kind === "public_address") throw new RuntimeConfigError(kind, { key });
  if (kind === "hostname") {
    if (value.length > 253) throw new RuntimeConfigError("invalid_host", { key });
    const labels = value.split(".");
    if (!labels.every((label) => LABEL_RE.test(label))) throw new RuntimeConfigError("invalid_host", { key });
    if (NUMERIC_LABEL_RE.test(labels[labels.length - 1])) throw new RuntimeConfigError("invalid_host", { key });
    if (labels.includes("railway")
      || RAILWAY_HOST_SUFFIXES.some((suffix) => value === suffix || value.endsWith(`.${suffix}`))) {
      throw new RuntimeConfigError("railway_host", { key });
    }
  }
  return value;
}

function validatePortText(value, key = "PGPORT") {
  if (!PORT_RE.test(value) || Number(value) > 65535) throw new RuntimeConfigError("invalid_port", { key });
  return Number(value);
}

function validateIdentifier(value, key, { database }) {
  if (!IDENT_RE.test(value)) throw new RuntimeConfigError("invalid_identifier", { key });
  if (database && RESERVED_DATABASES.has(value.toLowerCase())) throw new RuntimeConfigError("reserved_database", { key });
  return value;
}

function validatePassword(value, key = "PGPASSWORD") {
  const length = Array.from(value).length;
  if (length < 1 || length > 1024 || value.includes("\u0000")) throw new RuntimeConfigError("invalid_password", { key });
  return value;
}

function validateServerAddress(value) {
  if (!isStr(value) || !["ipv4", "ipv6"].includes(classifyIpLiteral(value))) {
    throw new RuntimeConfigError("policy_invalid_value", { key: "server_addresses" });
  }
  return value;
}

// ------------------------------------------------------------------ policy

const POLICY_TOP_KEYS = ["schema", "development_target"];
const POLICY_TARGET_KEYS = ["host", "port", "database", "role", "server_addresses", "server_port"];

/** The real filesystem provider. Tests inject a fake with the same four methods. */
const realFs = {
  lstat(p) {
    try {
      return statInfo(fs.lstatSync(p));
    } catch (error) {
      if (error && (error.code === "ENOENT" || error.code === "ENOTDIR")) return null;
      throw new FileReadError("unreadable");
    }
  },
  accessWritable(p) {
    try {
      fs.accessSync(p, fs.constants.W_OK);
      return true;
    } catch {
      return false;
    }
  },
  realpath(p) {
    return fs.realpathSync(p);
  },
  readNoFollow(p, maxBytes) {
    return readNoFollow(p, maxBytes);
  },
  readInRoot(root, name, maxBytes) {
    return readInRoot(root, name, maxBytes);
  },
};

function policyPath(platform = process.platform) {
  if (!hasOwn(POLICY_PATHS, platform)) throw new RuntimeConfigError("policy_unsupported_platform");
  return POLICY_PATHS[platform];
}

function checkOwnerAndMode(info, writable) {
  if (info.uid !== 0) return "policy_not_root_owned";
  if (info.mode & 0o022) return "policy_writable_mode";
  if (writable) return "policy_writable_acl";
  return null;
}

function policyMetadataFailure(p, provider) {
  if (!path.posix.isAbsolute(p) || p.split("/").includes("..")) return "policy_symlink";
  const chain = [];
  let current = path.posix.dirname(p);
  for (;;) {
    chain.unshift(current);
    if (current === "/") break;
    current = path.posix.dirname(current);
  }
  chain.push(p);
  for (let index = 0; index < chain.length; index += 1) {
    const component = chain[index];
    const info = provider.lstat(component);
    if (info === null) return "policy_missing";
    if (info.kind === "symlink") return "policy_symlink";
    const expected = index === chain.length - 1 ? "file" : "dir";
    if (info.kind !== expected) return expected === "file" ? "policy_not_regular" : "policy_not_directory";
    const code = checkOwnerAndMode(info, provider.accessWritable(component));
    if (code !== null) return code;
  }
  if (provider.realpath(p) !== p) return "policy_symlink";
  return null;
}

/** Load and validate the root-owned policy (design §4.2). Throws RuntimeConfigError. */
function loadPolicy(p = null, provider = null, { platform = undefined } = {}) {
  const policyFile = p === null ? policyPath(platform) : p;
  const fsProvider = provider === null ? realFs : provider;
  let code = null;
  try {
    code = policyMetadataFailure(policyFile, fsProvider);
  } catch {
    code = "policy_unreadable";
  }
  if (code !== null) throw new RuntimeConfigError(code);

  let reason = null;
  let bytes;
  let info;
  try {
    [bytes, info] = fsProvider.readNoFollow(policyFile, POLICY_MAX_BYTES);
  } catch (error) {
    reason = error instanceof FileReadError ? error.reason : "unreadable";
  }
  if (reason !== null) throw new RuntimeConfigError(`policy_${reason}`);
  code = checkOwnerAndMode(info, false);
  if (code !== null) throw new RuntimeConfigError(code);
  return parsePolicy(bytes);
}

function containsPasswordKey(value) {
  if (Array.isArray(value)) return value.some(containsPasswordKey);
  if (isObject(value)) {
    return Object.keys(value).some((k) => k.toLowerCase() === "password" || containsPasswordKey(value[k]));
  }
  return false;
}

function exactKeys(doc, keys) {
  for (const key of keys) if (!hasOwn(doc, key)) throw new RuntimeConfigError("policy_missing_key", { key });
  for (const key of Object.keys(doc).sort(compareCodePoints)) {
    if (!keys.includes(key)) throw new RuntimeConfigError("policy_unknown_key", { key });
  }
}

function parsePolicy(bytes) {
  const [ok, doc] = tryParseJson(bytes);
  if (!ok || !isObject(doc)) throw new RuntimeConfigError("policy_malformed");
  if (containsPasswordKey(doc)) throw new RuntimeConfigError("policy_password_key");
  exactKeys(doc, POLICY_TOP_KEYS);
  if (!(isInt(doc.schema) && doc.schema === 1)) throw new RuntimeConfigError("policy_invalid_value", { key: "schema" });
  const target = doc.development_target;
  if (!isObject(target)) throw new RuntimeConfigError("policy_invalid_value", { key: "development_target" });
  exactKeys(target, POLICY_TARGET_KEYS);
  for (const key of ["host", "database", "role"]) {
    if (!isStr(target[key])) throw new RuntimeConfigError("policy_invalid_value", { key });
  }
  for (const key of ["port", "server_port"]) {
    if (!(isInt(target[key]) && target[key] >= 1 && target[key] <= 65535)) {
      throw new RuntimeConfigError("policy_invalid_value", { key });
    }
  }
  let addresses = target.server_addresses;
  if (!Array.isArray(addresses) || addresses.length < 1 || addresses.length > 16) {
    throw new RuntimeConfigError("policy_invalid_value", { key: "server_addresses" });
  }
  addresses = addresses.map(validateServerAddress);
  if (new Set(addresses).size !== addresses.length) {
    throw new RuntimeConfigError("policy_invalid_value", { key: "server_addresses" });
  }
  validateHost(target.host, "host");
  validateIdentifier(target.database, "database", { database: true });
  validateIdentifier(target.role, "role", { database: false });
  return Object.freeze({
    host: target.host,
    port: target.port,
    database: target.database,
    role: target.role,
    serverAddresses: Object.freeze([...addresses]),
    serverPort: target.server_port,
  });
}

// -------------------------------------------------------------- resolution

class DevelopmentTarget {
  #password;

  constructor({ host, port, database, user, password, sslmode, connectTimeout, applicationName, explicitOptions }) {
    this.host = host;
    this.port = port;
    this.database = database;
    this.user = user;
    this.#password = password;
    this.sslmode = sslmode;
    this.connectTimeout = connectTimeout;
    this.applicationName = applicationName;
    this.explicitOptions = Object.freeze([...explicitOptions]);
    Object.freeze(this);
  }

  get password() {
    return this.#password;
  }

  /** pg Pool/Client fields per the design §4.1 mapping table; nothing falls back to process.env. */
  pgConfig() {
    return {
      host: this.host,
      port: this.port,
      database: this.database,
      user: this.user,
      password: this.#password,
      ssl: this.sslmode === "require" ? { rejectUnauthorized: false } : false,
      connectionTimeoutMillis: this.connectTimeout * 1000,
      application_name: this.applicationName,
    };
  }

  urlQuery() {
    const query = { sslmode: this.sslmode, connect_timeout: String(this.connectTimeout) };
    if (this.explicitOptions.includes("PGAPPNAME")) query.application_name = this.applicationName;
    return query;
  }

  toJSON() {
    return {
      host: this.host, port: this.port, database: this.database, user: this.user, password: "***",
      sslmode: this.sslmode, connectTimeout: this.connectTimeout, applicationName: this.applicationName,
    };
  }

  toString() {
    return `DevelopmentTarget(${JSON.stringify(this.toJSON())})`;
  }

  [util.inspect.custom]() {
    return this.toString();
  }
}

function pct(value) {
  return encodeURIComponent(value).replace(/[!'()*]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`);
}

/** Canonical exported URL, byte-identical to the Python composition. */
function composeDatabaseUrl(target) {
  const host = target.host.includes(":") ? `[${target.host}]` : target.host;
  const query = Object.entries(target.urlQuery()).map(([k, v]) => `${k}=${pct(v)}`).join("&");
  return `postgresql+psycopg2://${pct(target.user)}:${pct(target.password)}@${host}:${target.port}/${pct(target.database)}?${query}`;
}

const URL_SCHEMES = ["postgresql+psycopg2", "postgresql"];
const URL_QUERY_KEYS = ["sslmode", "connect_timeout", "application_name"];
const URL_CHARS_RE = /^[\x21-\x7e]*$/;
const PCT_TEXT_RE = /^(?:[A-Za-z0-9._~-]|%[0-9A-Fa-f]{2})*$/;

/** Strict percent-decoding: unreserved characters and %XX only, UTF-8 result. */
function pctDecode(text) {
  if (!PCT_TEXT_RE.test(text)) return null;
  const bytes = [];
  for (let i = 0; i < text.length;) {
    if (text[i] === "%") {
      bytes.push(parseInt(text.slice(i + 1, i + 3), 16));
      i += 3;
    } else {
      bytes.push(text.charCodeAt(i));
      i += 1;
    }
  }
  try {
    return decodeUtf8Strict(Buffer.from(bytes));
  } catch {
    return null;
  }
}

const countOf = (text, ch) => text.split(ch).length - 1;

function partition(text, sep) {
  const i = text.indexOf(sep);
  return i === -1 ? [text, "", ""] : [text.slice(0, i), sep, text.slice(i + sep.length)];
}

/** Strictly parse an inherited or CLI database URL; null if not accepted. Mirrors Python. */
function parseDatabaseUrl(url) {
  if (typeof url !== "string" || !URL_CHARS_RE.test(url) || url.includes("#")) return null;
  const [scheme, sep, rest] = partition(url, "://");
  if (!sep || !URL_SCHEMES.includes(scheme)) return null;
  const [main, qsep, query] = partition(rest, "?");
  if (qsep && !query) return null;
  const [authority, slash, database] = partition(main, "/");
  if (!slash || database.includes("/") || countOf(authority, "@") !== 1) return null;
  const [userinfo, hostport] = authority.split("@");
  if (countOf(userinfo, ":") !== 1) return null;
  const [userText, passwordText] = userinfo.split(":");
  const user = pctDecode(userText);
  const password = pctDecode(passwordText);
  if (user === null || password === null) return null;
  let host;
  let portText;
  if (hostport.startsWith("[")) {
    const close = hostport.indexOf("]");
    if (close === -1 || !hostport.slice(1, close).includes(":") || !hostport.slice(close + 1).startsWith(":")) return null;
    host = hostport.slice(1, close);
    portText = hostport.slice(close + 2);
  } else {
    if (countOf(hostport, ":") !== 1) return null;
    [host, portText] = hostport.split(":");
  }
  if (!PORT_RE.test(portText) || Number(portText) > 65535) return null;
  const params = {};
  if (qsep) {
    for (const item of query.split("&")) {
      if (countOf(item, "=") !== 1) return null;
      const [key, valueText] = item.split("=");
      const value = pctDecode(valueText);
      if (!URL_QUERY_KEYS.includes(key) || hasOwn(params, key) || value === null) return null;
      params[key] = value;
    }
  }
  return { scheme, user, password, host, port: Number(portText), database, query: params };
}

/** Component equality between a supplied URL and the resolved target (design §4.4). */
function databaseUrlMatches(url, target) {
  const parsed = parseDatabaseUrl(url);
  if (parsed === null) return false;
  const { query } = parsed;
  if (parsed.user !== target.user || parsed.password !== target.password || parsed.host !== target.host
    || parsed.port !== target.port || parsed.database !== target.database) return false;
  if (query.sslmode !== target.sslmode || query.connect_timeout !== String(target.connectTimeout)) return false;
  if (hasOwn(query, "application_name") && query.application_name !== target.applicationName) return false;
  return true;
}

function defaultApplicationName(purpose) {
  if (!PURPOSE_RE.test(purpose)) throw new RuntimeConfigError("invalid_purpose");
  return `bizqlab-dev-${purpose}`;
}

function optionValues(db, purpose) {
  const sslmode = db.PGSSLMODE;
  if (!SSLMODES.includes(sslmode)) throw new RuntimeConfigError("invalid_value", { key: "PGSSLMODE" });
  let timeout = DEFAULT_CONNECT_TIMEOUT;
  if (hasOwn(db, "PGCONNECT_TIMEOUT")) {
    const text = db.PGCONNECT_TIMEOUT;
    if (!TIMEOUT_RE.test(text) || Number(text) < 1 || Number(text) > 60) {
      throw new RuntimeConfigError("invalid_value", { key: "PGCONNECT_TIMEOUT" });
    }
    timeout = Number(text);
  }
  let appname = defaultApplicationName(purpose);
  if (hasOwn(db, "PGAPPNAME")) {
    appname = db.PGAPPNAME;
    if (!IDENT_RE.test(appname)) throw new RuntimeConfigError("invalid_value", { key: "PGAPPNAME" });
  }
  return [sslmode, timeout, appname];
}

function effectiveOptionText(target, key) {
  return {
    PGHOST: target.host, PGPORT: String(target.port), PGDATABASE: target.database,
    PGUSER: target.user, PGPASSWORD: target.password, PGSSLMODE: target.sslmode,
    PGCONNECT_TIMEOUT: String(target.connectTimeout), PGAPPNAME: target.applicationName,
  }[key];
}

class DevelopmentResolution {
  #databaseUrl;

  constructor({ target, databaseUrl, nondb, policy = null }) {
    this.target = target;
    this.#databaseUrl = databaseUrl;
    this.nondb = Object.freeze({ ...nondb });
    this.policy = policy; // the approved identity, for connection verification
    Object.freeze(this);
  }

  get databaseUrl() {
    return this.#databaseUrl;
  }

  toJSON() {
    return { target: this.target.toJSON(), nondbKeys: Object.keys(this.nondb).sort() };
  }

  toString() {
    return `DevelopmentResolution(${JSON.stringify(this.toJSON())})`;
  }

  [util.inspect.custom]() {
    return this.toString();
  }
}

/**
 * Combine profile, policy, inherited environment and CLI flags into one identity.
 * Pure: no I/O and no environment mutation. Throws RuntimeConfigError naming only the key.
 */
function resolveDevelopmentTarget(profile, policy, { inheritedEnv, purpose, cli = null }) {
  const [db, nondb] = splitProfile(profile);
  const host = validateHost(db.PGHOST);
  const port = validatePortText(db.PGPORT);
  const database = validateIdentifier(db.PGDATABASE, "PGDATABASE", { database: true });
  const user = validateIdentifier(db.PGUSER, "PGUSER", { database: false });
  const password = validatePassword(db.PGPASSWORD);
  const [sslmode, connectTimeout, applicationName] = optionValues(db, purpose);

  for (const [key, profileValue, policyValue] of [
    ["PGHOST", host, policy.host], ["PGPORT", port, policy.port],
    ["PGDATABASE", database, policy.database], ["PGUSER", user, policy.role],
  ]) {
    if (profileValue !== policyValue) throw new RuntimeConfigError("policy_mismatch", { key });
  }

  const target = new DevelopmentTarget({
    host, port, database, user, password, sslmode, connectTimeout, applicationName,
    explicitOptions: OPTIONAL_DB_KEYS.filter((k) => hasOwn(db, k)),
  });
  const url = composeDatabaseUrl(target);

  for (const key of Object.keys(inheritedEnv).sort(compareCodePoints)) {
    if (key === DATABASE_URL_KEY) {
      if (!databaseUrlMatches(inheritedEnv[key], target)) throw new RuntimeConfigError("inherited_conflict", { key });
    } else if (key.startsWith("PG")) {
      if (!REQUIRED_DB_KEYS.includes(key) && !OPTIONAL_DB_KEYS.includes(key)) {
        throw new RuntimeConfigError("inherited_pg_key", { key });
      }
      if (inheritedEnv[key] !== effectiveOptionText(target, key)) {
        throw new RuntimeConfigError("inherited_conflict", { key });
      }
    }
  }

  for (const [flag, value] of Object.entries(cli || {})) {
    if (!hasOwn(CLI_DB_FLAGS, flag)) throw new RuntimeConfigError("unknown_cli_flag", { key: flag });
    if (value === null || value === undefined) continue;
    const mapped = CLI_DB_FLAGS[flag];
    const equal = mapped === DATABASE_URL_KEY
      ? typeof value === "string" && databaseUrlMatches(value, target)
      : typeof value !== "boolean" && String(value) === effectiveOptionText(target, mapped);
    if (!equal) {
      throw new RuntimeConfigError("cli_conflict", { key: flag });
    }
  }

  return new DevelopmentResolution({ target, databaseUrl: url, nondb, policy });
}

// ---------------------------------------------------------------- combined

function present(provider, p) {
  try {
    return provider.lstat(p) !== null;
  } catch {
    return true;
  }
}

/**
 * Classify the runtime and, in development, resolve the approved identity.
 * Reads files only; never connects and never mutates env. In production the
 * development resolution stays null: production parameters are unchanged.
 */
function resolveRuntime(env, {
  purpose,
  cli = null,
  profilePath = PROFILE_PATH,
  repoRootSentinel = REPO_ROOT_SENTINEL,
  policyFile = undefined,
  buildRootDir = BUILD_ROOT_DIR,
  provider = null,
  platform = undefined,
} = {}) {
  const fsProvider = provider === null ? realFs : provider;
  let file = policyFile;
  if (file === undefined) {
    try {
      file = policyPath(platform);
    } catch {
      file = null;
    }
  }
  const policyPresent = file !== null && present(fsProvider, file);
  const profilePresent = present(fsProvider, profilePath);
  const mode = decideMode(
    env,
    () => readAttestation(buildRootDir, { buildRoot: BUILD_ROOT, env, reader: fsProvider.readInRoot }),
    { policyPresent, profilePresent },
  );
  if (mode === "production") return Object.freeze({ mode, development: null });
  if (file === null) throw new RuntimeConfigError("policy_unsupported_platform");
  if (!present(fsProvider, repoRootSentinel)) throw new RuntimeConfigError("repo_root_unconfirmed");
  const profile = readProfile(profilePath, fsProvider.readNoFollow);
  const policy = loadPolicy(file, fsProvider);
  const development = resolveDevelopmentTarget(profile, policy, { inheritedEnv: env, purpose, cli });
  return Object.freeze({ mode, development });
}

module.exports = {
  ATTESTATION_KEYS,
  ATTESTATION_MAX_BYTES,
  ATTESTATION_FILENAME,
  BUILD_ROOT,
  BUILD_ROOT_DIR,
  CLI_DB_FLAGS,
  DevelopmentResolution,
  DevelopmentTarget,
  FileReadError,
  JsonFloat,
  MARKER_KEYS,
  NONDB_ALLOWLIST,
  POLICY_MAX_BYTES,
  POLICY_PATHS,
  PROFILE_LINE_MAX_BYTES,
  PROFILE_MAX_BYTES,
  PROFILE_PATH,
  REPO_ROOT,
  RuntimeConfigError,
  classifyAttestationBytes,
  classifyIpLiteral,
  classifyKey,
  classifyMarkers,
  composeDatabaseUrl,
  databaseUrlMatches,
  decideMode,
  decideModeRow,
  defaultApplicationName,
  formatError,
  formatIpv6,
  loadPolicy,
  parseDatabaseUrl,
  parseIpv4,
  parseIpv6,
  parsePolicy,
  parseProfile,
  parseStrictJson,
  pathExistsNoFollow,
  policyPath,
  readAttestation,
  readNoFollow,
  readInRoot,
  readProfile,
  realFs,
  resolveDevelopmentTarget,
  resolveRuntime,
  splitProfile,
  validateHost,
  validateIdentifier,
  validatePassword,
  validatePortText,
  workstationIndicators,
};
