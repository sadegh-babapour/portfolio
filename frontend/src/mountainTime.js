export const MOUNTAIN_TIME_ZONE = "America/Edmonton";
export const THEME_MODE_STORAGE_KEY = "portfolio-theme-mode";
export const RESOLVED_THEME_STORAGE_KEY = "portfolio-theme";

export function mountainHour(date = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: MOUNTAIN_TIME_ZONE,
    hour: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  return Number(parts.find((part) => part.type === "hour")?.value ?? 0);
}

export function automaticTheme(date = new Date()) {
  const hour = mountainHour(date);
  return hour >= 7 && hour < 19 ? "light" : "dark";
}

export function resolveTheme(mode, date = new Date()) {
  return mode === "light" || mode === "dark" ? mode : automaticTheme(date);
}

export function formatMountainClock(date = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: MOUNTAIN_TIME_ZONE,
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short",
  }).format(date);
}

export function nextThemeMode(mode) {
  if (mode === "auto") return "light";
  if (mode === "light") return "dark";
  return "auto";
}
