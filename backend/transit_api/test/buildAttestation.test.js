"use strict";
/**
 * The transit-api build attestation generator and checker (design §3.4), mirroring
 * test/test_build_attestation.py. Temporary build roots, synthetic Railway
 * identifiers and injected workstation indicators; nothing connects anywhere.
 */
const test = require("node:test");
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const rt = require("../config/runtimeEnv");
const gen = require("../scripts/writeBuildAttestation");
const checker = require("../scripts/checkBuildAttestation");

const SERVICE = path.resolve(__dirname, "..");
const COMMIT = "0123456789abcdef0123456789abcdef01234567";
const ENV = { RAILWAY_PROJECT_ID: "proj-1", RAILWAY_ENVIRONMENT_ID: "env-1", RAILWAY_SERVICE_ID: "svc-1" };
const NOW = new Date("2026-10-16T12:00:00.123Z");
const noWorkstation = () => [false, false];

function withRoot(fn) {
  const dir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "bizqlab-attest-")));
  try {
    return fn(dir, path.join(dir, rt.ATTESTATION_FILENAME));
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

const write = (root, env = ENV, options = {}) => gen.writeAttestation(root, env, { now: NOW, isWorkstation: noWorkstation, ...options });

test("the written marker is valid for this build only", () => withRoot((root, marker) => {
  const env = { ...ENV, RAILWAY_GIT_COMMIT_SHA: COMMIT };
  assert.equal(write(root, env), "written");
  assert.equal(fs.statSync(marker).mode & 0o777, 0o444);
  assert.deepEqual(JSON.parse(fs.readFileSync(marker, "utf8")), {
    schema: 1, kind: "bizqlab-railway-build", build_root: "backend/transit_api", railway_service_id: "svc-1",
    railway_environment_id: "env-1", git_commit: COMMIT, generated_at: "2026-10-16T12:00:00Z",
  });
  assert.equal(rt.readAttestation(root, { env }), "valid");
  assert.equal(rt.readAttestation(root, { env: { ...env, RAILWAY_SERVICE_ID: "svc-2" } }), "invalid:service_mismatch");
  assert.equal(rt.readAttestation(root, { env: { ...env, RAILWAY_ENVIRONMENT_ID: "env-2" } }), "invalid:environment_mismatch");
  assert.equal(rt.readAttestation(root, { env: { ...env, RAILWAY_GIT_COMMIT_SHA: "f".repeat(40) } }), "invalid:commit_mismatch");
  assert.equal(rt.readAttestation(root, { buildRoot: ".", env }), "invalid:build_root");
}));

test("missing or malformed identifiers and workstations write nothing", () => withRoot((root, marker) => {
  const cases = [
    [{ RAILWAY_ENVIRONMENT_ID: "env-1" }, "missing_build_identifier", "RAILWAY_SERVICE_ID"],
    [{ RAILWAY_SERVICE_ID: "svc-1" }, "missing_build_identifier", "RAILWAY_ENVIRONMENT_ID"],
    [{ ...ENV, RAILWAY_SERVICE_ID: "svc/1" }, "invalid_build_identifier", "RAILWAY_SERVICE_ID"],
    [{ ...ENV, RAILWAY_GIT_COMMIT_SHA: "ABC" }, "invalid_build_identifier", "RAILWAY_GIT_COMMIT_SHA"],
  ];
  for (const [env, code, key] of cases) {
    assert.throws(() => write(root, env), (e) => e.code === code && e.key === key, code);
    assert.ok(!fs.existsSync(marker));
  }
  for (const indicators of [[true, false], [false, true]]) {
    assert.throws(() => write(root, ENV, { isWorkstation: () => indicators }), { code: "workstation_build_refused" });
    assert.ok(!fs.existsSync(marker));
  }
}));

test("a rebuild keeps an identical marker and refuses any other", () => withRoot((root, marker) => {
  write(root);
  const before = fs.readFileSync(marker);
  assert.equal(gen.writeAttestation(root, ENV, { now: new Date("2026-10-17T09:30:00Z"), isWorkstation: noWorkstation }), "unchanged");
  assert.deepEqual(fs.readFileSync(marker), before);
  for (const env of [{ ...ENV, RAILWAY_SERVICE_ID: "svc-2" }, { ...ENV, RAILWAY_GIT_COMMIT_SHA: COMMIT }]) {
    assert.throws(() => write(root, env), { code: "existing_marker_mismatch" });
    assert.deepEqual(fs.readFileSync(marker), before);
  }
  fs.chmodSync(marker, 0o644);
  fs.writeFileSync(marker, JSON.stringify({ ...JSON.parse(before), build_root: "." }));
  assert.throws(() => write(root), { code: "existing_marker_mismatch" });
  fs.rmSync(marker);
  fs.writeFileSync(path.join(root, "elsewhere.json"), before);
  fs.symlinkSync(path.join(root, "elsewhere.json"), marker);
  assert.throws(() => write(root), { code: "existing_marker_symlink" });
}));

test("the generator command without Railway identifiers refuses and writes nothing", () => {
  const marker = path.join(SERVICE, rt.ATTESTATION_FILENAME);
  assert.ok(!fs.existsSync(marker));
  const env = Object.fromEntries(Object.entries(process.env).filter(([k]) => !/^(RAILWAY_|BIZQLAB_|PG|NODE_)/.test(k)));
  const result = spawnSync(process.execPath, ["scripts/writeBuildAttestation.js"], { cwd: SERVICE, env, encoding: "utf8" });
  assert.equal(result.status, 2);
  assert.match(result.stderr, /missing_build_identifier \[key=RAILWAY_SERVICE_ID\]/);
  assert.ok(!fs.existsSync(marker));
});

test("the checker classifies without printing values", () => withRoot((root) => {
  write(root);
  const lines = [];
  const saved = console.log;
  console.log = (line) => lines.push(line);
  try {
    assert.equal(checker.main(ENV, root), 0);
    assert.equal(checker.main({ ...ENV, RAILWAY_SERVICE_ID: "svc-2" }, root), 1);
  } finally {
    console.log = saved;
  }
  assert.match(lines[0], /^attestation: valid /);
  assert.match(lines[1], /^attestation: invalid:service_mismatch /);
  assert.ok(!lines.join("\n").includes("svc-1"));
}));
