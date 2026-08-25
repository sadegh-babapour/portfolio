const { FEATURED_ROUTES } = require("../config/transitConfig");

async function getTransitHealth(pool) {
  const sql = `
    select
      now() as checked_at,
      extract(hour from now() at time zone 'America/Edmonton') >= 8
        and extract(hour from now() at time zone 'America/Edmonton') < 21
        as within_operating_hours,
      max(vehicle_timestamp) as latest_vehicle_timestamp,
      extract(epoch from (now() - max(vehicle_timestamp))) as vehicle_age_seconds,
      count(*) filter (
        where vehicle_timestamp >= now() - interval '3 minutes'
      ) as recent_vehicle_count,
      (select max(feed_header_timestamp) from transit.trip_updates_current)
        as latest_trip_update_timestamp,
      (select max(feed_header_timestamp) from transit.alerts_current)
        as latest_alert_timestamp
    from transit.vehicle_positions_current
  `;

  const result = await pool.query(sql);
  const row = result.rows[0] || {};
  const withinOperatingHours = row.within_operating_hours === true;
  const ageSeconds = row.vehicle_age_seconds === null
    || row.vehicle_age_seconds === undefined
    ? null
    : Number(row.vehicle_age_seconds);
  const recentVehicleCount = Number(row.recent_vehicle_count || 0);
  const status = !withinOperatingHours
    ? "outside_operating_hours"
    : ageSeconds !== null && ageSeconds <= 180 && recentVehicleCount > 0
      ? "healthy"
      : "degraded";

  return {
    ok: status !== "degraded",
    status,
    checked_at: row.checked_at || null,
    operating_hours: {
      timezone: "America/Edmonton",
      start: "08:00",
      end: "21:00",
    },
    latest_vehicle_timestamp: row.latest_vehicle_timestamp || null,
    vehicle_age_seconds: ageSeconds,
    recent_vehicle_count: recentVehicleCount,
    latest_trip_update_timestamp: row.latest_trip_update_timestamp || null,
    latest_alert_timestamp: row.latest_alert_timestamp || null,
  };
}

function buildVehicleWhere(mode, params) {
  let where = `where vehicle_status = 'in_service'`;

  if (mode === "brt") {
    where += ` and route_mode = 'brt'`;
  } else if (mode === "bus") {
    where += ` and route_mode = 'bus'`;
  } else if (mode === "featured") {
    params.push(FEATURED_ROUTES);
    where += ` and route_short_name = any($${params.length})`;
  }

  return where;
}

async function getVehicles(pool, mode) {
  const params = [];
  const where = buildVehicleWhere(mode, params);

  const sql = `
    select
      vehicle_id,
      trip_id,
      vehicle_timestamp,
      vehicle_timestamp_edmonton,
      lat,
      lon,
      route_short_name,
      route_long_name,
      route_category,
      trip_headsign,
      route_mode
    from transit.v_vehicle_dashboard
    ${where}
    order by
      case
        when route_short_name = '300' then 1
        when route_short_name in ('MP', 'MO') then 2
        else 3
      end,
      route_short_name nulls last,
      vehicle_id
  `;

  const result = await pool.query(sql, params);
  return result.rows;
}

async function getRoutePaths(pool, mode, routesParam) {
  const params = [];
  let where = buildVehicleWhere(mode, params);

  if (routesParam) {
    const routes = routesParam
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);

    if (routes.length > 0) {
      params.push(routes);
      where += ` and route_short_name = any($${params.length})`;
    }
  }

  const sql = `
    with active_routes as (
      select distinct on (vd.route_short_name)
        vd.route_short_name,
        vd.route_long_name,
        vd.route_mode,
        t.shape_id
      from transit.v_vehicle_dashboard vd
      join transit.trips t
        on t.trip_id = vd.trip_id
      ${where}
      and t.shape_id is not null
      order by vd.route_short_name, vd.vehicle_timestamp desc
    )
    select
      ar.route_short_name,
      ar.route_long_name,
      ar.route_mode,
      ar.shape_id,
      s.shape_pt_sequence,
      s.shape_pt_lat,
      s.shape_pt_lon
    from active_routes ar
    join transit.shapes s
      on s.shape_id = ar.shape_id
    order by ar.route_short_name, s.shape_pt_sequence
  `;

  const result = await pool.query(sql, params);

  const grouped = new Map();

  for (const row of result.rows) {
    const key = row.route_short_name;
    if (!grouped.has(key)) {
      grouped.set(key, {
        route_short_name: row.route_short_name,
        route_long_name: row.route_long_name,
        route_mode: row.route_mode,
        shape_id: row.shape_id,
        positions: [],
      });
    }
    grouped.get(key).positions.push([row.shape_pt_lat, row.shape_pt_lon]);
  }

  return Array.from(grouped.values());
}

