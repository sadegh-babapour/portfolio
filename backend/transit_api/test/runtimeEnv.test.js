"use strict";
/**
 * Batch 1 tests for config/runtimeEnv.js: the same shared fixtures as
 * test/test_runtime_env.py, checked against the same literal expectations.
 * Synthetic values, temporary files and injected providers only; no database,
 * no network, no real profile or policy.
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const util = require("node:util");

const rt = require("../config/runtimeEnv");

const FIXTURES = path.resolve(__dirname, "..", "..", "..", "test", "fixtures");
const SYNTHETIC_PASSWORD = "synthetic-Pw_1";

function loadFixture(name) {
  return JSON.parse(fs.readFileSync(path.join(FIXTURES, name), "utf8"));
}

function buildBytes(segments) {
  return Buffer.concat(segments.map((seg) => {
    if (seg.text !== undefined) return Buffer.from(seg.text, "utf8");
    if (seg.hex !== undefined) return Buffer.from(seg.hex, "hex");
    return Buffer.from(seg.repeat.repeat(seg.count), "utf8");
  }));
}

const expand = (v) => (v !== null && typeof v === "object" && v.repeat !== undefined ? v.repeat.repeat(v.count) : v);

function outcomeOf(fn) {
  try {
    return ["ok", fn()];
  } catch (error) {
    if (error instanceof rt.RuntimeConfigError) return ["error", [error.code, error.key, error.line]];
    throw error;
  }
}

const expectedError = (e) => [e.error.code, e.error.key ?? null, e.error.line ?? null];

function withTempDir(fn) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "bizqlab-rt-"));
  try {
    return fn(fs.realpathSync(dir));
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

function mkfifo(p) {
  const { execFileSync } = require("node:child_process");
  execFileSync("mkfifo", [p]);
}

// ------------------------------------------------------------------- mode

test("mode fixture rows and named contexts", () => {
  const fixture = loadFixture("runtime_mode_cases.json");
  assert.deepEqual(new Set(fixture.cases.map((c) => c.row)), new Set([1, 2, 3, 4, 5, 6, 7]));
  for (const c of [...fixture.cases, ...fixture.named_contexts]) {
    const got = rt.decideModeRow(c.env, c.attestation, { policyPresent: c.policy_present, profilePresent: c.profile_present });
    assert.deepEqual(got, [c.row, c.outcome], c.name);
  }
});

test("exhaustive mode matrix matches the V4 wording", () => {
  const modes = [undefined, "production", "development", "Production", " production", "", "staging"];
  const markerVariants = [
    ["absent", {}],
    ["partial-one", { RAILWAY_SERVICE_ID: "svc" }],
    ["partial-two", { RAILWAY_PROJECT_ID: "p", RAILWAY_ENVIRONMENT_ID: "e" }],
    ["complete", { RAILWAY_PROJECT_ID: "p", RAILWAY_ENVIRONMENT_ID: "e", RAILWAY_SERVICE_ID: "s" }],
    ["one-empty", { RAILWAY_PROJECT_ID: "p", RAILWAY_ENVIRONMENT_ID: "", RAILWAY_SERVICE_ID: "s" }],
    ["all-empty", { RAILWAY_PROJECT_ID: "", RAILWAY_ENVIRONMENT_ID: "", RAILWAY_SERVICE_ID: "" }],
  ];
  let count = 0;
  for (const mode of modes) {
    for (const [markerName, markers] of markerVariants) {
      for (const attestation of ["valid", "absent", "invalid:service_mismatch"]) {
        for (const policy of [false, true]) {
          for (const profile of [false, true]) {
            const env = { ...markers };
            if (mode !== undefined) env.BIZQLAB_RUNTIME = mode;
            let expected = "error";
            if (markerName === "absent" && (mode === undefined || mode === "development")) expected = "development";
            else if (mode === "production" && markerName === "complete" && attestation === "valid" && !policy && !profile) {
              expected = "production";
            }
            const [, outcome] = rt.decideModeRow(env, attestation, { policyPresent: policy, profilePresent: profile });
            const got = outcome === "production" || outcome === "development" ? outcome : "error";
            assert.equal(got, expected, JSON.stringify({ env, attestation, policy, profile }));
            count += 1;
          }
        }
      }
    }
  }
  assert.equal(count, 504);
});

test("attestation is evaluated only for row four", () => {
  let calls = 0;
  const attestation = () => { calls += 1; return "valid"; };
  const markers = { RAILWAY_PROJECT_ID: "x", RAILWAY_ENVIRONMENT_ID: "x", RAILWAY_SERVICE_ID: "x" };
  rt.decideModeRow({}, attestation, { policyPresent: false, profilePresent: false });
  rt.decideModeRow(markers, attestation, { policyPresent: true, profilePresent: false });
  rt.decideModeRow({ BIZQLAB_RUNTIME: "production" }, attestation, { policyPresent: false, profilePresent: false });
  assert.equal(calls, 0);
  rt.decideModeRow({ BIZQLAB_RUNTIME: "production", ...markers }, attestation, { policyPresent: false, profilePresent: false });
  assert.equal(calls, 1);
});

test("decideMode throws code-only errors with no cause", () => {
  assert.throws(
    () => rt.decideMode({ BIZQLAB_RUNTIME: "Production" }, "valid", { policyPresent: false, profilePresent: false }),
    (error) => error instanceof rt.RuntimeConfigError && error.message === "invalid_mode" && !("cause" in error),
  );
});

// ------------------------------------------------------------ attestation

function attestationContent(c, baseDoc) {
  if (c.content) return buildBytes(c.content);
  const doc = { ...baseDoc, ...c.doc.set };
  for (const key of c.doc.delete) delete doc[key];
  return Buffer.from(JSON.stringify(doc), "utf8");
}

/** Lay out the case under <tmp>/build (the build root); return the root. */
function materializeAttestation(tmp, c, baseDoc) {
  const root = path.join(tmp, "build");
  const target = path.join(root, rt.ATTESTATION_FILENAME);
  const content = attestationContent(c, baseDoc);
  if (c.file === "root_absent") return root;
  if (c.file === "root_file") {
    fs.writeFileSync(root, content);
    return root;
  }
  fs.mkdirSync(root);
  if (c.file === "absent") return root;
  if (c.file === "legacy_regular") {
    fs.mkdirSync(path.join(root, ".bizqlab"));
    fs.writeFileSync(path.join(root, ".bizqlab", "build-attestation.json"), content);
  } else if (c.file === "legacy_parent_symlink_outside") {
    const outside = path.join(tmp, "outside");
    fs.mkdirSync(outside);
    fs.writeFileSync(path.join(outside, "build-attestation.json"), content);
    fs.symlinkSync(outside, path.join(root, ".bizqlab"));
  } else if (c.file === "regular") fs.writeFileSync(target, content);
  else if (c.file === "symlink") {
    const real = path.join(root, "real.json");
    fs.writeFileSync(real, content);
    fs.symlinkSync(real, target);
  } else if (c.file === "symlink_outside") {
    const outside = path.join(tmp, "outside.json");
    fs.writeFileSync(outside, content);
    fs.symlinkSync(outside, target);
  } else if (c.file === "dangling_symlink") fs.symlinkSync(path.join(tmp, "nowhere.json"), target);
  else if (c.file === "directory") fs.mkdirSync(target);
  else if (c.file === "fifo") mkfifo(target);
  else throw new Error(c.file);
  return root;
}

