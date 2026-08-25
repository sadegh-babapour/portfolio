export const SHORT_MAP_TAP_MS = 350;

export function isShortBlankMapTap({ durationMs, moved, interactiveTarget }) {
  return Number.isFinite(durationMs)
    && durationMs <= SHORT_MAP_TAP_MS
    && moved !== true
    && interactiveTarget !== true;
}
