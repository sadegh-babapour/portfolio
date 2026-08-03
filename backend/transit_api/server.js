// const express = require("express");
// const { Pool } = require("pg");
// const cors = require("cors");

const express = require("express");
const cors = require("cors");
const { pool } = require("./db/pool");
const {
  getVehicles,
  getRoutePaths,
  getVehicleHistory,
  getVehicleContext,
  getVehicleStops,
  getVehicleAlerts,
} = require("./services/transitService");

const app = express();
app.use(cors());
app.use(express.json());

// const pool = new Pool({
//   host: process.env.PGHOST || "localhost",
//   port: Number(process.env.PGPORT || 5432),
//   database: process.env.PGDATABASE,
//   user: process.env.PGUSER,
//   password: process.env.PGPASSWORD,
// });

const FEATURED_ROUTES = ["300", "MP", "MO", "23", "57"];

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

app.get("/", (req, res) => {
  res.json({ ok: true, service: "calgary-transit-api" });
});

app.get("/api/health", async (req, res) => {
  try {
    await pool.query("select 1");
    res.json({ ok: true });
  } catch (err) {
    console.error(err);
    res.status(500).json({ ok: false });
  }
});

// app.get("/api/vehicles", async (req, res) => {
//   const mode = (req.query.mode || "featured").toLowerCase();
//   const density = (req.query.density || "all").toLowerCase();


//   const params = [];
//   const where = buildVehicleWhere(mode, params);

//   const perRouteLimit =
//     density === "1" ? 1 :
//       density === "2" ? 2 :
//         null;

//   if (perRouteLimit) {
//     params.push(perRouteLimit);

//     const sql = `
//     with ranked as (
//       select
//         vehicle_id,
//         trip_id,
//         vehicle_timestamp,
//         vehicle_timestamp_edmonton,
//         lat,
//         lon,
//         route_short_name,
//         route_long_name,
//         route_category,
//         trip_headsign,
//         route_mode,
//         row_number() over (
//           partition by route_short_name
//           order by vehicle_timestamp desc, vehicle_id
//         ) as rn
//       from transit.v_vehicle_dashboard
//       ${where}
//     )
//     select
//       vehicle_id,
//       trip_id,
//       vehicle_timestamp,
//       vehicle_timestamp_edmonton,
//       lat,
//       lon,
//       route_short_name,
//       route_long_name,
//       route_category,
//       trip_headsign,
//       route_mode
//     from ranked
//     where rn <= $${params.length}
//     order by
//       case
//         when route_short_name = '300' then 1
//         when route_short_name in ('MP', 'MO') then 2
//         else 3
//       end,
//       route_short_name nulls last,
//       vehicle_id
//   `;

//     try {
//       const result = await pool.query(sql, params);
//       return res.json(result.rows);
//     } catch (err) {
//       console.error(err);
//       return res.status(500).json({ error: "failed_to_load_vehicles" });
//     }
//   }});

app.get("/api/vehicles", async (req, res) => {
  const mode = (req.query.mode || "featured").toLowerCase();

  try {
    const rows = await getVehicles(pool, mode);
    res.json(rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "failed_to_load_vehicles" });
  }
});

// app.get("/api/routes/paths", async (req, res) => {
//   const mode = (req.query.mode || "featured").toLowerCase();
//   const routesParam = req.query.routes;

//   const params = [];
//   let where = buildVehicleWhere(mode, params);

//   if (routesParam) {
//     const routes = routesParam
//       .split(",")
//       .map((x) => x.trim())
//       .filter(Boolean);

//     if (routes.length > 0) {
//       params.push(routes);
//       where += ` and route_short_name = any($${params.length})`;
//     }
//   }