test("attestation fixture cases through real files", () => {
  const fixture = loadFixture("attestation_cases.json");
  for (const c of fixture.cases) {
    withTempDir((dir) => {
      const root = materializeAttestation(dir, c, fixture.base_doc);
      assert.equal(rt.readAttestation(root, { buildRoot: c.build_root, env: c.env }), c.expected, c.name);
    });
  }
});

test("B1 regression: Sol's two-window .bizqlab interleaving cannot supply the marker", () => {
  // Sol's retest interleaving (SOL_M1_GATE_B_BATCH1_RETEST): swap the retired .bizqlab
  // directory to an outside symlink for the open, restore it, then swap it again after
  // the next lstat. The old reader returned "valid" for the outside document. The direct
  // root reader never looks at .bizqlab, so the outcome depends only on the root's own marker.
  const base = loadFixture("attestation_cases.json").base_doc;
  const env = { RAILWAY_PROJECT_ID: "proj-1", RAILWAY_ENVIRONMENT_ID: "env-1", RAILWAY_SERVICE_ID: "svc-1" };
  for (const [marker, expected] of [[null, "absent"], [{ ...base, build_root: rt.BUILD_ROOT, railway_service_id: "wrong-service" }, "invalid:service_mismatch"]]) {
    withTempDir((dir) => {
      const root = path.join(dir, "build");
      const outside = path.join(dir, "outside");
      const parent = path.join(root, ".bizqlab");
      const moved = `${parent}.moved`;
      fs.mkdirSync(parent, { recursive: true });
      fs.mkdirSync(outside);
      fs.writeFileSync(path.join(parent, "build-attestation.json"), JSON.stringify({ ...base, build_root: rt.BUILD_ROOT, railway_service_id: "wrong-service" }));
      fs.writeFileSync(path.join(outside, "build-attestation.json"), JSON.stringify({ ...base, build_root: rt.BUILD_ROOT }));
      if (marker !== null) fs.writeFileSync(path.join(root, rt.ATTESTATION_FILENAME), JSON.stringify(marker));
      let opened = false;
      let postChecked = false;
      const swapOut = () => { fs.renameSync(parent, moved); fs.symlinkSync(outside, parent); };
      const restore = () => { fs.unlinkSync(parent); fs.renameSync(moved, parent); };
      const impl = {
        ...fs,
        openSync(p, flags) { swapOut(); const fd = fs.openSync(p, flags); restore(); opened = true; return fd; },
        lstatSync(p) { const st = fs.lstatSync(p); if (opened && !postChecked) { postChecked = true; swapOut(); } return st; },
        statSync(p) { const st = fs.statSync(p); if (opened && !postChecked) { postChecked = true; swapOut(); } return st; },
      };
      const reader = (r, name, max) => rt.readInRoot(r, name, max, impl);
      assert.equal(rt.readAttestation(root, { env, reader }), expected);
      assert.ok(opened || marker === null);
    });
  }
});