async function getVehicleHistory(pool, mode, density, windowMinutes, routesParam) {
  const params = [];
  let where = buildVehicleWhere(mode, params);
  const requestedRoutes = typeof routesParam === "string"
    ? routesParam.split(",").map((route) => route.trim()).filter(Boolean).slice(0, 10)
    : [];
  if (requestedRoutes.length > 0) {
    params.push(requestedRoutes);
    where += ` and route_short_name = any($${params.length})`;
  }

  const perRouteLimit =
    density === "1" ? 1 :
    density === "2" ? 2 :
    null;

  let eligibleVehiclesCte = `
    eligible_vehicles as (
      select
        vehicle_id,
        trip_id,
        route_short_name,
        route_long_name,
        route_category,
        trip_headsign,
        route_mode
      from transit.v_vehicle_dashboard
      ${where}
    )
  `;

  if (perRouteLimit) {
    params.push(perRouteLimit);
    eligibleVehiclesCte = `
      eligible_vehicles as (
        select
          vehicle_id,
          trip_id,
          route_short_name,
          route_long_name,
          route_category,
          trip_headsign,
          route_mode
        from (
          select
            vehicle_id,
            trip_id,
            route_short_name,
            route_long_name,
            route_category,
            trip_headsign,
            route_mode,
            row_number() over (
              partition by route_short_name
              order by vehicle_timestamp desc, vehicle_id
            ) as rn
          from transit.v_vehicle_dashboard
          ${where}
        ) ranked
        where rn <= $${params.length}
      )
    `;
  }

  params.push(windowMinutes);

  const sql = `
    with
    ${eligibleVehiclesCte},
    recent_points as (
      select
        vp.vehicle_id,
        vp.trip_id,
        vp.vehicle_timestamp,
        vp.lat,
        vp.lon
      from transit.vehicle_positions_raw vp
      join eligible_vehicles ev
        on ev.vehicle_id = vp.vehicle_id
       and ev.trip_id = vp.trip_id
      where vp.vehicle_timestamp >= now() - make_interval(mins => $${params.length})
    )
    select
      ev.vehicle_id,
      ev.trip_id,
      ev.route_short_name,
      ev.route_long_name,
      ev.route_category,
      ev.trip_headsign,
      ev.route_mode,
      rp.vehicle_timestamp,
      rp.lat,
      rp.lon
    from eligible_vehicles ev
    join recent_points rp
      on rp.vehicle_id = ev.vehicle_id
     and rp.trip_id = ev.trip_id
    order by ev.vehicle_id, rp.vehicle_timestamp
  `;

  const result = await pool.query(sql, params);

  const grouped = new Map();

  for (const row of result.rows) {
    if (!grouped.has(row.vehicle_id)) {
      grouped.set(row.vehicle_id, {
        vehicle_id: row.vehicle_id,
        trip_id: row.trip_id,
        route_short_name: row.route_short_name,
        route_long_name: row.route_long_name,
        route_category: row.route_category,
        trip_headsign: row.trip_headsign,
        route_mode: row.route_mode,
        observations: [],
      });
    }

    grouped.get(row.vehicle_id).observations.push({
      vehicle_timestamp: row.vehicle_timestamp,
      lat: row.lat,
      lon: row.lon,
    });
  }

  return Array.from(grouped.values());
}

async function getVehicleContext(pool, vehicleId) {
  const sql = `
    with selected_vehicle as (
      select
        vd.vehicle_id,
        vd.trip_id,
        vd.route_short_name,
        vd.route_long_name,
        vd.route_category,
        vd.trip_headsign,
        vd.route_mode,
        vd.lat,
        vd.lon
      from transit.v_vehicle_dashboard vd
      where vd.vehicle_id = $1
        and vd.vehicle_status = 'in_service'
    ),
    selected_trip as (
      select
        sv.*,
        t.shape_id
      from selected_vehicle sv
      join transit.trips t
        on t.trip_id = sv.trip_id
    ),
    future_tripupdate_stops as (
      select
        stu.trip_id,
        stu.stop_sequence,
        stu.stop_id,
        s.stop_name,
        s.stop_lat,
        s.stop_lon,
        stu.arrival_time,
        stu.departure_time
      from transit.trip_update_stop_times_current stu
      left join transit.stops s
        on s.stop_id = stu.stop_id
      join selected_trip st
        on st.trip_id = stu.trip_id
      order by stu.stop_sequence
    ),
    next_stops as (
      select *
      from future_tripupdate_stops
      order by stop_sequence
      limit 24
    ),
    shape_points as (
      select
        sh.shape_id,
        sh.shape_pt_sequence,
        sh.shape_pt_lat,
        sh.shape_pt_lon
      from transit.shapes sh
      join selected_trip st
        on st.shape_id = sh.shape_id
      order by sh.shape_pt_sequence
    )
    select json_build_object(
      'vehicle', (
        select row_to_json(st)
        from selected_trip st
        limit 1
      ),
      'next_stops', (
        select coalesce(json_agg(row_to_json(ns) order by ns.stop_sequence), '[]'::json)
        from next_stops ns
      ),
      'shape_points', (
        select coalesce(json_agg(row_to_json(sp) order by sp.shape_pt_sequence), '[]'::json)
        from shape_points sp
      )
    ) as payload
  `;

  const result = await pool.query(sql, [vehicleId]);
  return result.rows?.[0]?.payload || null;
}

