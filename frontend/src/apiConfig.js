export const PRODUCTION_TRANSIT_API_BASE =
  "https://transit-api-production.up.railway.app/api";

// Build modes and where their API target comes from. There is no default: a missing
// or invalid target fails the build (vite.config.js) or the page load, and never
// falls back to production or to NiceGUI's unrelated same-origin /api namespace.
//   development - VITE_TRANSIT_API_BASE_URL from frontend/.env.development.local
//   preview     - VITE_TRANSIT_API_BASE_URL naming the isolated preview API (https)
//   release     - the production endpoint above, explicitly
export const BUILD_MODES = ["development", "preview", "release"];

const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

export class TransitApiConfigError extends Error {
  constructor(message) {
    super(`Transit API target: ${message}`);
    this.name = "TransitApiConfigError";
  }
}

/**
 * Validate and normalize an explicit API base: an absolute https URL, or http on a
 * loopback host for local development; no credentials, query or fragment.
 */
export function resolveTransitApiBase(configuredBase) {
  const text = String(configuredBase ?? "").trim();
  if (!text) {
    throw new TransitApiConfigError("VITE_TRANSIT_API_BASE_URL is required; there is no default");
  }
  let url;
  try {
    url = new URL(text);
  } catch {
    throw new TransitApiConfigError("VITE_TRANSIT_API_BASE_URL must be an absolute URL");
  }
  const loopback = LOOPBACK_HOSTS.has(url.hostname);
  if (!(url.protocol === "https:" || (url.protocol === "http:" && loopback))) {
    throw new TransitApiConfigError("VITE_TRANSIT_API_BASE_URL must use https (http only on localhost)");
  }
  if (url.username || url.password || url.search || url.hash || text.includes("?") || text.includes("#")) {
    throw new TransitApiConfigError("VITE_TRANSIT_API_BASE_URL must not carry credentials, a query or a fragment");
  }
  return `${url.origin}${url.pathname}`.replace(/\/$/, "");
}

/** The API base a build mode must embed (used by vite.config.js before building or serving). */
export function transitApiBaseForMode(mode, configuredBase) {
  const configured = String(configuredBase ?? "").trim();
  if (mode === "release") {
    if (configured && resolveTransitApiBase(configured) !== PRODUCTION_TRANSIT_API_BASE) {
      throw new TransitApiConfigError("release builds target the production API; unset VITE_TRANSIT_API_BASE_URL");
    }
    return PRODUCTION_TRANSIT_API_BASE;
  }
  if (mode === "preview") {
    const base = resolveTransitApiBase(configured);
    if (base === PRODUCTION_TRANSIT_API_BASE || !base.startsWith("https://")) {
      throw new TransitApiConfigError("preview builds need the isolated preview API over https, never production");
    }
    return base;
  }
  if (mode === "development") {
    return resolveTransitApiBase(configured);
  }
  throw new TransitApiConfigError(`unknown build mode "${mode}"; use --mode ${BUILD_MODES.join(", --mode ")}`);
}
