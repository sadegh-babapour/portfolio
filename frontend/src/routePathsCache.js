// Route shapes are static GTFS (over 1 MB for all routes), so keep the last few filters'
// shapes in memory instead of downloading them again on every 30 s position refresh.
// Returning the same array also lets React skip redrawing every route line.
export function createRoutePathsCache({ maxAgeMs, maxEntries = 4 }) {
  const entries = new Map();

  return {
    get(url, nowMs) {
      const entry = entries.get(url);
      if (!entry || nowMs - entry.atMs > maxAgeMs) return null;
      entries.delete(url);
      entries.set(url, entry);
      return entry.paths;
    },

    set(url, paths, nowMs) {
      entries.delete(url);
      entries.set(url, { paths, atMs: nowMs });
      while (entries.size > maxEntries) entries.delete(entries.keys().next().value);
    },
  };
}
