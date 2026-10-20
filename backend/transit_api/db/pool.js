const { Pool } = require("pg");

const { RuntimeConfigError } = require("../config/runtimeEnv");
const runtime = require("../config/runtimeState");

const PURPOSE = "transit-api";

/**
 * The transit API pool. The runtime gate runs before any pool exists (design §7).
 * Development: an explicit-target pool that verifies identity on every new client
 * and checks the state before every query (config/runtimeState.js). Attested
 * production: today's configuration, unchanged.
 */
function createPool({ PoolClass = Pool, exit = (code) => process.exit(code) } = {}) {
  const state = runtime.verifyRuntime(PURPOSE);
  if (state.mode === "production") {
    return new PoolClass({
      host: process.env.PGHOST || "localhost",
      port: Number(process.env.PGPORT || 5432),
      database: process.env.PGDATABASE,
      user: process.env.PGUSER,
      password: process.env.PGPASSWORD,
    });
  }
  const pool = runtime.createDevelopmentPool(state, PoolClass);
  let ending = null;
  runtime.onRevoke((trigger) => {
    console.error(`BIZQLAB RUNTIME REVOKED (${PURPOSE}): ${trigger}; ending the pool`);
    if (ending === null) ending = pool.end().catch(() => undefined);
    ending.finally(() => exit(1));
  });
  return pool;
}

/** createPool for the server entry point: a refusal prints its code and exits 2 before any pool exists. */
function openPool(options = {}) {
  const exit = options.exit || ((code) => process.exit(code));
  try {
    return createPool({ ...options, exit });
  } catch (error) {
    if (!(error instanceof RuntimeConfigError)) throw error;
    console.error(`BIZQLAB RUNTIME REFUSED (${PURPOSE}): ${error.message}`);
    return exit(2);
  }
}

/**
 * Development startup probe before listen: one client is acquired, so its identity is
 * verified, then released. Production keeps today's lazy connections.
 */
async function ready(pool) {
  const state = runtime.currentState();
  if (state === null || state.mode !== "development") return;
  const client = await pool.connect();
  client.release();
}

module.exports = { createPool, openPool, ready };
