"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const { simplifyPath } = require("../services/shapeGeometry");
const { getShapes, getVehicleHistory, getRoutePaths } = require("../services/transitService");

function poolReturning(rows) {
  const calls = [];
  return {
    calls,
    async query(sql, params) {
      calls.push({ sql, params });
      return { rows };
    },
  };
}

// 1 m north at Calgary is about 0.000009 degrees of latitude.
const METRE = 1 / 111_132;

test("simplification drops points on a straight street and keeps corners", () => {
  const street = Array.from({ length: 101 }, (_, index) => [51.05, -114.07 + index * 0.0001]);
  const corner = [...street, [51.05 + 300 * METRE, -114.06]];
  const simplified = simplifyPath(corner);

  assert.deepEqual(simplified, [[51.05, -114.07], [51.05, -114.06], [51.0527, -114.06]]);
});

test("simplification keeps deviations over 2 m and rounds to about 1 m", () => {
  const bend = [[51.05, -114.07], [51.05 + 3 * METRE, -114.065], [51.05, -114.06]];
  const wobble = [[51.05, -114.07], [51.05 + 1 * METRE, -114.065], [51.05, -114.06]];

  assert.equal(simplifyPath(bend).length, 3);
  assert.equal(simplifyPath(wobble).length, 2);
  assert.deepEqual(simplifyPath([[51.0500004, -114.0700004]]), [[51.05, -114.07]]);
});

test("shapes are looked up by bounded, de-duplicated ids and grouped in order", async () => {
  const pool = poolReturning([
    { shape_id: "a", shape_pt_lat: 51.0, shape_pt_lon: -114.0 },
    { shape_id: "a", shape_pt_lat: 51.01, shape_pt_lon: -114.0 },
    { shape_id: "b", shape_pt_lat: 51.0, shape_pt_lon: -114.1 },
    { shape_id: "b", shape_pt_lat: 51.0, shape_pt_lon: -114.11 },
  ]);
  const ids = ["a", "b", "a", " ", "x".repeat(65), ...Array.from({ length: 60 }, (_, index) => `s${index}`)];

  const shapes = await getShapes(pool, ids.join(","));

  assert.equal(pool.calls.length, 1);
  assert.match(pool.calls[0].sql, /where shape_id = any\(\$1\)/);
  assert.equal(pool.calls[0].params[0].length, 50);
  assert.deepEqual(pool.calls[0].params[0].slice(0, 3), ["a", "b", "s0"]);
  assert.deepEqual(shapes, [
    { shape_id: "a", positions: [[51.0, -114.0], [51.01, -114.0]] },
    { shape_id: "b", positions: [[51.0, -114.1], [51.0, -114.11]] },
  ]);
});

test("no ids means no query", async () => {
  const pool = poolReturning([]);
  assert.deepEqual(await getShapes(pool, undefined), []);
  assert.deepEqual(await getShapes(pool, " , "), []);
  assert.equal(pool.calls.length, 0);
});

test("vehicle history tells the map which shape each bus follows", async () => {
  const pool = poolReturning([
    { vehicle_id: "v1", trip_id: "t1", route_short_name: "3", shape_id: "s3", vehicle_timestamp: "t", lat: 51, lon: -114 },
    { vehicle_id: "v2", trip_id: "t2", route_short_name: "4", vehicle_timestamp: "t", lat: 51, lon: -114 },
  ]);
  const history = await getVehicleHistory(pool, "all", "all", 4);

  assert.match(pool.calls[0].sql, /ev\.shape_id/);
  assert.equal(history[0].shape_id, "s3");
  assert.equal(history[1].shape_id, null);
});

test("route paths are simplified", async () => {
  const rows = Array.from({ length: 50 }, (_, index) => ({
    route_short_name: "1", route_long_name: "Line", route_mode: "bus", shape_id: "s1",
    shape_pt_sequence: index, shape_pt_lat: 51.05, shape_pt_lon: -114.07 + index * 0.0001,
  }));
  const [route] = await getRoutePaths(poolReturning(rows), "all");

  assert.deepEqual(route.positions, [[51.05, -114.07], [51.05, -114.0651]]);
});

test("the shapes endpoint lets browsers cache for a day", () => {
  const server = fs.readFileSync(path.join(__dirname, "..", "server.js"), "utf8");
  assert.match(server, /app\.get\("\/api\/shapes"[\s\S]*?Cache-Control", "public, max-age=86400"/);
});
