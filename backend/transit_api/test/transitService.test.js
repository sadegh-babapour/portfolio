const test = require("node:test");
const assert = require("node:assert/strict");

const {
  getTransitHealth,
  getVehicles,
  getRoutePaths,
  getTripPath,
  getVehicleHistory,
  getVehicleContext,
  getVehicleAlerts,
  searchRoutes,
  searchStops,
  getStopsByIds,
  getStopRoutes,
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
    usable_vehicle_count: "280",
    enriched_vehicle_count: "279",
    latest_trip_update_timestamp: "2026-08-13T17:59:31Z",
    latest_alert_timestamp: "2026-08-13T17:59:32Z",
  }]);
  const fresh = await getTransitHealth(freshPool);
  assert.equal(fresh.ok, true);
  assert.equal(fresh.status, "healthy");
  assert.equal(fresh.recent_vehicle_count, 287);
  assert.equal(fresh.usable_vehicle_count, 280);
  assert.equal(fresh.enriched_vehicle_count, 279);

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

test("transit health reports Calgary's feed next to what the poller stored", async () => {
  const pool = {
    async query(sql) {
      if (sql.includes("poller_feed_status")) {
        return {
          rows: [
            {
              feed_name: "vehicle_positions",
              finished_at: "2026-11-13T17:20:00Z",
              seconds_since_previous: 30.2,
              duration_seconds: 0.4,
              feed_header_timestamp: "2026-11-13T17:19:52Z",
              entities_in_feed: 355,
              rows_written: 355,
              timestamps_from_header: 266,
              median_ingest_lag_seconds: "21.5",
            },
            {
              feed_name: "trip_updates",
              finished_at: "2026-11-13T17:20:02Z",
              seconds_since_previous: 30.1,
              duration_seconds: 2.1,
              feed_header_timestamp: null,
              entities_in_feed: 1785,
              rows_written: 1785,
              timestamps_from_header: 0,
              median_ingest_lag_seconds: "21.5",
            },
          ],
        };
      }
      return {
        rows: [{
          within_operating_hours: true,
          vehicle_age_seconds: "20",
          recent_vehicle_count: "354",
          usable_vehicle_count: "350",
          enriched_vehicle_count: "350",
        }],
      };
    },
  };

  const health = await getTransitHealth(pool);
  assert.equal(health.status, "healthy");
  assert.equal(health.pipeline.median_ingest_lag_seconds, 21.5);
  assert.deepEqual(health.pipeline.feeds.vehicle_positions, {
    finished_at: "2026-11-13T17:20:00Z",
    seconds_since_previous: 30.2,
    duration_seconds: 0.4,
    feed_header_timestamp: "2026-11-13T17:19:52Z",
    city_entities: 355,
    rows_written: 355,
    timestamps_from_header: 266,
  });
  assert.equal(health.pipeline.feeds.trip_updates.duration_seconds, 2.1);
});