test("marker swapped for an outside symlink before the open is refused", () => {
  const base = loadFixture("attestation_cases.json").base_doc;
  const env = { RAILWAY_PROJECT_ID: "proj-1", RAILWAY_ENVIRONMENT_ID: "env-1", RAILWAY_SERVICE_ID: "svc-1" };
  withTempDir((dir) => {
    const root = path.join(dir, "build");
    fs.mkdirSync(root);
    const target = path.join(root, rt.ATTESTATION_FILENAME);
    fs.writeFileSync(target, JSON.stringify({ ...base, build_root: rt.BUILD_ROOT, railway_service_id: "svc-2" }));
    fs.writeFileSync(path.join(dir, "outside.json"), JSON.stringify({ ...base, build_root: rt.BUILD_ROOT }));
    const before = { ...fs, openSync(p, flags) { fs.rmSync(target); fs.symlinkSync(path.join(dir, "outside.json"), target); return fs.openSync(p, flags); } };
    assert.equal(rt.readAttestation(root, { env, reader: (r, n, m) => rt.readInRoot(r, n, m, before) }), "invalid:symlink");
  });
});

test("marker swapped after the open is read from the opened descriptor", () => {
  const base = loadFixture("attestation_cases.json").base_doc;
  const env = { RAILWAY_PROJECT_ID: "proj-1", RAILWAY_ENVIRONMENT_ID: "env-1", RAILWAY_SERVICE_ID: "svc-1" };
  withTempDir((dir) => {
    const root = path.join(dir, "build");
    fs.mkdirSync(root);
    const target = path.join(root, rt.ATTESTATION_FILENAME);
    fs.writeFileSync(target, JSON.stringify({ ...base, build_root: rt.BUILD_ROOT, railway_service_id: "svc-2" }));
    fs.writeFileSync(path.join(dir, "outside.json"), JSON.stringify({ ...base, build_root: rt.BUILD_ROOT }));
    const after = { ...fs, openSync(p, flags) { const fd = fs.openSync(p, flags); fs.rmSync(target); fs.symlinkSync(path.join(dir, "outside.json"), target); return fd; } };
    assert.equal(rt.readAttestation(root, { env, reader: (r, n, m) => rt.readInRoot(r, n, m, after) }), "invalid:service_mismatch");
  });
});

