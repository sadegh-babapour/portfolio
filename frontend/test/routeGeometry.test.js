import assert from "node:assert/strict";
import test from "node:test";

import {
  defaultCorridorStop,
  corridorViewportPoints,
  resolveCorridorStop,
  shapeSegmentToStop,
  stopsThroughDestination,
  upcomingStopById,
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

test("a tracked stop must still be upcoming before its corridor is shown", () => {
  const stops = [{ stop_id: "next" }, { stop_id: "later" }];

  assert.equal(upcomingStopById(stops, { stop_id: "later" }), stops[1]);
  assert.equal(upcomingStopById(stops, { stop_id: "passed" }), null);
});

test("corridor viewport includes the exact bus and destination coordinates", () => {
  const points = corridorViewportPoints(
    [[51.01, -114.01], [51.02, -114.02]],
    { lat: 51, lon: -114 },
    { stop_lat: 51.03, stop_lon: -114.03 },
  );

  assert.deepEqual(points.at(-2), [51, -114]);
  assert.deepEqual(points.at(-1), [51.03, -114.03]);
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