//   const sql = `
//     with active_routes as (
//       select distinct on (vd.route_short_name)
//         vd.route_short_name,
//         vd.route_long_name,
//         vd.route_mode,
//         t.shape_id
//       from transit.v_vehicle_dashboard vd
//       join transit.trips t
//         on t.trip_id = vd.trip_id
//       ${where}
//       and t.shape_id is not null
//       order by vd.route_short_name, vd.vehicle_timestamp desc
//     )
//     select
//       ar.route_short_name,
//       ar.route_long_name,
//       ar.route_mode,
//       ar.shape_id,
//       s.shape_pt_sequence,
//       s.shape_pt_lat,
//       s.shape_pt_lon
//     from active_routes ar
//     join transit.shapes s
//       on s.shape_id = ar.shape_id
//     order by ar.route_short_name, s.shape_pt_sequence
//   `;

//   try {
//     const result = await pool.query(sql, params);

//     const grouped = new Map();

//     for (const row of result.rows) {
//       const key = row.route_short_name;
//       if (!grouped.has(key)) {
//         grouped.set(key, {
//           route_short_name: row.route_short_name,
//           route_long_name: row.route_long_name,
//           route_mode: row.route_mode,
//           shape_id: row.shape_id,
//           positions: [],
//         });
//       }
//       grouped.get(key).positions.push([row.shape_pt_lat, row.shape_pt_lon]);
//     }

//     res.json(Array.from(grouped.values()));
//   } catch (err) {
//     console.error(err);
//     res.status(500).json({ error: "failed_to_load_route_paths" });
//   }
// });
app.get("/api/routes/paths", async (req, res) => {
  const mode = (req.query.mode || "featured").toLowerCase();
  const routesParam = req.query.routes;

  try {
    const rows = await getRoutePaths(pool, mode, routesParam);
    res.json(rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "failed_to_load_route_paths" });
  }
});

// app.get("/api/vehicles/history", async (req, res) => {
//   const mode = (req.query.mode || "featured").toLowerCase();
//   const density = (req.query.density || "all").toLowerCase();
//   const windowMinutes = Number(req.query.window_minutes || 4);

//   const params = [];
//   const where = buildVehicleWhere(mode, params);

//   const perRouteLimit =
//     density === "1" ? 1 :
//     density === "2" ? 2 :
//     null;

//   let eligibleVehiclesCte = `
//     eligible_vehicles as (
//       select
//         vehicle_id,
//         trip_id,
//         route_short_name,
//         route_long_name,
//         route_category,
//         trip_headsign,
//         route_mode
//       from transit.v_vehicle_dashboard
//       ${where}
//     )
//   `;

//   if (perRouteLimit) {
//     params.push(perRouteLimit);
//     eligibleVehiclesCte = `
//       eligible_vehicles as (
//         select
//           vehicle_id,
//           trip_id,
//           route_short_name,
//           route_long_name,
//           route_category,
//           trip_headsign,
//           route_mode
//         from (
//           select
//             vehicle_id,
//             trip_id,
//             route_short_name,
//             route_long_name,
//             route_category,
//             trip_headsign,
//             route_mode,
//             row_number() over (
//               partition by route_short_name
//               order by vehicle_timestamp desc, vehicle_id
//             ) as rn
//           from transit.v_vehicle_dashboard
//           ${where}
//         ) ranked
//         where rn <= $${params.length}
//       )
//     `;
//   }

//   params.push(windowMinutes);

//   const sql = `
//     with
//     ${eligibleVehiclesCte},
//     recent_points as (
//       select
//         vp.vehicle_id,
//         vp.trip_id,
//         vp.vehicle_timestamp,
//         vp.lat,
//         vp.lon
//       from transit.vehicle_positions_raw vp
//       join eligible_vehicles ev
//         on ev.vehicle_id = vp.vehicle_id
//       where vp.vehicle_timestamp >= now() - make_interval(mins => $${params.length})
//     )
//     select
//       ev.vehicle_id,
//       ev.trip_id,
//       ev.route_short_name,
//       ev.route_long_name,
//       ev.route_category,
//       ev.trip_headsign,
//       ev.route_mode,
//       rp.vehicle_timestamp,
//       rp.lat,
//       rp.lon
//     from eligible_vehicles ev
//     join recent_points rp
//       on rp.vehicle_id = ev.vehicle_id
//     order by ev.vehicle_id, rp.vehicle_timestamp
//   `;