test("the in-root reader takes a single path component", () => {
  for (const name of ["", ".", "..", ".bizqlab/build-attestation.json"]) {
    assert.throws(() => rt.readInRoot("/", name, 1024), /single path component/);
  }
});

test("node consumer constant is the transit-api build root", () => {
  assert.equal(rt.BUILD_ROOT, "backend/transit_api");
});

// ---------------------------------------------------------------- grammar

test("profile grammar fixture cases", () => {
  for (const c of loadFixture("profile_grammar_cases.json").cases) {
    const got = outcomeOf(() => rt.parseProfile(buildBytes(c.bytes)));
    if (c.expected.ok) assert.deepEqual(got, ["ok", c.expected.ok], c.name);
    else assert.deepEqual(got, ["error", expectedError(c.expected)], c.name);
  }
});

function exactSizeProfile(size) {
  const parts = [Buffer.from("A=1\n")];
  let length = 4;
  while (length < size) {
    const lineLen = Math.min(size - length, 2000);
    const line = lineLen >= 2 ? `#${"c".repeat(lineLen - 2)}\n` : "\n";
    parts.push(Buffer.from(line));
    length += line.length;
  }
  return Buffer.concat(parts);
}

function materializeProfile(dir, setup) {
  const p = path.join(dir, ".env.local");
  if (setup === "missing") return p;
  if (setup === "symlink") {
    fs.writeFileSync(path.join(dir, "real.env"), "A=1\n");
    fs.symlinkSync(path.join(dir, "real.env"), p);
  } else if (setup === "directory") fs.mkdirSync(p);
  else if (setup === "fifo") mkfifo(p);
  else if (setup === "empty") fs.writeFileSync(p, "");
  else if (setup === "oversized") fs.writeFileSync(p, exactSizeProfile(rt.PROFILE_MAX_BYTES + 1));
  else if (setup === "exact_limit") {
    fs.writeFileSync(p, exactSizeProfile(rt.PROFILE_MAX_BYTES));
    assert.equal(fs.statSync(p).size, rt.PROFILE_MAX_BYTES);
  } else if (setup === "unreadable") {
    fs.writeFileSync(p, "A=1\n");
    fs.chmodSync(p, 0);
  } else throw new Error(setup);
  return p;
}

test("profile file cases", () => {
  for (const c of loadFixture("profile_grammar_cases.json").file_cases) {
    if (c.setup === "unreadable" && process.getuid() === 0) continue;
    withTempDir((dir) => {
      const got = outcomeOf(() => rt.readProfile(materializeProfile(dir, c.setup)));
      if (c.expected === "ok") assert.equal(got[0], "ok", c.name);
      else assert.deepEqual(got, ["error", [c.expected, null, null]], c.name);
    });
  }
});

// ------------------------------------------------------------- validation

function validationInputs(fixture, c) {
  const profile = { ...fixture.base_profile };
  for (const [key, value] of Object.entries(c.profile)) {
    if (value === null) delete profile[key];
    else profile[key] = expand(value);
  }
  const t = { ...fixture.base_target, ...c.policy };
  const policy = {
    host: t.host, port: t.port, database: t.database, role: t.role,
    serverAddresses: t.server_addresses, serverPort: t.server_port,
  };
  return [profile, policy];
}

function resolutionView(res) {
  const t = res.target;
  return {
    params: {
      host: t.host, port: t.port, database: t.database, user: t.user,
      sslmode: t.sslmode, connect_timeout: t.connectTimeout, application_name: t.applicationName,
    },
    node_config: t.pgConfig(),
    database_url: res.databaseUrl,
    nondb_keys: Object.keys(res.nondb).sort(),
  };
}

test("validation fixture cases", () => {
  const fixture = loadFixture("validation_cases.json");
  for (const c of fixture.cases) {
    const [profile, policy] = validationInputs(fixture, c);
    const got = outcomeOf(() => rt.resolveDevelopmentTarget(profile, policy, {
      inheritedEnv: c.inherited_env, purpose: c.purpose, cli: c.cli,
    }));
    if (c.expected.ok) {
      assert.equal(got[0], "ok", `${c.name}: ${JSON.stringify(got[1])}`);
      const { python_kwargs: _ignored, ...expected } = c.expected.ok;
      assert.deepEqual(resolutionView(got[1]), expected, c.name);
    } else {
      assert.deepEqual(got, ["error", expectedError(c.expected)], c.name);
    }
  }
});

