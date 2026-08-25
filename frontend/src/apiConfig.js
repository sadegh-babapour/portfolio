export const PRODUCTION_TRANSIT_API_BASE =
  "https://transit-api-production.up.railway.app/api";


export function resolveTransitApiBase(configuredBase) {
  const normalized = String(configuredBase || "").trim().replace(/\/$/, "");
  return normalized || PRODUCTION_TRANSIT_API_BASE;
}
