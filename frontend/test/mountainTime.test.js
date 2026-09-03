import assert from "node:assert/strict";
import test from "node:test";

import {
  automaticTheme,
  formatMountainClock,
  nextThemeMode,
  resolveTheme,
} from "../src/mountainTime.js";

test("automatic theme follows Calgary daytime instead of the browser timezone", () => {
  assert.equal(automaticTheme(new Date("2026-09-02T14:00:00Z")), "light");
  assert.equal(automaticTheme(new Date("2026-09-02T03:00:00Z")), "dark");
});

test("explicit theme modes override Calgary time and cycle back to automatic", () => {
  const night = new Date("2026-09-02T03:00:00Z");
  assert.equal(resolveTheme("light", night), "light");
  assert.equal(resolveTheme("dark", night), "dark");
  assert.equal(resolveTheme("auto", night), "dark");
  assert.equal(nextThemeMode("auto"), "light");
  assert.equal(nextThemeMode("light"), "dark");
  assert.equal(nextThemeMode("dark"), "auto");
});

test("clock is explicitly formatted in Mountain Time", () => {
  const value = formatMountainClock(new Date("2026-09-02T14:05:06Z"));
  assert.match(value, /8:05/);
  assert.doesNotMatch(value, /:06/);
  assert.doesNotMatch(value, /M[DS]T/);
});
