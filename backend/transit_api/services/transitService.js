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
      (select count(*)
       from transit.v_vehicle_dashboard
       where vehicle_timestamp >= now() - interval '3 minutes'
         and vehicle_status = 'in_service') as usable_vehicle_count,
      (select count(*)
       from transit.v_vehicle_dashboard
       where vehicle_timestamp >= now() - interval '3 minutes'
         and vehicle_status = 'in_service'
         and matched_to_static) as enriched_vehicle_count,
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
  const usableVehicleCount = Number(row.usable_vehicle_count || 0);
  const enrichedVehicleCount = Number(row.enriched_vehicle_count || 0);
  const status = !withinOperatingHours
    ? "outside_operating_hours"
    : ageSeconds !== null
      && ageSeconds <= 180
      && recentVehicleCount > 0
      && usableVehicleCount > 0
      && enrichedVehicleCount > 0
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
    usable_vehicle_count: usableVehicleCount,
    enriched_vehicle_count: enrichedVehicleCount,
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

async function getTripPath(pool, tripId) {
  const result = await pool.query(
    `
    select
      t.trip_id,
      t.shape_id,
      r.route_short_name,
      r.route_long_name,
      case
        when coalesce(rc.route_category, '') in ('BRT', 'MAX', 'EXPRESS') then 'brt'
        else 'bus'
      end as route_mode,
      s.shape_pt_sequence,
      s.shape_pt_lat,
      s.shape_pt_lon
    from transit.trips t
    join transit.routes r on r.route_id = t.route_id
    left join transit.v_route_catalog_lookup rc
      on upper(trim(r.route_short_name)) = rc.route_short_name_norm
    join transit.shapes s on s.shape_id = t.shape_id
    where t.trip_id = $1
    order by s.shape_pt_sequence
    `,
    [tripId],
  );

  if (result.rows.length === 0) return null;
  const first = result.rows[0];
  return {
    trip_id: first.trip_id,
    shape_id: first.shape_id,
    route_short_name: first.route_short_name,
    route_long_name: first.route_long_name,
    route_mode: first.route_mode,
    positions: result.rows.map((row) => [row.shape_pt_lat, row.shape_pt_lon]),
  };
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

async function getStopsByIds(pool, stopIds) {
  const ids = Array.isArray(stopIds)
    ? stopIds.map((value) => String(value).trim()).filter(Boolean).slice(0, 20)
    : [];
  if (ids.length === 0) return [];
  const result = await pool.query(
    `
    select stop_id, stop_code, stop_name, stop_lat, stop_lon
    from transit.stops
    where stop_id = any($1::text[])
    order by array_position($1::text[], stop_id)
    `,
    [ids],
  );
  return result.rows;
}

async function getStopRoutes(pool, stopId) {
  const result = await pool.query(
    `
    with local_context as (
      select (now() at time zone 'America/Edmonton')::date as service_date
    ), base_services as (
      select c.service_id
      from transit.calendar c
      cross join local_context lc
      where lc.service_date between c.start_date and c.end_date
        and case extract(isodow from lc.service_date)::integer
          when 1 then c.monday
          when 2 then c.tuesday
          when 3 then c.wednesday
          when 4 then c.thursday
          when 5 then c.friday
          when 6 then c.saturday
          when 7 then c.sunday
        end = 1
    ), active_services as (
      (select service_id from base_services
       union
       select cd.service_id
       from transit.calendar_dates cd
       cross join local_context lc
       where cd.date = lc.service_date and cd.exception_type = 1)
      except
      select cd.service_id
      from transit.calendar_dates cd
      cross join local_context lc
      where cd.date = lc.service_date and cd.exception_type = 2
    )
    select
      r.route_short_name,
      max(r.route_long_name) as route_long_name
    from transit.stop_times st
    join transit.trips t on t.trip_id = st.trip_id
    join active_services active on active.service_id = t.service_id
    join transit.routes r on r.route_id = t.route_id
    where st.stop_id = $1
      and nullif(trim(r.route_short_name), '') is not null
    group by r.route_short_name
    order by r.route_short_name
    `,
    [stopId],
  );
  return result.rows;
}

async function getStopArrivals(pool, stopId, windowMinutes = 60) {
  const result = await pool.query(
    `
    with local_context as (
      select (now() at time zone 'America/Edmonton')::date as service_date
    ), base_services as (
      select c.service_id
      from transit.calendar c
      cross join local_context lc
      where lc.service_date between c.start_date and c.end_date
        and case extract(isodow from lc.service_date)::integer
          when 1 then c.monday
          when 2 then c.tuesday
          when 3 then c.wednesday
          when 4 then c.thursday
          when 5 then c.friday
          when 6 then c.saturday
          when 7 then c.sunday
        end = 1
    ), active_services as (
      (select service_id from base_services
       union
       select cd.service_id
       from transit.calendar_dates cd
       cross join local_context lc
       where cd.date = lc.service_date and cd.exception_type = 1)
      except
      select cd.service_id
      from transit.calendar_dates cd
      cross join local_context lc
      where cd.date = lc.service_date and cd.exception_type = 2
    ), realtime as (
      select
        stu.trip_id,
        stu.stop_sequence,
        stu.stop_id,
        s.stop_code,
        s.stop_name,
        stu.arrival_time,
        stu.departure_time,
        coalesce(r.route_short_name, lr.route_short_name, tu.route_id) as route_short_name,
        coalesce(r.route_long_name, lr.route_long_name) as route_long_name,
        t.trip_headsign,
        vd.vehicle_id,
        'predicted'::text as prediction_source
      from transit.trip_update_stop_times_current stu
      join transit.trip_updates_current tu on tu.trip_id = stu.trip_id
      left join transit.trips t on t.trip_id = stu.trip_id
      left join transit.routes r on r.route_id = t.route_id
      left join transit.routes lr on lr.route_id = tu.route_id
      left join transit.stops s on s.stop_id = stu.stop_id
      left join transit.v_vehicle_dashboard vd
        on vd.trip_id = stu.trip_id and vd.vehicle_status = 'in_service'
      where stu.stop_id = $1
    ), scheduled as (
      select
        st.trip_id,
        st.stop_sequence,
        st.stop_id,
        s.stop_code,
        s.stop_name,
        (
          lc.service_date::timestamp
          + make_interval(secs =>
              split_part(st.arrival_time, ':', 1)::integer * 3600
              + split_part(st.arrival_time, ':', 2)::integer * 60
              + split_part(st.arrival_time, ':', 3)::integer)
        ) at time zone 'America/Edmonton' as arrival_time,
        (
          lc.service_date::timestamp
          + make_interval(secs =>
              split_part(st.departure_time, ':', 1)::integer * 3600
              + split_part(st.departure_time, ':', 2)::integer * 60
              + split_part(st.departure_time, ':', 3)::integer)
        ) at time zone 'America/Edmonton' as departure_time,
        r.route_short_name,
        r.route_long_name,
        t.trip_headsign,
        null::text as vehicle_id,
        'scheduled'::text as prediction_source
      from transit.stop_times st
      join transit.trips t on t.trip_id = st.trip_id
      join active_services active on active.service_id = t.service_id
      join transit.routes r on r.route_id = t.route_id
      join transit.stops s on s.stop_id = st.stop_id
      cross join local_context lc
      where st.stop_id = $1
        and st.arrival_time ~ '^[0-9]{1,2}:[0-9]{2}:[0-9]{2}$'
        and st.departure_time ~ '^[0-9]{1,2}:[0-9]{2}:[0-9]{2}$'
    ), combined as (
      select * from realtime
      union all
      select scheduled.*
      from scheduled
      where not exists (
        select 1
        from realtime
        where realtime.trip_id = scheduled.trip_id
          and realtime.stop_sequence = scheduled.stop_sequence
      )
    ), ranked as (
      select
        combined.*,
        row_number() over (
          partition by route_short_name
          order by arrival_time
        ) as route_arrival_rank
      from combined
      where arrival_time >= now() - interval '30 seconds'
        and arrival_time <= now() + make_interval(mins => $2)
    )
    select
      trip_id, stop_sequence, stop_id, stop_code, stop_name,
      arrival_time, departure_time, route_short_name, route_long_name,
      trip_headsign, vehicle_id, prediction_source
    from ranked
    where route_arrival_rank <= 3
    order by arrival_time, route_short_name
    limit 48
    `,
    [stopId, windowMinutes],
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
  getTripPath,
  getVehicleHistory,
  getVehicleContext,
  getVehicleStops,
  getVehicleAlerts,
  searchRoutes,
  searchStops,
  getStopsByIds,
  getStopRoutes,
  getStopArrivals,
  getNearbyStops,
};