//   try {
//     const result = await pool.query(sql, params);

//     const grouped = new Map();

//     for (const row of result.rows) {
//       if (!grouped.has(row.vehicle_id)) {
//         grouped.set(row.vehicle_id, {
//           vehicle_id: row.vehicle_id,
//           trip_id: row.trip_id,
//           route_short_name: row.route_short_name,
//           route_long_name: row.route_long_name,
//           route_category: row.route_category,
//           trip_headsign: row.trip_headsign,
//           route_mode: row.route_mode,
//           observations: [],
//         });
//       }

//       grouped.get(row.vehicle_id).observations.push({
//         vehicle_timestamp: row.vehicle_timestamp,
//         lat: row.lat,
//         lon: row.lon,
//       });
//     }

//     res.json(Array.from(grouped.values()));
//   } catch (err) {
//     console.error(err);
//     res.status(500).json({ error: "failed_to_load_vehicle_history" });
//   }
// });
app.get("/api/vehicles/history", async (req, res) => {
  const mode = (req.query.mode || "featured").toLowerCase();
  const density = (req.query.density || "all").toLowerCase();
  const windowMinutes = Number(req.query.window_minutes || 4);

  try {
    const rows = await getVehicleHistory(pool, mode, density, windowMinutes);
    res.json(rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "failed_to_load_vehicle_history" });
  }
});

// app.get("/api/vehicles/:vehicleId/context", async (req, res) => {
//   const { vehicleId } = req.params;

//   const sql = `
//     with selected_vehicle as (
//       select
//         vd.vehicle_id,
//         vd.trip_id,
//         vd.route_short_name,
//         vd.route_long_name,
//         vd.route_category,
//         vd.trip_headsign,
//         vd.route_mode,
//         vd.lat,
//         vd.lon
//       from transit.v_vehicle_dashboard vd
//       where vd.vehicle_id = $1
//         and vd.vehicle_status = 'in_service'
//     ),
//     selected_trip as (
//       select
//         sv.*,
//         t.shape_id
//       from selected_vehicle sv
//       join transit.trips t
//         on t.trip_id = sv.trip_id
//     ),
//     future_tripupdate_stops as (
//       select
//         stu.trip_id,
//         stu.stop_sequence,
//         stu.stop_id,
//         s.stop_name,
//         s.stop_lat,
//         s.stop_lon,
//         stu.arrival_time,
//         stu.departure_time
//       from transit.trip_update_stop_times_current stu
//       left join transit.stops s
//         on s.stop_id = stu.stop_id
//       join selected_trip st
//         on st.trip_id = stu.trip_id
//       order by stu.stop_sequence
//     ),
//     next_stops as (
//       select *
//       from future_tripupdate_stops
//       order by stop_sequence
//       limit 3
//     ),
//     anchor_stop as (
//       select min(stop_sequence) as next_stop_sequence
//       from next_stops
//     ),
//     previous_static_stops as (
//       select
//         st.trip_id,
//         st.stop_sequence,
//         st.stop_id,
//         s.stop_name,
//         s.stop_lat,
//         s.stop_lon,
//         st.arrival_time,
//         st.departure_time
//       from transit.stop_times st
//       left join transit.stops s
//         on s.stop_id = st.stop_id
//       join selected_trip trip
//         on trip.trip_id = st.trip_id
//       join anchor_stop a
//         on st.stop_sequence < a.next_stop_sequence
//       order by st.stop_sequence desc
//       limit 3
//     ),
//     shape_points as (
//       select
//         sh.shape_id,
//         sh.shape_pt_sequence,
//         sh.shape_pt_lat,
//         sh.shape_pt_lon
//       from transit.shapes sh
//       join selected_trip st
//         on st.shape_id = sh.shape_id
//       order by sh.shape_pt_sequence
//     )
//     select json_build_object(
//       'vehicle', (
//         select row_to_json(st)
//         from selected_trip st
//         limit 1
//       ),
//       'previous_stops', (
//         select coalesce(json_agg(row_to_json(ps) order by ps.stop_sequence), '[]'::json)
//         from (
//           select *
//           from previous_static_stops
//           order by stop_sequence
//         ) ps
//       ),
//       'next_stops', (
//         select coalesce(json_agg(row_to_json(ns) order by ns.stop_sequence), '[]'::json)
//         from next_stops ns
//       ),
//       'shape_points', (
//         select coalesce(json_agg(row_to_json(sp) order by sp.shape_pt_sequence), '[]'::json)
//         from shape_points sp
//       )
//     ) as payload
//   `;

