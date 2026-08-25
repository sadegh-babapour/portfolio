import assert from "node:assert/strict";
import test from "node:test";

import {
  defaultCorridorStop,
  resolveCorridorStop,
  shapeSegmentToStop,
  stopsThroughDestination,
} from "../src/routeGeometry.js";


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

test("the default corridor runs through the next three stops", () => {
  const stops = [
    { stop_id: "1" },
    { stop_id: "2" },
    { stop_id: "3" },
    { stop_id: "4" },
  ];

  assert.equal(defaultCorridorStop(stops).stop_id, "3");
  assert.deepEqual(stopsThroughDestination(stops, defaultCorridorStop(stops)), stops.slice(0, 3));
});

test("a tracked stop keeps every intermediate stop in the corridor", () => {
  const stops = [
    { stop_id: "1" },
    { stop_id: "2" },
    { stop_id: "3" },
    { stop_id: "4" },
  ];
  const requested = { stop_id: "4", stop_name: "Tracked stop" };
  const resolved = resolveCorridorStop(stops, requested);

  assert.equal(resolved, stops[3]);
  assert.deepEqual(stopsThroughDestination(stops, resolved), stops);
});
