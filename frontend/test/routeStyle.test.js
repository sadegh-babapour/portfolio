import assert from "node:assert/strict";
import test from "node:test";

import { routeColor } from "../src/routeStyle.js";


test("corridors and route lines resolve the same route color", () => {
  assert.equal(routeColor({ route_short_name: "300" }), "#b45309");
  assert.equal(routeColor({ route_short_name: "MP" }), "#9333ea");
  assert.equal(routeColor({ route_mode: "brt" }), "#7c3aed");
  assert.equal(routeColor({ route_mode: "bus" }), "#2563eb");
});
