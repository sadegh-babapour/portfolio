"use strict";
/**
 * Test-only fakes for the transit API runtime gate, shared by the unit tests and the
 * startup shim (test/shims/isolate.js):
 * - LifecycleProvider: the runtimeEnv provider plus the runtimeState metadata provider
 *   over one mutable in-memory tree (mirrors test/test_lifecycle.py LifecycleFs).
 * - makeFakeClient: a pg Client stand-in for the real pg Pool / pg-pool, which logs
 *   every statement and answers the identity query.
 */
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const path = require("node:path");

const rt = require("../../config/runtimeEnv");

const FIXTURES = path.resolve(__dirname, "..", "..", "..", "..", "test", "fixtures");
const POLICY = "/Library/Application Support/Bizqlab/db-policy.json";
const PROFILE = "/synthetic/repo/.env.local";
const SENTINEL = "/synthetic/repo/scripts/bootstrap_transit_db.py";
const BUILD = "/synthetic/build";
const SYN_PW = "synthetic-Pw_1";
const IDENTITY = ["portfolio_dev", "portfolio_dev_user", "192.168.1.50", 5432];
const MARKERS = { RAILWAY_PROJECT_ID: "proj-1", RAILWAY_ENVIRONMENT_ID: "env-1", RAILWAY_SERVICE_ID: "svc-1" };
const KIND_BITS = { file: 0o100000, dir: 0o040000, symlink: 0o120000, other: 0o010000 };

function loadFixture(name) {
  return JSON.parse(fs.readFileSync(path.join(FIXTURES, name), "utf8"));
}

function profileText(overrides = {}) {
  const values = { ...loadFixture("validation_cases.json").base_profile, ...overrides };
  return Object.entries(values).filter(([, v]) => v !== null).map(([k, v]) => `${k}=${v}\n`).join("");
}

class LifecycleProvider {
  constructor({ profile = profileText(), production = false, policyDoc = null, attestation = undefined } = {}) {
    this.ino = 100;
    this.entries = new Map();
    this.files = new Map();
    this.statCalls = 0;
    const rootDir = { kind: "dir", uid: 0, mode: 0o755, writable: false };
    for (const d of ["/", "/Library", "/Library/Application Support", "/Library/Application Support/Bizqlab"]) {
      this.add(d, rootDir);
    }
    const userDir = { kind: "dir", uid: 501, mode: 0o755, writable: true };
    for (const d of ["/synthetic", "/synthetic/repo", "/synthetic/repo/scripts", BUILD]) this.add(d, userDir);
    this.add(SENTINEL, { kind: "file", uid: 501, mode: 0o644, writable: true }, Buffer.from("# sentinel\n"));
    if (production) {
      const doc = attestation === undefined ? { ...loadFixture("attestation_cases.json").base_doc, build_root: rt.BUILD_ROOT } : attestation;
      if (doc !== null) {
        this.add(`${BUILD}/${rt.ATTESTATION_FILENAME}`, { kind: "file", uid: 501, mode: 0o444, writable: false },
          Buffer.from(JSON.stringify(doc)));
      }
    } else {
      this.add(POLICY, { kind: "file", uid: 0, mode: 0o644, writable: false },
        Buffer.from(JSON.stringify(policyDoc || loadFixture("policy_cases.json").base_policy)));
      if (profile !== null) this.add(PROFILE, { kind: "file", uid: 501, mode: 0o600, writable: true }, Buffer.from(profile));
    }
    this.readNoFollow = this.readNoFollow.bind(this);
    this.readInRoot = this.readInRoot.bind(this);
  }

  add(p, entry, data = null) {
    this.entries.set(p, { ...entry, ino: this.ino++, gid: 0, mtime: 0, ctime: 0 });
    if (data !== null) this.files.set(p, data);
  }

  info(entry, p) {
    return { kind: entry.kind, uid: entry.uid, mode: entry.mode, size: (this.files.get(p) || Buffer.alloc(0)).length };
  }

  // runtimeEnv provider
  lstat(p) {
    const entry = this.entries.get(p);
    return entry === undefined ? null : this.info(entry, p);
  }

  accessWritable(p) {
    const entry = this.entries.get(p);
    return Boolean(entry && entry.writable);
  }

  realpath(p) {
    return p;
  }

  readNoFollow(p, maxBytes) {
    const entry = this.entries.get(p);
    if (entry === undefined) throw new rt.FileReadError("missing");
    if (entry.kind === "symlink") throw new rt.FileReadError("symlink");
    const info = this.info(entry, p);
    if (info.kind !== "file") throw new rt.FileReadError("not_regular");
    if (info.size > maxBytes) throw new rt.FileReadError("too_large");
    return [this.files.get(p), info];
  }

  readInRoot(root, name, maxBytes) {
    if (this.lstat(root) === null) throw new rt.FileReadError("missing");
    return this.readNoFollow(`${root}/${name}`, maxBytes);
  }

