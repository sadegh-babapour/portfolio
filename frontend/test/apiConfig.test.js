import test from "node:test";
import assert from "node:assert/strict";

import {
  PRODUCTION_TRANSIT_API_BASE,
  resolveTransitApiBase,
} from "../src/apiConfig.js";


test("production API default cannot fall back to the NiceGUI origin", () => {
  assert.equal(
    resolveTransitApiBase(undefined),
    "https://transit-api-production.up.railway.app/api",
  );
  assert.equal(resolveTransitApiBase(""), PRODUCTION_TRANSIT_API_BASE);
  assert.notEqual(resolveTransitApiBase(undefined), "/api");
});

test("configured development API is normalized without changing its host", () => {
  assert.equal(
    resolveTransitApiBase("http://localhost:4000/api/"),
    "http://localhost:4000/api",
  );
});
