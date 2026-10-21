"use strict";
/**
 * Exact startup commands for the transit API: `node server.js` and `npm start`, run
 * as subprocesses behind test/shims/isolate.js (NODE_OPTIONS=--require). The shim
 * supplies synthetic configuration and a fake pg Client; outbound connections stay
 * blocked. Covers the refusal-before-pool gate, identity before listen, today's
 * production pool, and a build-root-only copy of the service.
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const runtime = require("../config/runtimeState");
const rt = require("../config/runtimeEnv");
const { MARKERS, SYN_PW, loadFixture } = require("./helpers/runtimeFakes");

const SERVICE = path.resolve(__dirname, "..");
const SHIM = path.join(__dirname, "shims", "isolate.js");
const PROD_URL = "postgresql://prod_user:synthetic-prod-Pw@db.railway.internal:5432/railway";
const BASE_DOC = loadFixture("attestation_cases.json").base_doc;
const STRIP = /^(PG|RAILWAY_|BIZQLAB_|NODE_|npm_)|^DATABASE_URL$/;

function withTempDir(fn) {
  const dir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "bizqlab-start-")));
  try {
    return fn(dir);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

function start(scenario, { env = {}, command = [process.execPath, "server.js"], cwd = SERVICE } = {}) {
  return withTempDir((dir) => {
    const log = path.join(dir, "events.jsonl");
    const scenarioPath = path.join(dir, "scenario.json");
    fs.writeFileSync(scenarioPath, JSON.stringify({ log, ...scenario }));
    const base = Object.fromEntries(Object.entries(process.env).filter(([k]) => !STRIP.test(k)));
    const result = spawnSync(command[0], command.slice(1), {
      cwd,
      env: { ...base, NODE_OPTIONS: `--require "${SHIM}"`, BQ_NODE_SCENARIO: scenarioPath, ...env },
      encoding: "utf8",
      timeout: 60000,
    });
    const events = fs.existsSync(log) ? fs.readFileSync(log, "utf8").trim().split("\n").filter(Boolean).map(JSON.parse) : [];
    const output = `${result.stdout}${result.stderr}`;
    return { code: result.status, output, events, of: (kind) => events.filter((e) => e.event === kind) };
  });
}

const DB_EVENTS = new Set(["pool", "connect", "sql"]);

function assertRefusedBeforePool(run, code) {
  assert.equal(run.code, 2, run.output);
  assert.match(run.output, new RegExp(`BIZQLAB RUNTIME REFUSED \\(transit-api\\): ${code}`));
  assert.deepEqual(run.events.filter((e) => DB_EVENTS.has(e.event)), []);
  assert.deepEqual(run.of("listen"), []);
  assert.ok(!run.output.includes("synthetic-prod-Pw"));
  assert.ok(!run.output.includes(SYN_PW));
}

test("unsafe inputs are refused before any pool exists", () => {
  const cases = [
    [{}, { DATABASE_URL: PROD_URL }, "inherited_conflict"],
    [{}, { PGHOST: "10.9.9.9" }, "inherited_conflict"],
    [{}, { PGOPTIONS: "-c search_path=evil" }, "inherited_pg_key"],
    [{}, { PGSSLROOTCERT: "/tmp/x" }, "inherited_pg_key"],
    [{}, { BIZQLAB_RUNTIME: "production", ...MARKERS, DATABASE_URL: PROD_URL }, "railway_context_on_workstation"],
    [{ production: true }, { ...MARKERS, PGHOST: "db.railway.internal" }, "railway_context_without_production_mode"],
    [{ production: true, attestation: null }, { BIZQLAB_RUNTIME: "production", ...MARKERS }, "production_not_attested"],
    [{ production: true, attestation: { ...BASE_DOC, build_root: "." } }, { BIZQLAB_RUNTIME: "production", ...MARKERS },
      "production_not_attested"],
    [{ profile_overrides: { DATABASE_URL: "postgresql://x" } }, {}, "reserved_key"],
  ];
  for (const [scenario, env, code] of cases) {
    assertRefusedBeforePool(start(scenario, { env }), code);
  }
});

test("development verifies identity before listening, through an explicit guarded pool", () => {
  const run = start({});
  assert.equal(run.code, 0, run.output);
  assert.deepEqual(run.of("verified"), [{ event: "verified", purpose: "transit-api", mode: "development" }]);
  const [pool] = run.of("pool");
  assert.equal(pool.onConnect, true);
  for (const key of ["application_name", "connectionTimeoutMillis", "database", "host", "port", "ssl", "user"]) {
    assert.ok(pool.keys.includes(key), key);
  }
  const order = run.events.filter((e) => ["pool", "connect", "sql", "listen"].includes(e.event)).map((e) => e.event);
  assert.deepEqual(order, ["pool", "connect", "sql", "listen"]);
  assert.equal(run.of("sql")[0].statement, runtime.IDENTITY_SQL);
});

test("npm start runs the same gate", () => {
  const npm = process.platform === "win32" ? "npm.cmd" : "npm";
  const ok = start({}, { command: [npm, "start", "--silent"] });
  assert.equal(ok.code, 0, ok.output);
  assert.equal(ok.of("sql")[0].statement, runtime.IDENTITY_SQL);
  assert.equal(ok.of("listen").length, 1);
  const refused = start({}, { command: [npm, "start", "--silent"], env: { DATABASE_URL: PROD_URL } });
  assert.notEqual(refused.code, 0);
  assert.match(refused.output, /inherited_conflict/);
  assert.deepEqual(refused.events.filter((e) => DB_EVENTS.has(e.event)), []);
});

test("a wrong server identity stops startup before listen", () => {
  const run = start({ identity: ["portfolio_dev", "postgres", "192.168.1.50", 5432] });
  assert.notEqual(run.code, 0);
  assert.deepEqual(run.of("sql").map((e) => e.statement), [runtime.IDENTITY_SQL]);
  assert.deepEqual(run.of("listen"), []);
  assert.match(run.output, /identity_mismatch/);
  assert.ok(!run.output.includes(SYN_PW));
});

test("attested production keeps today's pool and lazy connections", () => {
  const env = {
    BIZQLAB_RUNTIME: "production", ...MARKERS, PGHOST: "db.railway.internal", PGPORT: "5432",
    PGDATABASE: "railway", PGUSER: "prod_user", PGPASSWORD: "synthetic-prod-Pw",
  };
  const run = start({ production: true }, { env });
  assert.equal(run.code, 0, run.output);
  assert.deepEqual(run.of("verified"), [{ event: "verified", purpose: "transit-api", mode: "production" }]);
  assert.deepEqual(run.of("pool"), [{ event: "pool", keys: ["database", "host", "port", "user"], onConnect: false }]);
  assert.deepEqual(run.of("connect"), []);
  assert.equal(run.of("listen").length, 1);
});

// ----------------------------------------------------- build-root-only copy

function copyServiceRoot(dir) {
  const root = path.join(dir, "transit_api");
  fs.mkdirSync(root);
  for (const entry of ["server.js", "package.json", "config", "db", "services", "scripts"]) {
    const from = path.join(SERVICE, entry);
    if (fs.existsSync(from)) fs.cpSync(from, path.join(root, entry), { recursive: true });
  }
  fs.symlinkSync(path.join(SERVICE, "node_modules"), path.join(root, "node_modules"));
  return root;
}

test("a build-root-only copy starts only with its own transit-api marker", () => {
  withTempDir((dir) => {
    const root = copyServiceRoot(dir);
    const realFs = { profilePath: path.join(dir, "no-profile"), policyFile: path.join(dir, "no-policy.json") };
    const env = { BIZQLAB_RUNTIME: "production", ...MARKERS, PGHOST: "db.railway.internal", PGDATABASE: "railway" };
    const marker = path.join(root, rt.ATTESTATION_FILENAME);
    const run = () => start({ real_fs: realFs }, { env, cwd: root });

    assertRefusedBeforePool(run(), "production_not_attested"); // absent
    fs.writeFileSync(marker, JSON.stringify(BASE_DOC)); // the Python services' "." marker
    assertRefusedBeforePool(run(), "production_not_attested");
    fs.rmSync(marker);
    fs.mkdirSync(path.join(root, ".bizqlab"));
    fs.writeFileSync(path.join(root, ".bizqlab", "build-attestation.json"), JSON.stringify({ ...BASE_DOC, build_root: rt.BUILD_ROOT }));
    assertRefusedBeforePool(run(), "production_not_attested"); // the retired path is not a fallback
    // The copy's own generator writes the marker, as the Railway build would.
    const generator = require(path.join(root, "scripts", "writeBuildAttestation.js"));
    assert.equal(generator.writeAttestation(root, env, { isWorkstation: () => [false, false] }), "written");
    const ok = run();
    assert.equal(ok.code, 0, ok.output);
    assert.deepEqual(ok.of("verified").map((e) => e.mode), ["production"]);
    assert.equal(ok.of("listen").length, 1);
  });
});

test("no transit API source opens a database connection outside db/pool.js", () => {
  const offenders = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (["node_modules", "test"].includes(entry.name)) continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.name.endsWith(".js")) {
        const text = fs.readFileSync(full, "utf8");
        if (/require\(["']pg(-pool)?["']\)|new (Pool|Client)\b|\.connect\(/.test(text)) offenders.push(path.relative(SERVICE, full));
      }
    }
  };
  walk(SERVICE);
  // pool.js constructs the pool after the gate; runtimeState.js holds the guarded pool and its probe.
  assert.deepEqual(offenders.sort(), ["config/runtimeState.js", "db/pool.js"]);
  const services = fs.readFileSync(path.join(SERVICE, "services", "transitService.js"), "utf8");
  assert.ok(!/\.connect\(|new Pool|require\("pg"\)/.test(services));
});

test("npm test runs every test file behind the isolation shim", { skip: !String(process.env.NODE_OPTIONS || "").includes("isolate.js") }, () => {
  const net = require("node:net");
  assert.throws(() => net.connect(5432, "192.0.2.1"), /blocked by test isolation/);
  assert.throws(() => new net.Socket().connect(5432, "192.0.2.1"), /blocked by test isolation/);
  for (const p of [rt.PROFILE_PATH, "/Library/Application Support/Bizqlab/db-policy.json"]) {
    assert.throws(() => fs.openSync(p, "r"), /blocked by test isolation/);
    assert.throws(() => fs.readFileSync(p), /blocked by test isolation/);
  }
});