async function getVehicleStops(pool, vehicleId) {
  const sql = `
    with selected_vehicle as (
      select *
      from transit.v_vehicle_dashboard
      where vehicle_id = $1
        and vehicle_status = 'in_service'
    )
    select
      sv.vehicle_id,
      sv.trip_id,
      sv.route_short_name,
      sv.route_long_name,
      sv.route_category,
      sv.trip_headsign,
      s.stop_sequence,
      s.stop_id,
      s.stop_name,
      s.arrival_time,
      s.departure_time
    from selected_vehicle sv
    join transit.v_trip_upcoming_stops s
      on s.trip_id = sv.trip_id
    order by s.stop_sequence
  `;

  const result = await pool.query(sql, [vehicleId]);
  return result.rows;
}

async function getVehicleAlerts(pool, vehicleId) {
  const sql = `
    with selected_vehicle as (
      select *
      from transit.v_vehicle_dashboard
      where vehicle_id = $1
        and vehicle_status = 'in_service'
    )
    select distinct
      a.feed_entity_id,
      a.active_start,
      a.active_end,
      a.header_text,
      a.route_short_name,
      a.route_long_name,
      a.stop_id,
      a.stop_name,
      a.description_html
    from selected_vehicle sv
    join transit.v_active_alerts a
      on a.route_short_name = sv.route_short_name
    order by a.active_end nulls last, a.feed_entity_id
  `;

  const result = await pool.query(sql, [vehicleId]);
  return result.rows;
}

async function searchRoutes(pool, query) {
  const normalized = String(query || "").trim().slice(0, 60);
  if (!normalized) return [];
  const result = await pool.query(
    `
    select
      route_short_name,
      max(route_long_name) as route_long_name,
      max(route_mode) as route_mode,
      count(distinct vehicle_id)::integer as active_vehicle_count,
      array_remove(array_agg(distinct nullif(trim(trip_headsign), '')), null) as headsigns
    from transit.v_vehicle_dashboard
    where vehicle_status = 'in_service'
      and (
        route_short_name ilike $1
        or route_long_name ilike $1
        or trip_headsign ilike $1
      )
    group by route_short_name
    order by
      case when upper(route_short_name) = upper($2) then 0 else 1 end,
      route_short_name
    limit 12
    `,
    [`%${normalized}%`, normalized],
  );
  return result.rows;
}

async function searchStops(pool, query) {
  const normalized = String(query || "").trim().slice(0, 60);
  if (!normalized) return [];
  const result = await pool.query(
    `
    select stop_id, stop_code, stop_name, stop_lat, stop_lon
    from transit.stops
    where stop_code ilike $1 or stop_name ilike $1
    order by
      case when upper(coalesce(stop_code, '')) = upper($2) then 0 else 1 end,
      stop_name,
      stop_code nulls last
    limit 12
    `,
    [`%${normalized}%`, normalized],
  );
  return result.rows;
}

async function getStopArrivals(pool, stopId) {
  const result = await pool.query(
    `
    select
      stu.trip_id,
      stu.stop_sequence,
      stu.stop_id,
      s.stop_code,
      s.stop_name,
      stu.arrival_time,
      stu.departure_time,
      coalesce(r.route_short_name, tu.route_id) as route_short_name,
      r.route_long_name,
      t.trip_headsign,
      vd.vehicle_id
    from transit.trip_update_stop_times_current stu
    join transit.trip_updates_current tu on tu.trip_id = stu.trip_id
    left join transit.trips t on t.trip_id = stu.trip_id
    left join transit.routes r on r.route_id = t.route_id
    left join transit.stops s on s.stop_id = stu.stop_id
    left join transit.v_vehicle_dashboard vd
      on vd.trip_id = stu.trip_id and vd.vehicle_status = 'in_service'
    where stu.stop_id = $1
      and stu.arrival_time >= now() - interval '30 seconds'
      and stu.arrival_time <= now() + interval '15 minutes'
    order by stu.arrival_time, route_short_name
    limit 24
    `,
    [stopId],
  );
  return result.rows;
}

async function getNearbyStops(pool, lat, lon, limit = 8, radiusMeters = 800) {
  const result = await pool.query(
    `
    with nearby as (
      select
        stop_id,
        stop_code,
        stop_name,
        stop_lat,
        stop_lon,
        round((
          111045 * sqrt(
            power(stop_lat - $1, 2)
            + power((stop_lon - $2) * cos(radians($1)), 2)
          )
        )::numeric, 0)::integer as distance_meters
      from transit.stops
      where stop_lat is not null
        and stop_lon is not null
        and stop_lat between $1 - 0.12 and $1 + 0.12
        and stop_lon between $2 - 0.18 and $2 + 0.18
    )
    select *
    from nearby
    where distance_meters <= $4
    order by distance_meters, stop_name
    limit $3
    `,
    [lat, lon, limit, radiusMeters],
  );
  return result.rows;
}

module.exports = {
  getTransitHealth,
  getVehicles,
  getRoutePaths,
  getVehicleHistory,
  getVehicleContext,
  getVehicleStops,
  getVehicleAlerts,
  searchRoutes,
  searchStops,
  getStopArrivals,
  getNearbyStops,
};
