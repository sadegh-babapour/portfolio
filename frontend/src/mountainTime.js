import navigation from "../../content/navigation.json" with { type: "json" };

// Shared with the NiceGUI header (app/components/navbar.py) via content/navigation.json.
const { theme: THEME } = navigation;

export const MOUNTAIN_TIME_ZONE = THEME.time_zone;
export const THEME_MODE_STORAGE_KEY = THEME.mode_storage_key;
export const RESOLVED_THEME_STORAGE_KEY = THEME.resolved_storage_key;

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
  return hour >= THEME.light_from_hour && hour < THEME.dark_from_hour ? "light" : "dark";
}

export function resolveTheme(mode, date = new Date()) {
  return mode === "light" || mode === "dark" ? mode : automaticTheme(date);
}

export function formatMountainClock(date = new Date()) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: MOUNTAIN_TIME_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
}

export function nextThemeMode(mode) {
  if (mode === "auto") return "light";
  if (mode === "light") return "dark";
  return "auto";
}
