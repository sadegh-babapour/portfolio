const test = require("node:test");
const assert = require("node:assert/strict");

const {
  getTransitHealth,
  getVehicles,
  getRoutePaths,
  getVehicleHistory,
  getVehicleContext,
  getVehicleAlerts,
  searchRoutes,
  searchStops,
  getStopArrivals,
  getNearbyStops,
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

test("transit health distinguishes fresh and after-hours data", async () => {
  const freshPool = poolReturning([{
    checked_at: "2026-08-13T18:00:00Z",
    within_operating_hours: true,
    latest_vehicle_timestamp: "2026-08-13T17:59:30Z",
    vehicle_age_seconds: "30",
    recent_vehicle_count: "287",
    latest_trip_update_timestamp: "2026-08-13T17:59:31Z",
    latest_alert_timestamp: "2026-08-13T17:59:32Z",
  }]);
  const fresh = await getTransitHealth(freshPool);
  assert.equal(fresh.ok, true);
  assert.equal(fresh.status, "healthy");
  assert.equal(fresh.recent_vehicle_count, 287);

  const afterHoursPool = poolReturning([{
    checked_at: "2026-08-13T05:00:00Z",
    within_operating_hours: false,
    latest_vehicle_timestamp: "2026-08-13T02:58:40Z",
    vehicle_age_seconds: "7280",
    recent_vehicle_count: "0",
  }]);
  const afterHours = await getTransitHealth(afterHoursPool);
  assert.equal(afterHours.ok, true);
  assert.equal(afterHours.status, "outside_operating_hours");
});

test("transit health is degraded when vehicles are stale during operating hours", async () => {
  const pool = poolReturning([{
    within_operating_hours: true,
    latest_vehicle_timestamp: "2026-08-13T17:50:00Z",
    vehicle_age_seconds: "600",
    recent_vehicle_count: "0",
  }]);

  const health = await getTransitHealth(pool);
  assert.equal(health.ok, false);
  assert.equal(health.status, "degraded");
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

  const result = await getVehicleHistory(pool, "bus", "2", 15, "23");

  assert.deepEqual(pool.calls[0].params, [["23"], 2, 15]);
  assert.match(pool.calls[0].sql, /route_mode = 'bus'/);
  assert.match(
    pool.calls[0].sql,
    /ev\.vehicle_id = vp\.vehicle_id\s+and ev\.trip_id = vp\.trip_id/
  );
  assert.match(
    pool.calls[0].sql,
    /rp\.vehicle_id = ev\.vehicle_id\s+and rp\.trip_id = ev\.trip_id/
  );
  assert.deepEqual(result[0].observations, [
    { vehicle_timestamp: "2026-08-03T04:00:00Z", lat: 51.0, lon: -114.0 },
    { vehicle_timestamp: "2026-08-03T04:00:30Z", lat: 51.01, lon: -114.01 },
  ]);
});

test("route and stop search stay parameterized and bounded", async () => {
  const routePool = poolReturning([{ route_short_name: "23" }]);
  assert.deepEqual(await searchRoutes(routePool, " 23 "), [{ route_short_name: "23" }]);
  assert.deepEqual(routePool.calls[0].params, ["%23%", "23"]);

  const stopPool = poolReturning([{ stop_id: "1001" }]);
  assert.deepEqual(await searchStops(stopPool, " Centre "), [{ stop_id: "1001" }]);
  assert.deepEqual(stopPool.calls[0].params, ["%Centre%", "Centre"]);
});

test("stop arrivals use the requested stop and a fifteen minute window", async () => {
  const pool = poolReturning([]);
  assert.deepEqual(await getStopArrivals(pool, "1001"), []);
  assert.deepEqual(pool.calls[0].params, ["1001"]);
  assert.match(pool.calls[0].sql, /interval '15 minutes'/);
});

test("nearby stops use bounded parameterized coordinates", async () => {
  const pool = poolReturning([{ stop_id: "1001", distance_meters: 120 }]);
  const rows = await getNearbyStops(pool, 51.0447, -114.0719, 6);
  assert.equal(rows[0].distance_meters, 120);
  assert.deepEqual(pool.calls[0].params, [51.0447, -114.0719, 6]);
  assert.match(pool.calls[0].sql, /limit \$3/);
  assert.match(pool.calls[0].sql, /distance_meters/);
});

test("missing vehicle context returns null", async () => {
  const pool = poolReturning([]);

  assert.equal(await getVehicleContext(pool, "missing"), null);
  assert.deepEqual(pool.calls[0].params, ["missing"]);
  assert.match(pool.calls[0].sql, /next_stops[\s\S]*limit 3/);
  assert.doesNotMatch(pool.calls[0].sql, /previous_static_stops|previous_stops/);
});

test("vehicle alerts require a matching active alert", async () => {
  const pool = poolReturning([]);

  assert.deepEqual(await getVehicleAlerts(pool, "8305"), []);
  assert.match(pool.calls[0].sql, /join transit\.v_active_alerts a/);
  assert.match(pool.calls[0].sql, /a\.header_text/);
  assert.doesNotMatch(pool.calls[0].sql, /left join transit\.v_active_alerts a/);
});
