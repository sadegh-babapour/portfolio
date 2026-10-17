const express = require("express");
const cors = require("cors");

const { pool } = require("./db/pool");
const {
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
} = require("./services/transitService");


const app = express();
app.use(cors());
app.use(express.json());

app.get("/", (request, response) => {
  response.json({ ok: true, service: "calgary-transit-api" });
});

app.get("/api/health", async (request, response) => {
  try {
    const health = await getTransitHealth(pool);
    response.status(health.ok ? 200 : 503).json(health);
  } catch (error) {
    console.error(error);
    response.status(503).json({ ok: false, status: "unavailable" });
  }
});

app.get("/api/vehicles", async (request, response) => {
  const mode = (request.query.mode || "featured").toLowerCase();
  try {
    response.json(await getVehicles(pool, mode));
  } catch (error) {
    console.error(error);
    response.status(500).json({ error: "failed_to_load_vehicles" });
  }
});

app.get("/api/routes/paths", async (request, response) => {
  const mode = (request.query.mode || "featured").toLowerCase();
  try {
    response.json(await getRoutePaths(pool, mode, request.query.routes));
  } catch (error) {
    console.error(error);
    response.status(500).json({ error: "failed_to_load_route_paths" });
  }
});

app.get("/api/trips/:tripId/path", async (request, response) => {
  try {
    const path = await getTripPath(pool, request.params.tripId);
    if (!path) return response.status(404).json({ error: "trip_path_not_found" });
    return response.json(path);
  } catch (error) {
    console.error(error);
    return response.status(500).json({ error: "failed_to_load_trip_path" });
  }
});

app.get("/api/vehicles/history", async (request, response) => {
  const mode = (request.query.mode || "featured").toLowerCase();
  const density = (request.query.density || "all").toLowerCase();
  const windowMinutes = Number(request.query.window_minutes || 4);
  try {
    response.json(await getVehicleHistory(
      pool,
      mode,
      density,
      windowMinutes,
      request.query.routes,
    ));
  } catch (error) {
    console.error(error);
    response.status(500).json({ error: "failed_to_load_vehicle_history" });
  }
});

app.get("/api/vehicles/:vehicleId/context", async (request, response) => {
  try {
    const payload = await getVehicleContext(pool, request.params.vehicleId);
    if (!payload || !payload.vehicle) {
      return response.status(404).json({ error: "vehicle_context_not_found" });
    }
    return response.json(payload);
  } catch (error) {
    console.error(error);
    return response.status(500).json({ error: "failed_to_load_vehicle_context" });
  }
});

app.get("/api/vehicles/:vehicleId/stops", async (request, response) => {
  try {
    response.json(await getVehicleStops(pool, request.params.vehicleId));
  } catch (error) {
    console.error(error);
    response.status(500).json({ error: "failed_to_load_stops" });
  }
});

app.get("/api/vehicles/:vehicleId/alerts", async (request, response) => {
  try {
    response.json(await getVehicleAlerts(pool, request.params.vehicleId));
  } catch (error) {
    console.error(error);
    response.status(500).json({ error: "failed_to_load_alerts" });
  }
});

app.get("/api/routes/search", async (request, response) => {
  try {
    response.json(await searchRoutes(pool, request.query.q));
  } catch (error) {
    console.error(error);
    response.status(500).json({ error: "failed_to_search_routes" });
  }
});

app.get("/api/stops/search", async (request, response) => {
  try {
    response.json(await searchStops(pool, request.query.q));
  } catch (error) {
    console.error(error);
    response.status(500).json({ error: "failed_to_search_stops" });
  }
});

app.post("/api/stops/nearby", async (request, response) => {
  const lat = Number(request.body?.lat);
  const lon = Number(request.body?.lon);
  const requestedLimit = Number(request.body?.limit ?? 8);
  const radiusMeters = Number(request.body?.radius_meters ?? 800);
  if (
    !Number.isFinite(lat)
    || !Number.isFinite(lon)
    || !Number.isInteger(requestedLimit)
    || !Number.isInteger(radiusMeters)
    || lat < 50.7
    || lat > 51.4
    || lon < -114.5
    || lon > -113.7
    || radiusMeters < 100
    || radiusMeters > 2000
  ) {
    return response.status(400).json({ error: "invalid_calgary_location" });
  }
  const limit = Math.min(8, Math.max(1, requestedLimit));
  try {
    return response.json(await getNearbyStops(pool, lat, lon, limit, radiusMeters));
  } catch (error) {
    console.error(error);
    return response.status(500).json({ error: "failed_to_load_nearby_stops" });
  }
});

app.get("/api/stops", async (request, response) => {
  const ids = String(request.query.ids || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean)
    .slice(0, 20);
  try {
    response.json(await getStopsByIds(pool, ids));
  } catch (error) {
    console.error(error);
    response.status(500).json({ error: "failed_to_load_stops" });
  }
});

app.get("/api/stops/:stopId/routes", async (request, response) => {
  try {
    response.json(await getStopRoutes(pool, request.params.stopId));
  } catch (error) {
    console.error(error);
    response.status(500).json({ error: "failed_to_load_stop_routes" });
  }
});

app.get("/api/stops/:stopId/arrivals", async (request, response) => {
  const requestedWindow = Number(request.query.window_minutes || 60);
  if (!Number.isInteger(requestedWindow) || requestedWindow < 15 || requestedWindow > 180) {
    return response.status(400).json({ error: "invalid_arrival_window" });
  }
  try {
    return response.json(await getStopArrivals(
      pool,
      request.params.stopId,
      requestedWindow,
    ));
  } catch (error) {
    console.error(error);
    return response.status(500).json({ error: "failed_to_load_stop_arrivals" });
  }
});

const port = Number(process.env.TRANSIT_API_PORT || process.env.PORT || 4000);
app.listen(port, () => {
  console.log(`API listening on ${port}`);
});