test("pg config never leaves a field for pg to fill from process.env", () => {
  const fixture = loadFixture("validation_cases.json");
  const [profile, policy] = validationInputs(fixture, { profile: {}, policy: {} });
  const config = rt.resolveDevelopmentTarget(profile, policy, { inheritedEnv: {}, purpose: "transit-api" }).target.pgConfig();
  for (const key of ["host", "port", "database", "user", "password", "connectionTimeoutMillis", "application_name"]) {
    assert.ok(config[key], key);
  }
  assert.ok(config.ssl === false || typeof config.ssl === "object");
});

test("resolution does not mutate inputs or process.env", () => {
  const fixture = loadFixture("validation_cases.json");
  const [profile, policy] = validationInputs(fixture, { profile: {}, policy: {} });
  const env = { PGHOST: "192.168.1.50" };
  const before = JSON.stringify([profile, env, process.env]);
  rt.resolveDevelopmentTarget(profile, policy, { inheritedEnv: env, purpose: "web" });
  assert.equal(JSON.stringify([profile, env, process.env]), before);
});

// ----------------------------------------------------------------- policy

class FakeFs {
  constructor(c, policyPath, basePolicy) {
    const dirDefault = () => ({ kind: "dir", uid: 0, mode: 0o755, writable: false });
    this.entries = new Map();
    let current = path.posix.dirname(policyPath);
    for (;;) {
      this.entries.set(current, dirDefault());
      if (current === "/") break;
      current = path.posix.dirname(current);
    }
    this.entries.set(policyPath, { kind: "file", uid: 0, mode: 0o644, writable: false });
    for (const [p, override] of Object.entries(c.entries || {})) {
      if (override === null) this.entries.delete(p);
      else {
        const merged = { ...(this.entries.get(p) || dirDefault()) };
        for (const [k, v] of Object.entries(override)) merged[k] = k === "mode" ? parseInt(v, 8) : v;
        this.entries.set(p, merged);
      }
    }
    const data = c.content ? buildBytes(c.content) : Buffer.from(JSON.stringify(c.doc || basePolicy), "utf8");
    this.files = new Map([[policyPath, data]]);
    this.realpaths = c.realpath || {};
    this.read = {};
    for (const [k, v] of Object.entries(c.read || {})) this.read[k] = k === "mode" ? parseInt(v, 8) : v;
    this.readNoFollow = this.readNoFollow.bind(this);
    this.readInRoot = this.readInRoot.bind(this);
  }

  info(entry, p) {
    return { kind: entry.kind, uid: entry.uid, mode: entry.mode, size: (this.files.get(p) || Buffer.alloc(0)).length };
  }

  lstat(p) {
    const entry = this.entries.get(p);
    return entry === undefined ? null : this.info(entry, p);
  }

  accessWritable(p) {
    return this.entries.get(p).writable;
  }

  realpath(p) {
    return this.realpaths[p] ?? p;
  }

  readInRoot(root, name, maxBytes) {
    if (this.lstat(root) === null) throw new rt.FileReadError("missing");
    return this.readNoFollow(`${root}/${name}`, maxBytes);
  }

  readNoFollow(p, maxBytes) {
    if (this.read.error) throw new rt.FileReadError(this.read.error);
    const entry = this.entries.get(p);
    if (entry === undefined) throw new rt.FileReadError("missing");
    if (entry.kind === "symlink") throw new rt.FileReadError("symlink");
    const { error: _e, ...overrides } = this.read;
    const info = this.info({ ...entry, ...overrides }, p);
    if (info.kind !== "file") throw new rt.FileReadError("not_regular");
    if (info.size > maxBytes) throw new rt.FileReadError("too_large");
    return [this.files.get(p), info];
  }
}

const policyView = (t) => ({
  host: t.host, port: t.port, database: t.database, role: t.role,
  server_addresses: [...t.serverAddresses], server_port: t.serverPort,
});

