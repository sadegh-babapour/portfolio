"use strict";
/**
 * Runtime authorization state, identity verification and revocation for the
 * transit API (M1 design §6–§8), mirroring app/runtime_state.py and the identity
 * part of app/runtime_db.py.
 *
 * verifyRuntime() resolves the runtime once (config/runtimeEnv.js) and commits an
 * immutable state. In development, assertUsable() re-checks the environment
 * snapshot and the security metadata of the profile, the policy and its ancestor
 * directories at every guarded boundary; any failure revokes, and revocation is
 * terminal. Production has no per-statement checks (design §8.5).
 *
 * createDevelopmentPool() builds a pg Pool whose every new client runs the
 * identity query before any application SQL (pg-pool `onConnect`), and whose
 * pool.query, pool.connect and per-client query check the state first. Releasing
 * and ending are always allowed. Errors are new objects with no `cause`.
 */
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const rt = require("./runtimeEnv");

const ACTIVE = "active";
const REVOKED = "revoked";
const IDENTITY_SQL = "SELECT current_database(), current_user, host(inet_server_addr()), inet_server_port()";
// DB settings plus the mode inputs: any change after commit revokes (design §8.1).
const SNAPSHOT_KEYS = ["DATABASE_URL", "BIZQLAB_RUNTIME", ...rt.MARKER_KEYS, "RAILWAY_GIT_COMMIT_SHA"];
// Ancestor directories keep identity, type, owner, group and mode only (plus the
// access check). Their size and times change whenever an unrelated sibling is
// created, so they are not part of the fingerprint. Files keep every field.
const ANCESTOR_FIELDS = 5; // dev, ino, mode (with type bits), uid, gid
const SQLSTATE_RE = /^[0-9A-Z]{5}$/;

class RuntimeNotBootstrappedError extends rt.RuntimeConfigError {
  constructor() {
    super("runtime_not_bootstrapped");
    this.name = "RuntimeNotBootstrappedError";
  }
}

/** Raised at every boundary once the state is revoked. `trigger` says why; never a value. */
class RuntimeRevokedError extends rt.RuntimeConfigError {
  constructor(trigger, { key = null } = {}) {
    super("runtime_revoked", { key });
    this.name = "RuntimeRevokedError";
    this.trigger = trigger;
    this.message = `runtime_revoked [trigger=${trigger}]${key === null ? "" : ` [key=${key}]`}`;
  }
}

/** A sanitized connect or identity failure: code and SQLSTATE only. */
class RuntimeConnectError extends rt.RuntimeConfigError {
  constructor(code, { sqlstate = null } = {}) {
    super(code);
    this.name = "RuntimeConnectError";
    this.sqlstate = sqlstate;
    if (sqlstate !== null) this.message = `${code} [sqlstate=${sqlstate}]`;
  }
}

// ------------------------------------------------------------------ inputs

/** Security metadata of a path without following a final symlink; mode includes the type bits. */
const realMetadata = {
  statKey(p) {
    let st;
    try {
      st = fs.lstatSync(p, { bigint: true });
    } catch (error) {
      if (error && (error.code === "ENOENT" || error.code === "ENOTDIR")) return null;
      throw error;
    }
    return [st.dev, st.ino, st.mode, st.uid, st.gid, st.size, st.mtimeNs, st.ctimeNs].map(String);
  },
  accessWritable(p) {
    try {
      fs.accessSync(p, fs.constants.W_OK);
      return true;
    } catch {
      return false;
    }
  },
};

/** Everything verifyRuntime reads. The real process by default; tests inject fakes. */
function realInputs() {
  return {
    env: process.env,
    profilePath: rt.PROFILE_PATH,
    policyFile: undefined, // the fixed path for the platform
    buildRootDir: rt.BUILD_ROOT_DIR,
    repoRootSentinel: undefined,
    provider: null, // runtimeEnv provider (realFs by default)
    meta: null, // metadata provider (realMetadata by default)
    platform: undefined,
  };
}

const DEFAULTS = { inputs: realInputs };

function policyFileOf(inputs) {
  if (inputs.policyFile !== undefined) return inputs.policyFile;
  try {
    return rt.policyPath(inputs.platform);
  } catch {
    return null;
  }
}

// ------------------------------------------------------------- fingerprint

const digest = (value) => crypto.createHash("sha256").update(value).digest("hex");

function envSnapshot(env) {
  return Object.keys(env)
    .filter((key) => SNAPSHOT_KEYS.includes(key) || key.startsWith("PG"))
    .sort()
    .map((key) => [key, digest(String(env[key]))]);
}

/** [path, isAncestorDirectory]: the profile, each policy ancestor, then the policy file. */
function trackedEntries(inputs) {
  const entries = [[String(inputs.profilePath), false]];
  const policy = policyFileOf(inputs);
  if (policy !== null) {
    const ancestors = [];
    let current = path.posix.dirname(policy);
    for (;;) {
      ancestors.unshift([current, true]);
      if (current === "/") break;
      current = path.posix.dirname(current);
    }
    entries.push(...ancestors, [policy, false]);
  }
  return entries;
}

