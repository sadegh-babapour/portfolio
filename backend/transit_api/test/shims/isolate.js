"use strict";
/**
 * Test-only isolation, loaded with NODE_OPTIONS=--require by `npm test`, by
 * test/run_isolated.py for Node children of the Python suite, and by the exact
 * startup commands (test/startup.test.js). Production code contains none of this.
 *
 * Always: outbound TCP/TLS connections are refused, and opening the real profile,
 * root .env files or the root approval policy is refused.
 * With BQ_NODE_SCENARIO (a JSON file):
 * - require("pg") returns the real pg whose Pool uses the fake Client from
 *   test/helpers/runtimeFakes.js; every pool construction and statement is logged;
 * - config/runtimeState.js gets synthetic inputs (or real files at given paths);
 * - http listen is recorded instead of performed, then the process exits 0.
 * Events are appended to the scenario's JSON-lines log as they happen.
 */
const fs = require("node:fs");
const http = require("node:http");
const Module = require("node:module");
const net = require("node:net");
const path = require("node:path");
const tls = require("node:tls");

function refuse() {
  throw new Error("network connection blocked by test isolation");
}
net.Socket.prototype.connect = refuse;
net.connect = refuse;
net.createConnection = refuse;
tls.connect = refuse;

const REPO = path.resolve(__dirname, "..", "..", "..", "..");
const PROTECTED = new Set([
  path.join(REPO, ".env.local"),
  path.join(REPO, ".env"),
  path.join(REPO, "frontend", ".env.development.local"),
  "/Library/Application Support/Bizqlab/db-policy.json",
  "/etc/bizqlab/db-policy.json",
]);
for (const name of ["openSync", "readFileSync"]) {
  const original = fs[name];
  fs[name] = function guarded(target, ...rest) {
    if (typeof target === "string" && PROTECTED.has(path.resolve(target))) {
      throw new Error("real configuration read blocked by test isolation");
    }
    return original.call(this, target, ...rest);
  };
}

const scenarioPath = process.env.BQ_NODE_SCENARIO;
if (scenarioPath) {
  const scenario = JSON.parse(fs.readFileSync(scenarioPath, "utf8"));
  const record = (event, fields = {}) => fs.appendFileSync(scenario.log, `${JSON.stringify({ event, ...fields })}\n`);
  const fakes = require("../helpers/runtimeFakes");
  const server = new fakes.FakeServer({
    identity: scenario.identity || fakes.IDENTITY,
    onLog: (connection, statement) => record("sql", { connection, statement }),
  });
  const FakeClient = fakes.makeFakeClient(server);
  const originalConnect = FakeClient.prototype.connect;
  FakeClient.prototype.connect = function connect(callback) {
    record("connect", { keys: Object.keys(this.options).filter((k) => k !== "password" && this.options[k] !== undefined).sort() });
    return originalConnect.call(this, callback);
  };

  let patchedPg = null;
  const originalLoad = Module._load;
  Module._load = function load(request, parent, isMain) {
    const loaded = originalLoad.call(this, request, parent, isMain);
    if (request === "pg") {
      if (patchedPg === null) {
        class Pool extends loaded.Pool {
          constructor(options) {
            record("pool", {
              keys: Object.keys(options).filter((k) => k !== "password").sort(),
              onConnect: typeof options.onConnect === "function",
            });
            super({ ...options, Client: FakeClient });
          }
        }
        patchedPg = { ...loaded, Pool };
      }
      return patchedPg;
    }
    let filename = null;
    try {
      filename = Module._resolveFilename(request, parent, isMain);
    } catch {
      filename = null;
    }
    if (filename && filename.endsWith(path.join("config", "runtimeState.js")) && !loaded.__bizqlabPatched) {
      loaded.__bizqlabPatched = true;
      if (scenario.real_fs) {
        const realInputs = loaded.realInputs;
        loaded.DEFAULTS.inputs = () => ({ ...realInputs(), ...scenario.real_fs });
      } else {
        const provider = new fakes.LifecycleProvider({
          profile: fakes.profileText(scenario.profile_overrides || {}),
          production: Boolean(scenario.production),
          attestation: scenario.attestation,
        });
        const inputs = provider.inputs(process.env);
        loaded.DEFAULTS.inputs = () => inputs;
      }
      const verify = loaded.verifyRuntime;
      loaded.verifyRuntime = (purpose, options) => {
        record("verify", { purpose });
        const state = verify(purpose, options);
        record("verified", { purpose, mode: state.mode });
        return state;
      };
    }
    return loaded;
  };

  http.Server.prototype.listen = function listen(port) {
    record("listen", { port: Number(port) });
    setImmediate(() => process.exit(0));
    return this;
  };
}