  // runtimeState metadata provider
  statKey(p) {
    this.statCalls += 1;
    const e = this.entries.get(p);
    if (e === undefined) return null;
    return [1, e.ino, KIND_BITS[e.kind] | e.mode, e.uid, e.gid, (this.files.get(p) || Buffer.alloc(0)).length,
      e.mtime, e.ctime].map(String);
  }

  // metadata-only mutations (content unchanged)
  touch(p) {
    const e = this.entries.get(p);
    e.mtime += 1;
    e.ctime += 1;
  }

  chmod(p, mode) {
    this.entries.get(p).mode = mode;
    this.touch(p);
  }

  chown(p, { uid, gid } = {}) {
    const e = this.entries.get(p);
    if (uid !== undefined) e.uid = uid;
    if (gid !== undefined) e.gid = gid;
    e.ctime += 1;
  }

  grantAcl(p) {
    this.entries.get(p).writable = true;
    this.entries.get(p).ctime += 1;
  }

  swapToSymlink(p) {
    const e = this.entries.get(p);
    e.kind = "symlink";
    e.ino = this.ino++;
  }

  replaceIdentical(p) {
    this.entries.get(p).ino = this.ino++;
  }

  delete(p) {
    this.entries.delete(p);
  }

  addSibling(directory) {
    this.add(`${directory}/unrelated-app`, { kind: "dir", uid: 501, mode: 0o755, writable: true });
    this.files.set(directory, Buffer.concat([this.files.get(directory) || Buffer.alloc(0), Buffer.alloc(64)]));
    this.touch(directory);
  }

  rewrite(p, data) {
    this.files.set(p, Buffer.from(data));
    this.touch(p);
  }

  inputs(env = {}) {
    return {
      env, profilePath: PROFILE, policyFile: POLICY, buildRootDir: BUILD, repoRootSentinel: SENTINEL,
      provider: this, meta: this, platform: "darwin",
    };
  }
}

class FakeServer {
  constructor({ identity = IDENTITY, onLog = null } = {}) {
    this.identity = identity;
    this.identities = [];
    this.log = [];
    this.connects = [];
    this.clients = [];
    this.failConnect = false;
    this.failSql = null;
    this.onLog = onLog;
  }

  nextIdentity() {
    return this.identities.length ? this.identities.shift() : this.identity;
  }

  record(number, sql) {
    this.log.push([number, sql]);
    if (this.onLog) this.onLog(number, sql);
  }

  statements(number = null) {
    return this.log.filter(([n]) => number === null || n === number).map(([, sql]) => sql);
  }
}

/** A pg Client class for `new Pool({ Client })`: logs statements, answers identity, never touches a socket. */
function makeFakeClient(server) {
  return class FakeClient extends EventEmitter {
    constructor(options) {
      super();
      this.options = options;
      this._queryable = false;
      this._ending = false;
      this.number = 0;
      this.identity = null;
      server.clients.push(this);
    }

    connect(callback) {
      const keys = Object.keys(this.options).filter((k) => k !== "password" && this.options[k] !== undefined).sort();
      server.connects.push(keys);
      if (server.failConnect) {
        const error = new Error("connect ECONNREFUSED 192.0.2.1:5432");
        error.code = "ECONNREFUSED";
        setImmediate(callback, error);
        return;
      }
      this.number = server.connects.length;
      this.identity = server.nextIdentity();
      this._queryable = true;
      setImmediate(callback);
    }

    query(config, values, callback) {
      let cb = callback;
      if (typeof values === "function") cb = values;
      const text = typeof config === "string" ? config : config.text;
      const arrayMode = typeof config === "object" && config.rowMode === "array";
      let error = null;
      let result = null;
      if (!this._queryable) {
        error = new Error("Client was closed and is not queryable");
      } else {
        server.record(this.number, text);
        if (server.failSql && text.toLowerCase().includes(server.failSql)) {
          error = new Error("terminating connection due to administrator command");
          error.code = "57P01";
        } else if (text.startsWith("SELECT current_database()")) {
          const row = this.identity;
          result = { rows: [arrayMode ? row : { current_database: row[0], current_user: row[1], host: row[2], inet_server_port: row[3] }] };
        } else {
          result = { rows: [] };
        }
      }
      if (cb) {
        setImmediate(() => cb(error, error ? undefined : result));
        return undefined;
      }
      return error ? Promise.reject(error) : Promise.resolve(result);
    }

    end(callback) {
      this._ending = true;
      this._queryable = false;
      if (callback) {
        setImmediate(callback);
        return undefined;
      }
      return Promise.resolve();
    }

    ref() {}

    unref() {}
  };
}

module.exports = {
  BUILD, FakeServer, IDENTITY, LifecycleProvider, MARKERS, POLICY, PROFILE, SENTINEL, SYN_PW,
  loadFixture, makeFakeClient, profileText,
};