function fileMetadata(inputs) {
  const meta = inputs.meta || realMetadata;
  return trackedEntries(inputs).map(([p, ancestor]) => {
    let key = meta.statKey(p);
    if (key !== null && ancestor) key = key.slice(0, ANCESTOR_FIELDS);
    return [p, key, key !== null && meta.accessWritable(p)];
  });
}

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function firstDifference(a, b) {
  const da = new Map(a);
  const db = new Map(b);
  for (const key of [...new Set([...da.keys(), ...db.keys()])].sort()) {
    if (da.get(key) !== db.get(key)) return key;
  }
  return null;
}

/** Wraps the resolver provider and keeps the bytes it read, for content digests. */
function capturing(provider) {
  const read = new Map();
  return {
    read,
    provider: {
      lstat: (p) => provider.lstat(p),
      accessWritable: (p) => provider.accessWritable(p),
      realpath: (p) => provider.realpath(p),
      readNoFollow(p, maxBytes) {
        const result = provider.readNoFollow(p, maxBytes);
        read.set(String(p), result[0]);
        return result;
      },
      readInRoot: (root, name, maxBytes) => provider.readInRoot(root, name, maxBytes),
    },
  };
}

function targetKey(resolution) {
  const dev = resolution.development;
  if (dev === null) return null;
  const t = dev.target;
  const p = dev.policy;
  return [t.host, t.port, t.database, t.user, digest(t.password), t.sslmode, t.connectTimeout,
    t.applicationName, t.explicitOptions, p === null ? null : [p.serverAddresses, p.serverPort],
    Object.keys(dev.nondb).sort()];
}

// ------------------------------------------------------------ module state

let STATE = null;
const REVOKE_HOOKS = [];

function currentState() {
  return STATE;
}

/** Called with the trigger after revocation; used to end the pool and exit (design §8.4). */
function onRevoke(hook) {
  REVOKE_HOOKS.push(hook);
}

function evaluate(purpose, cli, inputs) {
  const envView = { ...inputs.env };
  const before = fileMetadata(inputs);
  const capture = capturing(inputs.provider || rt.realFs);
  const options = {
    purpose, cli, profilePath: inputs.profilePath, buildRootDir: inputs.buildRootDir,
    provider: capture.provider, platform: inputs.platform, policyFile: policyFileOf(inputs),
  };
  if (inputs.repoRootSentinel !== undefined) options.repoRootSentinel = inputs.repoRootSentinel;
  const resolution = rt.resolveRuntime(envView, options);
  const after = fileMetadata(inputs);
  if (!same(before, after)) throw new rt.RuntimeConfigError("configuration_changed_during_bootstrap");
  const development = resolution.mode === "development";
  // Allowlisted non-DB profile keys apply only where unset, after the decisions (design §4.1).
  const exports = {};
  if (development) {
    for (const [key, value] of Object.entries(resolution.development.nondb)) {
      if (!Object.prototype.hasOwnProperty.call(envView, key)) exports[key] = value;
    }
  }
  const fingerprint = {
    mode: resolution.mode,
    purpose,
    target: targetKey(resolution),
    env: envSnapshot({ ...envView, ...exports }),
    files: development ? after : [],
    digests: development ? [...capture.read.entries()].sort().map(([p, bytes]) => [p, digest(bytes)]) : [],
  };
  return { resolution, fingerprint, exports };
}

/**
 * Resolve and commit the runtime state (design §8.1, §8.4).
 * - First call: validate, then commit. A failure commits nothing and leaves env unchanged.
 * - Later call with fingerprint-identical inputs: no-op, returns the same state.
 * - Later call with different or invalid inputs: revokes, then throws.
 * - After revocation: always throws RuntimeRevokedError.
 */
function verifyRuntime(purpose, { cli = null, inputs = DEFAULTS.inputs() } = {}) {
  const current = STATE;
  if (current !== null && current.status === REVOKED) throw new RuntimeRevokedError(current.trigger || "revoked");
  let candidate = null;
  let failure = null;
  try {
    candidate = evaluate(purpose, cli, inputs);
  } catch (error) {
    if (!(error instanceof rt.RuntimeConfigError)) throw error;
    failure = error;
  }
  if (failure !== null) {
    if (current !== null) revokeState("rebootstrap_invalid");
    throw failure;
  }
  if (current !== null) {
    if (same(candidate.fingerprint, current.fingerprint) && inputs.env === current.inputs.env) return current;
    revokeState("rebootstrap_conflict");
    throw new RuntimeRevokedError("rebootstrap_conflict");
  }
  Object.assign(inputs.env, candidate.exports);
  STATE = Object.freeze({
    mode: candidate.resolution.mode,
    status: ACTIVE,
    development: candidate.resolution.development,
    fingerprint: candidate.fingerprint,
    inputs,
    trigger: null,
  });
  return STATE;
}

