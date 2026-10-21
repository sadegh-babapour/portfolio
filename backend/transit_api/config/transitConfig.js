const FEATURED_ROUTES = ["300", "MP", "MO", "23", "57"];

// Browser origins allowed to read the API (CORS). The map is served from bizqlab.com;
// loopback covers local development. Other sites' pages get no CORS header, so the
// browser blocks them. This does not stop non-browser clients.
const ALLOWED_ORIGINS = new Set(["https://bizqlab.com", "https://www.bizqlab.com"]);
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

function isAllowedOrigin(origin) {
  if (ALLOWED_ORIGINS.has(origin)) return true;
  try {
    const url = new URL(origin);
    return url.protocol === "http:" && LOOPBACK_HOSTS.has(url.hostname);
  } catch {
    return false;
  }
}

module.exports = {
  FEATURED_ROUTES,
  isAllowedOrigin,
};
