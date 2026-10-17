import test from "node:test";
import assert from "node:assert/strict";

import {
  PRODUCTION_TRANSIT_API_BASE,
  TransitApiConfigError,
  resolveTransitApiBase,
  transitApiBaseForMode,
} from "../src/apiConfig.js";


test("a missing API target fails clearly instead of choosing production or /api", () => {
  for (const missing of [undefined, null, "", "   "]) {
    assert.throws(() => resolveTransitApiBase(missing), TransitApiConfigError);
  }
  assert.throws(() => resolveTransitApiBase("/api"), /absolute URL/);
});

test("invalid API targets are refused", () => {
  for (const value of [
    "http://transit.example/api",
    "ftp://localhost/api",
    "https://user:pw@transit.example/api",
    "https://transit.example/api?x=1",
    "https://transit.example/api#x",
    "localhost:4000/api",
  ]) {
    assert.throws(() => resolveTransitApiBase(value), TransitApiConfigError, value);
  }
});

test("configured development API is normalized without changing its host", () => {
  assert.equal(resolveTransitApiBase("http://localhost:4000/api/"), "http://localhost:4000/api");
  assert.equal(resolveTransitApiBase("http://127.0.0.1:4000/api"), "http://127.0.0.1:4000/api");
  assert.equal(transitApiBaseForMode("development", "http://localhost:4000/api"), "http://localhost:4000/api");
  assert.throws(() => transitApiBaseForMode("development", undefined), TransitApiConfigError);
});

test("preview builds require the isolated https API and never production", () => {
  assert.equal(transitApiBaseForMode("preview", "https://transit-api-preview.example/api/"),
    "https://transit-api-preview.example/api");
  assert.throws(() => transitApiBaseForMode("preview", undefined), TransitApiConfigError);
  assert.throws(() => transitApiBaseForMode("preview", PRODUCTION_TRANSIT_API_BASE), /never production/);
  assert.throws(() => transitApiBaseForMode("preview", "http://localhost:4000/api"), /https/);
});

test("release builds target the existing production endpoint explicitly", () => {
  assert.equal(PRODUCTION_TRANSIT_API_BASE, "https://transit-api-production.up.railway.app/api");
  assert.equal(transitApiBaseForMode("release", undefined), PRODUCTION_TRANSIT_API_BASE);
  assert.equal(transitApiBaseForMode("release", `${PRODUCTION_TRANSIT_API_BASE}/`), PRODUCTION_TRANSIT_API_BASE);
  assert.throws(() => transitApiBaseForMode("release", "https://transit-api-preview.example/api"), /production API/);
});

test("Vite's implicit production mode is refused, so no build selects a target by default", () => {
  for (const mode of ["production", "staging", ""]) {
    assert.throws(() => transitApiBaseForMode(mode, PRODUCTION_TRANSIT_API_BASE), /unknown build mode/);
  }
});