test("policy fixture cases", () => {
  const fixture = loadFixture("policy_cases.json");
  for (const c of fixture.cases) {
    const provider = new FakeFs(c, fixture.policy_path, fixture.base_policy);
    const got = outcomeOf(() => rt.loadPolicy(null, provider, { platform: c.platform }));
    if (c.expected.ok) {
      assert.equal(got[0], "ok", `${c.name}: ${JSON.stringify(got[1])}`);
      assert.deepEqual(policyView(got[1]), c.expected.ok, c.name);
    } else {
      assert.deepEqual(got, ["error", expectedError(c.expected)], c.name);
    }
  }
});

test("policy paths are fixed and ignore HOME", () => {
  const saved = process.env.HOME;
  process.env.HOME = "/tmp/redirected-home";
  try {
    assert.equal(rt.policyPath("darwin"), "/Library/Application Support/Bizqlab/db-policy.json");
    assert.equal(rt.policyPath("linux"), "/etc/bizqlab/db-policy.json");
  } finally {
    process.env.HOME = saved;
  }
  assert.throws(() => rt.policyPath("win32"), { code: "policy_unsupported_platform" });
});

test("real provider rejects a user-owned temporary policy", () => {
  if (process.getuid() === 0) return;
  withTempDir((dir) => {
    const p = path.join(dir, "db-policy.json");
    fs.writeFileSync(p, JSON.stringify(loadFixture("policy_cases.json").base_policy));
    fs.chmodSync(p, 0o444);
    assert.throws(() => rt.loadPolicy(p), { code: "policy_not_root_owned" });
  });
});

// ------------------------------------------------------------ combined

const POLICY = "/Library/Application Support/Bizqlab/db-policy.json";
const PROFILE = "/synthetic/repo/.env.local";
const SENTINEL = "/synthetic/repo/scripts/bootstrap_transit_db.py";

function provider({ profile = null, policyCase = {}, sentinel = true } = {}) {
  const fp = new FakeFs(policyCase, POLICY, loadFixture("policy_cases.json").base_policy);
  if (profile !== null) {
    fp.entries.set(PROFILE, { kind: "file", uid: 501, mode: 0o600, writable: true });
    fp.files.set(PROFILE, Buffer.from(profile));
  }
  if (sentinel) fp.entries.set(SENTINEL, { kind: "file", uid: 501, mode: 0o644, writable: true });
  return fp;
}

function profileText(overrides = {}) {
  const values = { ...loadFixture("validation_cases.json").base_profile, ...overrides };
  return Object.entries(values).map(([k, v]) => `${k}=${v}\n`).join("");
}

const resolve = (env, p, buildRootDir = "/synthetic/build") => rt.resolveRuntime(env, {
  purpose: "transit-api", profilePath: PROFILE, repoRootSentinel: SENTINEL, policyFile: POLICY, buildRootDir, provider: p,
});

test("resolveRuntime: development end to end", () => {
  const result = resolve({}, provider({ profile: profileText() }));
  assert.equal(result.mode, "development");
  assert.equal(result.development.target.applicationName, "bizqlab-dev-transit-api");
  assert.ok(!util.inspect(result, { depth: 5 }).includes(SYNTHETIC_PASSWORD));
  assert.ok(!JSON.stringify(result).includes(SYNTHETIC_PASSWORD));
});

test("resolveRuntime: development requires policy, profile and a confirmed repo root", () => {
  assert.throws(() => resolve({}, provider({ profile: profileText(), policyCase: { entries: { [POLICY]: null } } })), { code: "policy_missing" });
  assert.throws(() => resolve({}, provider({ sentinel: false })), { code: "repo_root_unconfirmed" });
  assert.throws(() => resolve({}, provider()), { code: "profile_missing" });
});

test("resolveRuntime: railway run on this workstation is refused even with an attestation", () => {
  const env = { BIZQLAB_RUNTIME: "production", RAILWAY_PROJECT_ID: "x", RAILWAY_ENVIRONMENT_ID: "x", RAILWAY_SERVICE_ID: "x" };
  assert.throws(() => resolve(env, provider({ profile: profileText() })), { code: "railway_context_on_workstation" });
});