/** Check the committed state at a boundary (design §8.2). Revokes on any failure. */
function assertUsable() {
  const state = STATE;
  if (state === null) throw new RuntimeNotBootstrappedError();
  if (state.status !== ACTIVE) throw new RuntimeRevokedError(state.trigger || "revoked");
  if (state.mode === "production") return state;
  const env = envSnapshot(state.inputs.env);
  if (!same(env, state.fingerprint.env)) revoke("env_drift", { key: firstDifference(env, state.fingerprint.env) });
  let files = null;
  try {
    files = fileMetadata(state.inputs);
  } catch {
    files = null;
  }
  if (!same(files, state.fingerprint.files)) revoke("metadata_changed");
  return state;
}

/** Revoke the active state (terminal) and throw RuntimeRevokedError. */
function revoke(trigger, { key = null } = {}) {
  revokeState(trigger);
  throw new RuntimeRevokedError(trigger, { key });
}

function revokeState(trigger) {
  const state = STATE;
  if (state === null || state.status === REVOKED) return;
  STATE = Object.freeze({ ...state, status: REVOKED, trigger });
  for (const hook of [...REVOKE_HOOKS]) {
    try {
      hook(trigger);
    } catch {
      // revocation must never be blocked by cleanup
    }
  }
}

function resetForTests() {
  STATE = null;
  REVOKE_HOOKS.length = 0;
}

// ---------------------------------------------------------------- identity

function normalizeAddress(text) {
  if (typeof text !== "string") return null;
  if (text.includes(":")) {
    const hextets = rt.parseIpv6(text.toLowerCase());
    return hextets === null ? null : rt.formatIpv6(hextets);
  }
  const octets = rt.parseIpv4(text);
  return octets === null ? null : octets.join(".");
}

function identityMatches(row, policy) {
  if (!Array.isArray(row) || row.length !== 4) return false;
  const [database, role, address, port] = row;
  return database === policy.database
    && role === policy.role
    && policy.serverAddresses.includes(normalizeAddress(address))
    && Number.isInteger(port) && port === policy.serverPort;
}

function sqlstateOf(error) {
  const code = error && error.code;
  return typeof code === "string" && SQLSTATE_RE.test(code) ? code : null;
}

/**
 * Run the identity query as the first statement on a new client (design §6). On any
 * failure the state is revoked and a sanitized error is thrown; pg-pool then removes
 * and ends the client and fails the acquire (design L2).
 */
async function verifyClientIdentity(client, policy, query) {
  let code = null;
  let sqlstate = null;
  let row = null;
  try {
    const result = await query.call(client, { text: IDENTITY_SQL, rowMode: "array" });
    row = result && Array.isArray(result.rows) ? result.rows[0] : null;
  } catch (error) {
    code = "identity_query_failed";
    sqlstate = sqlstateOf(error);
  }
  if (code === null && !identityMatches(row, policy)) code = "identity_mismatch";
  if (code === null) return;
  revokeState(code);
  throw new RuntimeConnectError(code, { sqlstate });
}

// ------------------------------------------------------------------- pool

/** Check the state, then call; a refusal is delivered the way the caller expects (callback or promise). */
function guarded(args, call) {
  let failure = null;
  try {
    assertUsable();
  } catch (error) {
    failure = error;
  }
  if (failure === null) return call(args);
  const last = args[args.length - 1];
  if (typeof last === "function") {
    process.nextTick(last, failure);
    return undefined;
  }
  return Promise.reject(failure);
}

/**
 * A development pool over the explicit target (every pg field set; nothing falls back
 * to process.env). Identity runs in onConnect on every new client, so idle-timeout
 * replacements and reconnects are verified again. pool.query, pool.connect and each
 * client's query check the state first; release and end are always allowed.
 */
function createDevelopmentPool(state, PoolClass) {
  const dev = state.development;
  if (state.mode !== "development" || dev === null || dev.policy === null) {
    throw new rt.RuntimeConfigError("development_only");
  }
  class GuardedPool extends PoolClass {
    query(...args) {
      return guarded(args, (a) => super.query(...a));
    }

    connect(...args) {
      return guarded(args, (a) => super.connect(...a));
    }
  }
  const pool = new GuardedPool({
    ...dev.target.pgConfig(),
    onConnect: async (client) => {
      assertUsable();
      const query = client.query;
      await verifyClientIdentity(client, dev.policy, query);
      client.query = function guardedQuery(...args) {
        return guarded(args, (a) => query.apply(client, a));
      };
    },
  });
  // Async errors on idle clients: class and code only, never the message.
  pool.on("error", (error) => {
    console.error(`transit-api pool error: ${(error && error.name) || "Error"} ${(error && error.code) || ""}`.trim());
  });
  return pool;
}

module.exports = {
  ACTIVE,
  DEFAULTS,
  IDENTITY_SQL,
  REVOKED,
  RuntimeConnectError,
  RuntimeNotBootstrappedError,
  RuntimeRevokedError,
  assertUsable,
  createDevelopmentPool,
  currentState,
  envSnapshot,
  fileMetadata,
  identityMatches,
  normalizeAddress,
  onRevoke,
  realInputs,
  realMetadata,
  resetForTests,
  revoke,
  trackedEntries,
  verifyClientIdentity,
  verifyRuntime,
};
