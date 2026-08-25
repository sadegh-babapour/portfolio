import assert from "node:assert/strict";
import test from "node:test";

import { shapeSegmentToStop } from "../src/routeGeometry.js";


test("selected corridor follows ordered shape vertices instead of a direct stop line", () => {
  const segment = shapeSegmentToStop(
    [
      { shape_pt_lat: 51, shape_pt_lon: -114 },
      { shape_pt_lat: 51, shape_pt_lon: -113.99 },
      { shape_pt_lat: 51.01, shape_pt_lon: -113.99 },
      { shape_pt_lat: 51.01, shape_pt_lon: -113.98 },
    ],
    { lat: 51, lon: -113.999 },
    { stop_lat: 51.01, stop_lon: -113.981 },
  );

  assert.deepEqual(segment.slice(1, -1), [
    [51, -113.99],
    [51.01, -113.99],
  ]);
  assert.ok(segment.length >= 4);
});

test("missing shape or stop coordinates produces no invented corridor", () => {
  assert.deepEqual(shapeSegmentToStop([], { lat: 51, lon: -114 }, {}), []);
});