//   try {
//     const result = await pool.query(sql, [vehicleId]);
//     const payload = result.rows?.[0]?.payload || null;

//     if (!payload || !payload.vehicle) {
//       return res.status(404).json({ error: "vehicle_context_not_found" });
//     }

//     res.json(payload);
//   } catch (err) {
//     console.error(err);
//     res.status(500).json({ error: "failed_to_load_vehicle_context" });
//   }
// });
app.get("/api/vehicles/:vehicleId/context", async (req, res) => {
  const { vehicleId } = req.params;

  try {
    const payload = await getVehicleContext(pool, vehicleId);

    if (!payload || !payload.vehicle) {
      return res.status(404).json({ error: "vehicle_context_not_found" });
    }

    res.json(payload);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "failed_to_load_vehicle_context" });
  }
});

// app.get("/api/vehicles/:vehicleId/stops", async (req, res) => {
//   const { vehicleId } = req.params;

//   const sql = `
//     with selected_vehicle as (
//       select *
//       from transit.v_vehicle_dashboard
//       where vehicle_id = $1
//         and vehicle_status = 'in_service'
//     )
//     select
//       sv.vehicle_id,
//       sv.trip_id,
//       sv.route_short_name,
//       sv.route_long_name,
//       sv.route_category,
//       sv.trip_headsign,
//       s.stop_sequence,
//       s.stop_id,
//       s.stop_name,
//       s.arrival_time,
//       s.departure_time
//     from selected_vehicle sv
//     join transit.v_trip_upcoming_stops s
//       on s.trip_id = sv.trip_id
//     order by s.stop_sequence
//   `;

//   try {
//     const result = await pool.query(sql, [vehicleId]);
//     res.json(result.rows);
//   } catch (err) {
//     console.error(err);
//     res.status(500).json({ error: "failed_to_load_stops" });
//   }
// });
app.get("/api/vehicles/:vehicleId/stops", async (req, res) => {
  const { vehicleId } = req.params;

  try {
    const rows = await getVehicleStops(pool, vehicleId);
    res.json(rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "failed_to_load_stops" });
  }
});

// app.get("/api/vehicles/:vehicleId/alerts", async (req, res) => {
//   const { vehicleId } = req.params;

//   const sql = `
//     with selected_vehicle as (
//       select *
//       from transit.v_vehicle_dashboard
//       where vehicle_id = $1
//         and vehicle_status = 'in_service'
//     )
//     select distinct
//       a.feed_entity_id,
//       a.active_start,
//       a.active_end,
//       a.route_short_name,
//       a.route_long_name,
//       a.stop_id,
//       a.stop_name,
//       a.description_html
//     from selected_vehicle sv
//     left join transit.v_active_alerts a
//       on a.route_short_name = sv.route_short_name
//     order by a.active_end nulls last, a.feed_entity_id
//   `;

//   try {
//     const result = await pool.query(sql, [vehicleId]);
//     res.json(result.rows);
//   } catch (err) {
//     console.error(err);
//     res.status(500).json({ error: "failed_to_load_alerts" });
//   }
// });
app.get("/api/vehicles/:vehicleId/alerts", async (req, res) => {
  const { vehicleId } = req.params;

  try {
    const rows = await getVehicleAlerts(pool, vehicleId);
    res.json(rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: "failed_to_load_alerts" });
  }
});

// const port = Number(process.env.PORT || 4000);
const port = Number(process.env.TRANSIT_API_PORT || process.env.PORT || 4000);

app.listen(port, () => {
  console.log(`API listening on ${port}`);
});