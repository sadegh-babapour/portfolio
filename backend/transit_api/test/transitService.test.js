const test = require("node:test");
const assert = require("node:assert/strict");

const {
  getVehicles,
  getRoutePaths,
  getVehicleHistory,
  getVehicleContext,
  getVehicleAlerts,
} = require("../services/transitService");

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

test("featured vehicles use the configured route allowlist", async () => {
  const rows = [{ vehicle_id: "8305", route_short_name: "300" }];
  const pool = poolReturning(rows);

  assert.deepEqual(await getVehicles(pool, "featured"), rows);
  assert.deepEqual(pool.calls[0].params, [["300", "MP", "MO", "23", "57"]]);
  assert.match(pool.calls[0].sql, /route_short_name = any\(\$1\)/);
});

test("route paths group ordered shape points by route", async () => {
  const pool = poolReturning([
    {
      route_short_name: "300",
      route_long_name: "Airport",
      route_mode: "brt",
      shape_id: "shape-a",
      shape_pt_lat: 51.1,
      shape_pt_lon: -114.1,
    },
    {
      route_short_name: "300",
      route_long_name: "Airport",
      route_mode: "brt",
      shape_id: "shape-a",
      shape_pt_lat: 51.2,
      shape_pt_lon: -114.2,
    },
  ]);

  const result = await getRoutePaths(pool, "all", "300");

  assert.deepEqual(pool.calls[0].params, [["300"]]);
  assert.deepEqual(result, [
    {
      route_short_name: "300",
      route_long_name: "Airport",
      route_mode: "brt",
      shape_id: "shape-a",
      positions: [[51.1, -114.1], [51.2, -114.2]],
    },
  ]);
});

test("vehicle history applies density and window parameters and groups observations", async () => {
  const pool = poolReturning([
    {
      vehicle_id: "v1",
      trip_id: "t1",
      route_short_name: "23",
      route_long_name: "52 St E",
      route_category: "Regular",
      trip_headsign: "North",
      route_mode: "bus",
      vehicle_timestamp: "2026-08-03T04:00:00Z",
      lat: 51.0,
      lon: -114.0,
    },
    {
      vehicle_id: "v1",
      trip_id: "t1",
      route_short_name: "23",
      route_long_name: "52 St E",
      route_category: "Regular",
      trip_headsign: "North",
      route_mode: "bus",
      vehicle_timestamp: "2026-08-03T04:00:30Z",
      lat: 51.01,
      lon: -114.01,
    },
  ]);

  const result = await getVehicleHistory(pool, "bus", "2", 15);

  assert.deepEqual(pool.calls[0].params, [2, 15]);
  assert.match(pool.calls[0].sql, /route_mode = 'bus'/);
  assert.deepEqual(result[0].observations, [
    { vehicle_timestamp: "2026-08-03T04:00:00Z", lat: 51.0, lon: -114.0 },
    { vehicle_timestamp: "2026-08-03T04:00:30Z", lat: 51.01, lon: -114.01 },
  ]);
});

test("missing vehicle context returns null", async () => {
  const pool = poolReturning([]);

  assert.equal(await getVehicleContext(pool, "missing"), null);
  assert.deepEqual(pool.calls[0].params, ["missing"]);
});

test("vehicle alerts require a matching active alert", async () => {
  const pool = poolReturning([]);

  assert.deepEqual(await getVehicleAlerts(pool, "8305"), []);
  assert.match(pool.calls[0].sql, /join transit\.v_active_alerts a/);
  assert.doesNotMatch(pool.calls[0].sql, /left join transit\.v_active_alerts a/);
});
