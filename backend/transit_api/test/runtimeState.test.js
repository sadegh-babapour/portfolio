"use strict";
/**
 * Lifecycle tests for config/runtimeState.js and db/pool.js: state, revocation,
 * identity on every new client, guarded pool and client queries, and the startup
 * gate. The real pg Pool (pg-pool 3.13) runs over a fake Client; files come from an
 * injected provider whose metadata the tests mutate. No database, no network.
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const util = require("node:util");
const { Pool } = require("pg");

const rt = require("../config/runtimeEnv");
const runtime = require("../config/runtimeState");
const { createPool, openPool, ready } = require("../db/pool");
const {
  FakeServer, IDENTITY, LifecycleProvider, MARKERS, POLICY, PROFILE, SYN_PW, makeFakeClient, profileText,
} = require("./helpers/runtimeFakes");

const ANCESTOR = "/Library/Application Support/Bizqlab";

function setup({ provider = new LifecycleProvider(), env = {}, server = new FakeServer() } = {}) {
  runtime.resetForTests();
  const inputs = provider.inputs(env);
  const savedDefaults = runtime.DEFAULTS.inputs;
  runtime.DEFAULTS.inputs = () => inputs;
  const FakeClient = makeFakeClient(server);
  class TestPool extends Pool {
    constructor(options) {
      super({ ...options, Client: FakeClient });
      TestPool.options = options;
    }
  }
  const exits = [];
  const ctx = {
    provider, env, inputs, server, TestPool, exits,
    exit: (code) => {
      exits.push(code);
    },
    restore() {
      runtime.DEFAULTS.inputs = savedDefaults;
      runtime.resetForTests();
    },
  };
  return ctx;
}

async function withSetup(options, fn) {
  const ctx = setup(options);
  try {
    await fn(ctx);
  } finally {
    ctx.restore();
  }
}

function assertSanitized(error) {
  assert.ok(error instanceof rt.RuntimeConfigError, String(error));
  assert.ok(!("cause" in error));
  const rendered = `${error.stack}\n${util.inspect(error)}\n${JSON.stringify(error)}`;
  assert.ok(!rendered.includes(SYN_PW), rendered);
  assert.ok(!rendered.includes("postgresql://"), rendered);
}

const nextTick = () => new Promise((resolve) => setImmediate(resolve));

// ------------------------------------------------------------------- state

test("verifyRuntime commits development and applies non-DB keys only where unset", () => withSetup({
  provider: new LifecycleProvider({ profile: profileText({ TRANSIT_API_PORT: "4100", APP_ENV: "development" }) }),
  env: { APP_ENV: "preset" },
}, ({ env }) => {
  const state = runtime.verifyRuntime("transit-api");
  assert.deepEqual([state.mode, state.status], ["development", runtime.ACTIVE]);
  assert.equal(state.development.target.applicationName, "bizqlab-dev-transit-api");
  assert.deepEqual([env.TRANSIT_API_PORT, env.APP_ENV], ["4100", "preset"]);
  assert.equal(env.DATABASE_URL, undefined); // nothing DB-related is exported into the environment
  assert.equal(runtime.assertUsable(), state);
  assert.ok(!util.inspect(state, { depth: 6 }).includes(SYN_PW));
}));

test("identical re-verify is a no-op; a different or invalid one revokes", () => withSetup({}, ({ provider }) => {
  const state = runtime.verifyRuntime("transit-api");
  assert.equal(runtime.verifyRuntime("transit-api"), state);
  assert.throws(() => runtime.verifyRuntime("other"), { code: "runtime_revoked", trigger: "rebootstrap_conflict" });
  assert.throws(() => runtime.assertUsable(), { trigger: "rebootstrap_conflict" });
  assert.throws(() => runtime.verifyRuntime("transit-api"), { trigger: "rebootstrap_conflict" });
  runtime.resetForTests();
  runtime.verifyRuntime("transit-api");
  provider.rewrite(PROFILE, "PGHOST = broken\n");
  assert.throws(() => runtime.verifyRuntime("transit-api"), { code: "profile_space_around_equals" });
  assert.throws(() => runtime.assertUsable(), { trigger: "rebootstrap_invalid" });
}));

test("a failed initial verify commits nothing and leaves the environment unchanged", () => {
  const provider = new LifecycleProvider();
  provider.delete(POLICY);
  return withSetup({ provider, env: { KEEP: "1", PGHOST: "192.168.1.50" } }, ({ env }) => {
    assert.throws(() => runtime.verifyRuntime("transit-api"), { code: "policy_missing" });
    assert.deepEqual(env, { KEEP: "1", PGHOST: "192.168.1.50" });
    assert.equal(runtime.currentState(), null);
    assert.throws(() => runtime.assertUsable(), { code: "runtime_not_bootstrapped" });
  });
});

test("environment drift revokes; unrelated changes do not", async () => {
  const drifts = [
    ["PGOPTIONS", (env) => { env.PGOPTIONS = "-c search_path=evil"; }],
    ["DATABASE_URL", (env) => { env.DATABASE_URL = "postgresql://x@db.railway.internal/railway"; }],
    ["PGHOST", (env) => { env.PGHOST = "10.9.9.9"; }],
    ["BIZQLAB_RUNTIME", (env) => { env.BIZQLAB_RUNTIME = "production"; }],
    ["RAILWAY_SERVICE_ID", (env) => { env.RAILWAY_SERVICE_ID = "svc-1"; }],
  ];
  for (const [key, mutate] of drifts) {
    await withSetup({}, ({ env }) => {
      runtime.verifyRuntime("transit-api");
      env.HOME = "/tmp/elsewhere";
      env.pghost = "8.8.8.8";
      runtime.assertUsable();
      mutate(env);
      assert.throws(() => runtime.assertUsable(), (error) => error.trigger === "env_drift" && error.key === key, key);
    });
  }
});

test("metadata-only changes revoke; unrelated sibling creation in policy ancestors does not", async () => {
  const mutations = [
    ["chmod profile", (p) => p.chmod(PROFILE, 0o640)],
    ["chown profile", (p) => p.chown(PROFILE, { gid: 20 })],
    ["chmod policy", (p) => p.chmod(POLICY, 0o444)],
    ["chown policy", (p) => p.chown(POLICY, { uid: 501 })],
    ["touch policy", (p) => p.touch(POLICY)],
    ["chmod ancestor", (p) => p.chmod(ANCESTOR, 0o750)],
    ["chown ancestor", (p) => p.chown("/Library", { gid: 80 })],
    ["ACL on ancestor", (p) => p.grantAcl(ANCESTOR)],
    ["symlink swap of profile", (p) => p.swapToSymlink(PROFILE)],
    ["symlink swap of ancestor", (p) => p.swapToSymlink(ANCESTOR)],
    ["replacement of ancestor directory", (p) => p.replaceIdentical(ANCESTOR)],
    ["identical replacement of policy", (p) => p.replaceIdentical(POLICY)],
    ["deletion of policy", (p) => p.delete(POLICY)],
    ["deletion of profile", (p) => p.delete(PROFILE)],
  ];
  for (const [name, mutate] of mutations) {
    await withSetup({}, ({ provider }) => {
      runtime.verifyRuntime("transit-api");
      mutate(provider);
      assert.throws(() => runtime.assertUsable(), { trigger: "metadata_changed" }, name);
    });
  }
  await withSetup({}, ({ provider }) => {
    const state = runtime.verifyRuntime("transit-api");
    for (const directory of ["/", "/Library", "/Library/Application Support", ANCESTOR]) {
      provider.addSibling(directory);
      assert.equal(runtime.assertUsable(), state, directory);
    }
  });
});

test("production has no per-statement checks", () => withSetup({
  provider: new LifecycleProvider({ production: true }), env: { BIZQLAB_RUNTIME: "production", ...MARKERS },
}, ({ provider, env }) => {
  const state = runtime.verifyRuntime("transit-api");
  assert.deepEqual([state.mode, state.development], ["production", null]);
  provider.statCalls = 0;
  env.PGHOST = "10.9.9.9";
  assert.equal(runtime.assertUsable(), state);
  assert.equal(provider.statCalls, 0);
  assert.throws(() => runtime.createDevelopmentPool(state, Pool), { code: "development_only" });
}));

test("real metadata ignores sibling activity in ancestors but sees mode changes", () => {
  const fs = require("node:fs");
  const os = require("node:os");
  const path = require("node:path");
  const dir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "bizqlab-meta-")));
  try {
    const ancestor = path.join(dir, "Bizqlab");
    fs.mkdirSync(ancestor);
    const inputs = { env: {}, profilePath: path.join(dir, "profile"), policyFile: path.join(ancestor, "db-policy.json") };
    fs.writeFileSync(inputs.profilePath, "x");
    fs.writeFileSync(inputs.policyFile, "{}");
    const before = runtime.fileMetadata(inputs);
    fs.mkdirSync(path.join(dir, "unrelated-sibling"));
    fs.writeFileSync(path.join(ancestor, "unrelated.txt"), "y");
    assert.deepEqual(runtime.fileMetadata(inputs), before);
    fs.chmodSync(ancestor, 0o700);
    assert.notDeepEqual(runtime.fileMetadata(inputs), before);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

// -------------------------------------------------------------------- pool

test("every new client runs the identity query before application SQL", () => withSetup({}, async (ctx) => {
  const pool = createPool({ PoolClass: ctx.TestPool, exit: ctx.exit });
  const options = ctx.TestPool.options;
  for (const key of ["host", "port", "database", "user", "password", "connectionTimeoutMillis", "application_name"]) {
    assert.ok(options[key], key);
  }
  assert.equal(options.ssl, false);
  await ready(pool);
  await pool.query("SELECT 1");
  const client = await pool.connect();
  await client.query("SELECT 2");
  client.release();
  assert.deepEqual(ctx.server.statements(), [runtime.IDENTITY_SQL, "SELECT 1", "SELECT 2"]);
  // A destroyed client is replaced by a new one, which is verified again (reconnect).
  const doomed = await pool.connect();
  doomed.release(true);
  await pool.query("SELECT 3");
  assert.deepEqual(ctx.server.statements(2), [runtime.IDENTITY_SQL, "SELECT 3"]);
  await pool.end();
}));

test("a wrong identity rejects the acquire, ends the client, revokes, ends the pool and exits", async () => {
  const wrongs = [
    ["database", ["postgres", ...IDENTITY.slice(1)]],
    ["role", [IDENTITY[0], "postgres", ...IDENTITY.slice(2)]],
    ["address", [...IDENTITY.slice(0, 2), "10.0.0.9", IDENTITY[3]]],
    ["NULL address (unix socket)", [...IDENTITY.slice(0, 2), null, IDENTITY[3]]],
    ["port", [...IDENTITY.slice(0, 3), 5433]],
    ["port as text", [...IDENTITY.slice(0, 3), "5432"]],
  ];
  for (const [name, identity] of wrongs) {
    await withSetup({ server: new FakeServer({ identity }) }, async (ctx) => {
      const pool = createPool({ PoolClass: ctx.TestPool, exit: ctx.exit });
      const error = await pool.query("UPDATE t SET x = 1").then(() => null, (e) => e);
      assert.equal(error && error.code, "identity_mismatch", name);
      assertSanitized(error);
      assert.deepEqual(ctx.server.statements(), [runtime.IDENTITY_SQL], name);
      assert.equal(ctx.server.clients[0]._ending, true, name);
      assert.throws(() => runtime.assertUsable(), { trigger: "identity_mismatch" });
      await nextTick();
      await nextTick();
      assert.deepEqual(ctx.exits, [1], name);
      assert.equal(pool.ending, true, name);
    });
  }
});

test("an equivalent IPv6 server address matches", () => {
  const policy = { database: "d", role: "r", serverAddresses: ["fd00::1"], serverPort: 5432 };
  assert.ok(runtime.identityMatches(["d", "r", "fd00:0:0:0:0:0:0:1", 5432], policy));
  assert.ok(runtime.identityMatches(["d", "r", "FD00::1", 5432], policy));
  assert.ok(!runtime.identityMatches(["d", "r", "fd00::2", 5432], policy));
});

test("an identity query failure is sanitized, revokes, and carries only the SQLSTATE", () => {
  const server = new FakeServer();
  server.failSql = "current_database()";
  return withSetup({ server }, async (ctx) => {
    const pool = createPool({ PoolClass: ctx.TestPool, exit: ctx.exit });
    const error = await ready(pool).then(() => null, (e) => e);
    assert.deepEqual([error.code, error.sqlstate], ["identity_query_failed", "57P01"]);
    assertSanitized(error);
    assert.throws(() => runtime.assertUsable(), { trigger: "identity_query_failed" });
  });
});

test("retained clients and idle pooled clients cannot query after revocation, but can be released", () => withSetup({}, async (ctx) => {
  const pool = createPool({ PoolClass: ctx.TestPool, exit: ctx.exit });
  const retained = await pool.connect();
  const idle = await pool.connect();
  idle.release(); // back to the pool, still connected
  const logged = ctx.server.log.length;
  ctx.env.PGHOST = "10.9.9.9"; // drift, detected at the next boundary without a new connection
  const fromRetained = await retained.query("UPDATE t SET x = 1").then(() => null, (e) => e);
  assert.equal(fromRetained.trigger, "env_drift");
  assertSanitized(fromRetained);
  // Callback style is refused the same way.
  const viaCallback = await new Promise((resolve) => { retained.query("SELECT 1", (err) => resolve(err)); });
  assert.equal(viaCallback.code, "runtime_revoked");
  // An idle pooled client is never reached: the pool refuses first.
  const fromPool = await pool.query("SELECT 1").then(() => null, (e) => e);
  assert.equal(fromPool.code, "runtime_revoked");
  const fromConnect = await pool.connect().then(() => null, (e) => e);
  assert.equal(fromConnect.code, "runtime_revoked");
  assert.equal(ctx.server.log.length, logged);
  retained.release(); // always allowed
  await nextTick();
  await nextTick();
  assert.deepEqual(ctx.exits, [1]);
}));

test("a new client after revocation is refused before its identity query", () => withSetup({}, async (ctx) => {
  const pool = createPool({ PoolClass: ctx.TestPool, exit: ctx.exit });
  await ready(pool);
  const held = await pool.connect(); // the verified client stays checked out, so the next acquire is new
  ctx.provider.chmod(PROFILE, 0o640);
  // Bypass the pool proxy to reach onConnect directly, as a reconnect would.
  const error = await ctx.TestPool.prototype.connect.call(pool).then(() => null, (e) => e);
  assert.equal(error.trigger, "metadata_changed");
  assert.deepEqual(ctx.server.statements(), [runtime.IDENTITY_SQL]);
  assert.equal(ctx.server.clients.length, 2);
  assert.equal(ctx.server.clients[1]._ending, true); // pg-pool ended the refused client
  held.release();
}));

test("openPool refuses before constructing any pool", async () => {
  const cases = [
    [{ env: { DATABASE_URL: "postgresql://u:synthetic-prod@db.railway.internal:5432/railway" } }, "inherited_conflict"],
    [{ env: { PGOPTIONS: "-c search_path=evil" } }, "inherited_pg_key"],
    [{ env: { ...MARKERS } }, "railway_context_on_workstation"],
    [{ env: { BIZQLAB_RUNTIME: "production", ...MARKERS }, provider: new LifecycleProvider({ production: true, attestation: null }) },
      "production_not_attested"],
    [{ env: { ...MARKERS }, provider: new LifecycleProvider({ production: true }) }, "railway_context_without_production_mode"],
  ];
  for (const [options, code] of cases) {
    await withSetup(options, (ctx) => {
      let constructed = 0;
      class Counting extends ctx.TestPool {
        constructor(o) {
          super(o);
          constructed += 1;
        }
      }
      const errors = [];
      const saved = console.error;
      console.error = (line) => errors.push(line);
      try {
        assert.equal(openPool({ PoolClass: Counting, exit: ctx.exit }), undefined);
      } finally {
        console.error = saved;
      }
      assert.deepEqual(ctx.exits, [2], code);
      assert.equal(constructed, 0, code);
      assert.equal(errors.length, 1);
      assert.match(errors[0], new RegExp(`^BIZQLAB RUNTIME REFUSED \\(transit-api\\): ${code}`));
      assert.ok(!errors[0].includes("synthetic-prod"));
    });
  }
});

test("attested production keeps today's pool configuration", () => withSetup({
  provider: new LifecycleProvider({ production: true }), env: { BIZQLAB_RUNTIME: "production", ...MARKERS },
}, async (ctx) => {
  const saved = { ...process.env };
  Object.assign(process.env, { PGHOST: "db.railway.internal", PGPORT: "6543", PGDATABASE: "railway", PGUSER: "u", PGPASSWORD: "synthetic-prod" });
  try {
    const pool = createPool({ PoolClass: ctx.TestPool, exit: ctx.exit });
    assert.deepEqual(ctx.TestPool.options, {
      host: "db.railway.internal", port: 6543, database: "railway", user: "u", password: "synthetic-prod",
    });
    await ready(pool); // no probe in production
    assert.deepEqual(ctx.server.connects, []);
    await pool.query("SELECT 1");
    assert.deepEqual(ctx.server.statements(), ["SELECT 1"]); // no identity query, no per-statement checks
    await pool.end();
  } finally {
    for (const key of Object.keys(process.env)) if (!(key in saved)) delete process.env[key];
    Object.assign(process.env, saved);
  }
}));
