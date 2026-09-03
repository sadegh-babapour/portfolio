export function usableCachedLocation(location) {
  return Array.isArray(location)
    && location.length === 2
    && location.every(Number.isFinite)
    ? location
    : null;
}