test("resolveRuntime: attested production from a build-root-only copy", () => {
  withTempDir((dir) => {
    // Copy only the module into a bare build root; it must need nothing outside it.
    fs.mkdirSync(path.join(dir, "config"));
    fs.copyFileSync(require.resolve("../config/runtimeEnv"), path.join(dir, "config", "runtimeEnv.js"));
    const copy = require(path.join(dir, "config", "runtimeEnv.js"));
    assert.equal(copy.BUILD_ROOT_DIR, dir);
    const base = loadFixture("attestation_cases.json").base_doc;
    const env = { BIZQLAB_RUNTIME: "production", RAILWAY_PROJECT_ID: "proj-1", RAILWAY_ENVIRONMENT_ID: "env-1", RAILWAY_SERVICE_ID: "svc-1" };
    const noWorkstation = { policyFile: path.join(dir, "no-policy.json"), profilePath: path.join(dir, "no-profile") };
    const attestation = path.join(dir, copy.ATTESTATION_FILENAME);
    fs.writeFileSync(attestation, JSON.stringify({ ...base, build_root: "." }));
    assert.throws(() => copy.resolveRuntime(env, { purpose: "transit-api", ...noWorkstation }), { code: "production_not_attested" });
    fs.writeFileSync(attestation, JSON.stringify({ ...base, build_root: "backend/transit_api" }));
    const result = copy.resolveRuntime(env, { purpose: "transit-api", ...noWorkstation });
    assert.deepEqual([result.mode, result.development], ["production", null]);
  });
});

// ----------------------------------------------------------- sanitization

function assertSanitized(error, code) {
  assert.ok(error instanceof rt.RuntimeConfigError);
  assert.equal(error.code, code);
  assert.ok(!("cause" in error));
  const rendered = `${error.stack}\n${util.inspect(error)}\n${JSON.stringify(error)}`;
  assert.ok(!rendered.includes(SYNTHETIC_PASSWORD), rendered);
  assert.ok(!rendered.includes("postgresql://"), rendered);
}

test("every validation error omits the password", () => {
  const fixture = loadFixture("validation_cases.json");
  for (const c of fixture.cases) {
    if (!c.expected.error) continue;
    const [profile, policy] = validationInputs(fixture, c);
    try {
      rt.resolveDevelopmentTarget(profile, policy, { inheritedEnv: c.inherited_env, purpose: c.purpose, cli: c.cli });
      assert.fail(`expected refusal: ${c.name}`);
    } catch (error) {
      assertSanitized(error, c.expected.error.code);
      assert.ok(!util.inspect(error).includes("p@ss"), c.name);
    }
  }
});

test("grammar and policy errors carry no value and no cause", () => {
  try {
    rt.parseProfile(Buffer.from(`PGPASSWORD=${SYNTHETIC_PASSWORD} #x\n`));
    assert.fail("expected refusal");
  } catch (error) {
    assertSanitized(error, "profile_unquoted_hash");
  }
  const fixture = loadFixture("policy_cases.json");
  const p = new FakeFs({ content: [{ text: `{"password": "${SYNTHETIC_PASSWORD}"` }] }, fixture.policy_path, fixture.base_policy);
  try {
    rt.loadPolicy(null, p, { platform: "darwin" });
    assert.fail("expected refusal");
  } catch (error) {
    assertSanitized(error, "policy_malformed");
  }
});

test("representations mask the password", () => {
  const fixture = loadFixture("validation_cases.json");
  const [profile, policy] = validationInputs(fixture, { profile: {}, policy: {} });
  const res = rt.resolveDevelopmentTarget(profile, policy, { inheritedEnv: {}, purpose: "web" });
  for (const text of [util.inspect(res), String(res), JSON.stringify(res), util.inspect(res.target), String(res.target),
    JSON.stringify(res.target), JSON.stringify({ ...res.target }), Object.keys(res.target).join(",")]) {
    assert.ok(!text.includes(SYNTHETIC_PASSWORD), text);
  }
  assert.equal(res.target.password, SYNTHETIC_PASSWORD);
  assert.ok(res.databaseUrl.includes(SYNTHETIC_PASSWORD));
});
