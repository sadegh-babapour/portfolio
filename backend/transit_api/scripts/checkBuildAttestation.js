"use strict";
/**
 * Classify the transit-api build attestation for the current environment (design §3.4).
 * Read-only and connects to nothing. Prints a non-secret classification and the
 * binding variables' presence (never their values). Exit 0 only when valid.
 * Mirrors ops/check_build_attestation.py.
 */
const rt = require("../config/runtimeEnv");

function main(env = process.env, root = rt.BUILD_ROOT_DIR) {
  const status = rt.readAttestation(root, { buildRoot: rt.BUILD_ROOT, env });
  const present = ["BIZQLAB_RUNTIME", ...rt.MARKER_KEYS, "RAILWAY_GIT_COMMIT_SHA"]
    .map((key) => `${key}=${env[key] ? "set" : "unset"}`).join(", ");
  console.log(`attestation: ${status} (build_root=${rt.BUILD_ROOT}, file=${rt.ATTESTATION_FILENAME}; ${present})`);
  return status === "valid" ? 0 : 1;
}

if (require.main === module) process.exitCode = main();

module.exports = { main };
