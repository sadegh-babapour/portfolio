import assert from "node:assert/strict";
import test from "node:test";

import { createRouteSnapper } from "../src/routeSnapping.js";
import { computePlaybackVehicles, distanceMeters } from "../src/transitPlayback.js";


// Synthetic streets near downtown Calgary, laid out in metres east/north of a corner.
const ORIGIN = { lat: 51.05, lon: -114.07 };
const METERS_PER_DEGREE_LAT = 111_132;
const METERS_PER_DEGREE_LON = METERS_PER_DEGREE_LAT * Math.cos((51.05 * Math.PI) / 180);
const at = (east, north) => [
  ORIGIN.lat + north / METERS_PER_DEGREE_LAT,
  ORIGIN.lon + east / METERS_PER_DEGREE_LON,
];
const report = (east, north, second) => {
  const [lat, lon] = at(east, north);
  return { lat, lon, vehicle_timestamp: new Date(Date.UTC(2026, 9, 21, 20, 0, second)).toISOString() };
};
const metresFrom = (point, east, north) => {
  const [lat, lon] = at(east, north);
  return distanceMeters(point.lat, point.lon, lat, lon);
};

// Route 1 runs east 400 m along a street, then turns north for 400 m.
const corner = { route_short_name: "1", shape_id: "c", positions: [at(0, 0), at(400, 0), at(400, 400)] };
const bus = { vehicle_id: "v1", trip_id: "t1", route_short_name: "1" };


test("a bus turning a corner follows the street instead of cutting across", () => {
  const snapper = createRouteSnapper([corner]);
  const halfway = snapper.position(bus, report(200, 0, 0), report(400, 200, 40), 0.5);

  // 400 m along the road from (200, 0) to (400, 200): halfway is the corner itself.
  assert.ok(metresFrom(halfway, 400, 0) < 1, `at the corner, got ${metresFrom(halfway, 400, 0)} m away`);
  // The straight line would put the bus 71 m inside the block.
  assert.ok(metresFrom({ lat: at(300, 100)[0], lon: at(300, 100)[1] }, 400, 0) > 140);
});

test("reports a few metres off the street are pulled onto it", () => {
  const snapper = createRouteSnapper([corner]);
  const point = snapper.position(bus, report(100, 12, 0), report(300, -9, 20), 0.5);

  assert.ok(metresFrom(point, 200, 0) < 1);
});

test("reports that do not fit the route fall back to the straight line", () => {
  const snapper = createRouteSnapper([corner]);

  assert.equal(snapper.position(bus, report(100, 80, 0), report(300, 0, 20), 0.5), null, "80 m off the street");
  assert.equal(snapper.position({ ...bus, route_short_name: "99" }, report(100, 0, 0), report(300, 0, 20), 0.5), null);
});

test("a report sits in the same place for the pair before it and the pair after it", () => {
  const snapper = createRouteSnapper([corner]);
  const [first, shared, last] = [report(100, 20, 0), report(380, -25, 40), report(410, 300, 80)];
  const end = snapper.position(bus, first, shared, 1);
  const start = snapper.position(bus, shared, last, 0);

  assert.ok(distanceMeters(end.lat, end.lon, start.lat, start.lon) < 0.5);
});

test("on an out-and-back route the bus stays on its own pass", () => {
  // East 600 m, then back west 600 m on a street 20 m to the north.
  const outAndBack = {
    route_short_name: "2",
    shape_id: "o",
    positions: [at(0, 0), at(600, 0), at(600, 20), at(0, 20)],
  };
  const snapper = createRouteSnapper([outAndBack]);
  const point = snapper.position({ ...bus, route_short_name: "2" }, report(200, 0, 0), report(300, 0, 15), 0.5);

  assert.ok(metresFrom(point, 250, 0) < 1, "does not detour round the far end");
});

test("heading follows the street in the direction of travel", () => {
  const snapper = createRouteSnapper([corner]);
  const east = snapper.position(bus, report(100, 0, 0), report(300, 0, 20), 0.5);
  const north = snapper.position(bus, report(400, 100, 0), report(400, 300, 20), 0.5);
  const west = snapper.position(bus, report(300, 0, 0), report(100, 0, 20), 0.5);

  assert.ok(Math.abs(east.heading - 90) < 1);
  assert.ok(north.heading < 1 || north.heading > 359);
  assert.ok(Math.abs(west.heading - 270) < 1);
});

test("playback uses the road position for moving buses only", () => {
  const snapper = createRouteSnapper([corner]);
  const rows = [
    { ...bus, observations: [report(200, 0, 0), report(400, 200, 40)] },
    { ...bus, vehicle_id: "v2", observations: [report(200, 0, 0), report(205, 0, 40)] },
  ];
  const [moving, stopped] = computePlaybackVehicles(
    rows,
    Date.parse(report(0, 0, 20).vehicle_timestamp),
    { snapper },
  );

  assert.ok(metresFrom(moving, 400, 0) < 1);
  assert.equal(stopped.isStopped, true);
  assert.ok(metresFrom(stopped, 202.5, 0) < 0.5, "a stopped bus keeps the plain interpolation");
});

test("a bus on the other direction's street follows its own trip shape", () => {
  // The drawn route goes north on one street; this bus's trip comes south on a
  // parallel one-way street 100 m east, which the route shape does not cover.
  const northbound = { route_short_name: "3", shape_id: "north", positions: [at(0, 0), at(0, 800)] };
  const southbound = { shape_id: "south", positions: [at(100, 800), at(100, 400), at(100, 0)] };
  const southBus = { vehicle_id: "v3", trip_id: "t3", route_short_name: "3", shape_id: "south" };
  const from = report(103, 600, 0);
  const to = report(97, 200, 40);

  assert.equal(createRouteSnapper([northbound]).position(southBus, from, to, 0.5), null);
  const point = createRouteSnapper([northbound], { tripShapes: [southbound] }).position(southBus, from, to, 0.5);
  assert.ok(metresFrom(point, 100, 400) < 1);
  assert.ok(Math.abs(point.heading - 180) < 1);
});

test("when the trip shape does not fit, the route shape is still tried", () => {
  const wrongTripShape = { shape_id: "far", positions: [at(1000, 0), at(1000, 800)] };
  const snapper = createRouteSnapper([corner], { tripShapes: [wrongTripShape] });
  const point = snapper.position({ ...bus, shape_id: "far" }, report(100, 0, 0), report(300, 0, 20), 0.5);

  assert.ok(metresFrom(point, 200, 0) < 1);
});

test("a road route that would need an impossible speed is not used", () => {
  // A U-shaped trip: north 300 m, east 400 m, south 300 m. Its two ends are 400 m apart
  // in a straight line but 1,000 m by road.
  const uTurn = { shape_id: "u", positions: [at(0, 0), at(0, 300), at(400, 300), at(400, 0)] };
  const snapper = createRouteSnapper([], { tripShapes: [uTurn] });
  const uBus = { vehicle_id: "v4", trip_id: "t4", route_short_name: "4", shape_id: "u" };

  assert.equal(snapper.position(uBus, report(0, 0, 0), report(400, 0, 20), 0.5), null, "1 km in 20 s is 50 m/s");
  const plausible = snapper.position(uBus, report(0, 0, 0), report(400, 0, 60), 0.5);
  assert.ok(metresFrom(plausible, 200, 300) < 1, "1 km in 60 s follows the road");
});
