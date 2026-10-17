"use strict";
/**
 * Write the Railway build attestation for the transit-api build root (design §3.4).
 *
 * The build root is backend/transit_api (the service's Railway root). The marker is
 * `.bizqlab-build-attestation.json` directly inside it, bound to this Railway service,
 * environment and (when Railway supplies it) commit. It holds no secrets and is
 * ignored by Git. Mirrors ops/write_build_attestation.py.
 *
 * Inert until a Railway build command calls it (see the M1 deployment checklist). It
 * never runs on a workstation: it requires the Railway build identifiers and refuses
 * where the local profile or approval policy exists.
 *
 * Exit 0: written, or an existing marker for exactly this service/environment/commit
 * was kept. Exit 2: refused; nothing was written and an existing marker was not changed.
 */
const fs = require("node:fs");
const path = require("node:path");

const rt = require("../config/runtimeEnv");

const ID_KEYS = ["RAILWAY_SERVICE_ID", "RAILWAY_ENVIRONMENT_ID"];
const ID_RE = /^[A-Za-z0-9-]{1,64}$/;
const COMMIT_RE = /^[0-9a-f]{40}$/;

class AttestationRefused extends Error {
  constructor(code, key = null) {
    super(rt.formatError(code, key));
    this.name = "AttestationRefused";
    this.code = code;
    this.key = key;
  }
}

/** The document for this build, or AttestationRefused naming the key at fault (never a value). */
function attestationDocument(env, now, buildRoot = rt.BUILD_ROOT) {
  for (const key of ID_KEYS) {
    const value = env[key];
    if (!value) throw new AttestationRefused("missing_build_identifier", key);
    if (!ID_RE.test(value)) throw new AttestationRefused("invalid_build_identifier", key);
  }
  const commit = env.RAILWAY_GIT_COMMIT_SHA || null;
  if (commit !== null && !COMMIT_RE.test(commit)) throw new AttestationRefused("invalid_build_identifier", "RAILWAY_GIT_COMMIT_SHA");
  return {
    schema: 1, kind: "bizqlab-railway-build", build_root: buildRoot,
    railway_service_id: env.RAILWAY_SERVICE_ID, railway_environment_id: env.RAILWAY_ENVIRONMENT_ID,
    git_commit: commit, generated_at: now.toISOString().replace(/\.\d{3}Z$/, "Z"),
  };
}

const render = (doc) => Buffer.from(`${JSON.stringify(doc)}\n`, "utf8");

/** An existing marker is kept only if it is this exact build's document (generated_at aside). */
function sameBuild(bytes, doc) {
  let existing;
  try {
    existing = rt.parseStrictJson(bytes);
  } catch {
    return false;
  }
  if (existing === null || typeof existing !== "object" || Array.isArray(existing)) return false;
  const keys = Object.keys(existing).sort();
  if (JSON.stringify(keys) !== JSON.stringify(Object.keys(doc).sort())) return false;
  return Object.keys(doc).every((k) => k === "generated_at" || existing[k] === doc[k]);
}

/** W1/W2 of design §3.1 by lstat: the approval policy or the local profile exists. */
function workstation() {
  let policy = null;
  try {
    policy = rt.policyPath();
  } catch {
    policy = null;
  }
  return [policy !== null && rt.pathExistsNoFollow(policy), rt.pathExistsNoFollow(rt.PROFILE_PATH)];
}

/** Write or keep the marker under root. Returns "written" or "unchanged". */
function writeAttestation(root, env, { now = new Date(), isWorkstation = workstation, buildRoot = rt.BUILD_ROOT } = {}) {
  const doc = attestationDocument(env, now, buildRoot);
  if (isWorkstation().some(Boolean)) throw new AttestationRefused("workstation_build_refused");
  let reason = null;
  let bytes = null;
  try {
    [bytes] = rt.readInRoot(root, rt.ATTESTATION_FILENAME, rt.ATTESTATION_MAX_BYTES);
  } catch (error) {
    reason = error instanceof rt.FileReadError ? error.reason : "unreadable";
  }
  let outcome;
  if (reason === null) {
    if (!sameBuild(bytes, doc)) throw new AttestationRefused("existing_marker_mismatch");
    outcome = "unchanged";
  } else if (reason === "missing") {
    const flags = fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_NOFOLLOW;
    const fd = fs.openSync(path.join(root, rt.ATTESTATION_FILENAME), flags, 0o444);
    try {
      fs.writeSync(fd, render(doc));
      fs.fsyncSync(fd);
    } finally {
      fs.closeSync(fd);
    }
    outcome = "written";
  } else {
    throw new AttestationRefused(`existing_marker_${reason}`);
  }
  const status = rt.readAttestation(root, { buildRoot, env });
  if (status !== "valid") throw new AttestationRefused(`self_check_${status.replace(":", "_")}`);
  return outcome;
}

function main() {
  try {
    const outcome = writeAttestation(rt.BUILD_ROOT_DIR, process.env);
    console.log(`bizqlab build attestation ${outcome}: build_root=${rt.BUILD_ROOT}, file=${rt.ATTESTATION_FILENAME}`);
    return 0;
  } catch (error) {
    const message = error instanceof AttestationRefused || error instanceof rt.RuntimeConfigError
      ? error.message : (error && error.code) || "unexpected_error";
    console.error(`BIZQLAB ATTESTATION REFUSED (build_root=${rt.BUILD_ROOT}): ${message}`);
    return 2;
  }
}

if (require.main === module) process.exitCode = main();

module.exports = { AttestationRefused, attestationDocument, render, writeAttestation };