test("transit health still answers when the poller status cannot be read", async () => {
  const pool = {
    async query(sql) {
      if (sql.includes("poller_feed_status")) throw new Error('relation "transit.poller_feed_status" does not exist');
      return { rows: [{ within_operating_hours: true, vehicle_age_seconds: "20", recent_vehicle_count: "5",
        usable_vehicle_count: "5", enriched_vehicle_count: "5" }] };
    },
  };
  const originalError = console.error;
  console.error = () => {};
  try {
    const health = await getTransitHealth(pool);
    assert.equal(health.status, "healthy");
    assert.equal(health.pipeline, null);
  } finally {
    console.error = originalError;
  }
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

test("transit health is degraded when fresh positions cannot be statically enriched", async () => {
  const pool = poolReturning([{
    within_operating_hours: true,
    latest_vehicle_timestamp: "2026-09-02T22:32:01Z",
    vehicle_age_seconds: "79",
    recent_vehicle_count: "551",
    usable_vehicle_count: "540",
    enriched_vehicle_count: "0",
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

test("trip path returns the exact scheduled trip shape", async () => {
  const pool = poolReturning([
    {
      trip_id: "trip-54",
      shape_id: "shape-54",
      route_short_name: "54",
      route_long_name: "Edgevalley",
      route_mode: "bus",
      shape_pt_lat: 51.1,
      shape_pt_lon: -114.1,
    },
    {
      trip_id: "trip-54",
      shape_id: "shape-54",
      route_short_name: "54",
      route_long_name: "Edgevalley",
      route_mode: "bus",
      shape_pt_lat: 51.2,
      shape_pt_lon: -114.2,
    },
  ]);

  assert.deepEqual(await getTripPath(pool, "trip-54"), {
    trip_id: "trip-54",
    shape_id: "shape-54",
    route_short_name: "54",
    route_long_name: "Edgevalley",
    route_mode: "bus",
    positions: [[51.1, -114.1], [51.2, -114.2]],
  });
  assert.deepEqual(pool.calls[0].params, ["trip-54"]);
  assert.match(pool.calls[0].sql, /where t\.trip_id = \$1/);
});

test("missing trip path returns null", async () => {
  assert.equal(await getTripPath(poolReturning([]), "missing"), null);
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

test("stop arrivals use the requested stop and requested prediction window", async () => {
  const pool = poolReturning([]);
  assert.deepEqual(await getStopArrivals(pool, "1001", 60), []);
  assert.deepEqual(pool.calls[0].params, ["1001", 60]);
  assert.match(pool.calls[0].sql, /make_interval\(mins => \$2\)/);
});

test("saved-stop hydration and stop routes stay parameterized and bounded", async () => {
  const savedPool = poolReturning([{ stop_id: "4775" }]);
  assert.deepEqual(await getStopsByIds(savedPool, ["4775", "1001"]), [
    { stop_id: "4775" },
  ]);
  assert.deepEqual(savedPool.calls[0].params, [["4775", "1001"]]);
  assert.match(savedPool.calls[0].sql, /stop_id = any\(\$1::text\[\]\)/);

  const routePool = poolReturning([{ route_short_name: "78" }]);
  assert.deepEqual(await getStopRoutes(routePool, "4775"), [
    { route_short_name: "78" },
  ]);
  assert.deepEqual(routePool.calls[0].params, ["4775"]);
  assert.match(routePool.calls[0].sql, /where st\.stop_id = \$1/);
});

test("nearby stops use bounded parameterized coordinates and walking radius", async () => {
  const pool = poolReturning([{ stop_id: "1001", distance_meters: 120 }]);
  const rows = await getNearbyStops(pool, 51.0447, -114.0719, 6, 800);
  assert.equal(rows[0].distance_meters, 120);
  assert.deepEqual(pool.calls[0].params, [51.0447, -114.0719, 6, 800]);
  assert.match(pool.calls[0].sql, /limit \$3/);
  assert.match(pool.calls[0].sql, /distance_meters <= \$4/);
  assert.match(pool.calls[0].sql, /distance_meters/);
});

test("missing vehicle context returns null", async () => {
  const pool = poolReturning([]);

  assert.equal(await getVehicleContext(pool, "missing"), null);
  assert.deepEqual(pool.calls[0].params, ["missing"]);
  assert.match(pool.calls[0].sql, /next_stops[\s\S]*limit 24/);
  assert.doesNotMatch(pool.calls[0].sql, /previous_static_stops|previous_stops/);
});

test("vehicle alerts require a matching active alert", async () => {
  const pool = poolReturning([]);

  assert.deepEqual(await getVehicleAlerts(pool, "8305"), []);
  assert.match(pool.calls[0].sql, /join transit\.v_active_alerts a/);
  assert.match(pool.calls[0].sql, /a\.header_text/);
  assert.doesNotMatch(pool.calls[0].sql, /left join transit\.v_active_alerts a/);
});
