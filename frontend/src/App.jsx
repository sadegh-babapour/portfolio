import { useEffect, useMemo, useRef, useState } from "react";
// import {
//   MapContainer,
//   Marker,
//   Popup,
//   TileLayer,
//   useMap,
// } from "react-leaflet";
import {
  MapContainer,
  Marker,
  // Popup,
  TileLayer,
  useMap,
  // useMapEvents,
} from "react-leaflet";

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./App.css";
// import AntPath from "./AntPath";
import RouteLine from "./RouteLine";
import SelectedRouteAntPath from "./SelectedRouteAntPath";
import SelectedCorridor from "./SelectedCorridor";



delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

// const API_BASE = "http://localhost:4000/api";
const API_BASE = import.meta.env.VITE_TRANSIT_API_BASE_URL || "/api";
const FEATURED_ROUTES = ["300", "MP", "MO", "23", "57"];

const TILE_CONFIG = {
  light: {
    url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: "&copy; OpenStreetMap contributors",
    label: "Light",
  },
  dark: {
    url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    attribution: "&copy; OpenStreetMap &copy; CARTO",
    label: "Dark",
  },
  white: {
    url: "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
    attribution: "&copy; OpenStreetMap &copy; CARTO",
    label: "White",
  },
};

const PLAYBACK_DELAY_SECONDS = 75;
const HISTORY_WINDOW_MINUTES = 4;
const STOPPED_THRESHOLD_METERS = 20;
const STALE_THRESHOLD_SECONDS = 120;

function toMillis(value) {
  return new Date(value).getTime();
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function distanceMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const toRad = (d) => (d * Math.PI) / 180;

  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const p1 = toRad(lat1);
  const p2 = toRad(lat2);

  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(p1) * Math.cos(p2) * Math.sin(dLon / 2) ** 2;

  return 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function modeLabel(mode) {
  if (mode === "brt") return "BRT / MAX / Express";
  if (mode === "bus") return "Bus";
  if (mode === "featured") return "Featured";
  return "All";
}

function routeBadgeClass(vehicle) {
  if (FEATURED_ROUTES.includes(vehicle.route_short_name)) return "badge featured";
  if (vehicle.route_mode === "brt") return "badge brt";
  return "badge bus";
}

function routeColor(vehicleOrRoute) {
  const shortName = vehicleOrRoute.route_short_name;

  if (shortName === "300") return "#b45309";
  if (shortName === "MP") return "#9333ea";
  if (shortName === "MO") return "#ea580c";
  if (shortName === "MG") return "#16a34a";
  if (shortName === "MT") return "#0f766e";
  if (shortName === "MY") return "#ca8a04";

  if (vehicleOrRoute.route_mode === "brt") return "#7c3aed";
  return "#2563eb";
}

function createBusIcon(vehicle, selected = false) {
  const bg = vehicle.isStale
    ? "#4b5563"
    : vehicle.isStopped
      ? "#6b7280"
      : routeColor(vehicle);

  const border = selected ? "3px solid #111827" : "2px solid white";
  const opacity = vehicle.isStale ? 0.72 : vehicle.isStopped ? 0.82 : 1;

  const statusText = vehicle.isStale
    ? "Stale"
    : vehicle.isStopped
      ? "Stopped"
      : "";

  return L.divIcon({
    className: "",
    html: `
      <div style="display:flex;flex-direction:column;align-items:center;">
        ${statusText
        ? `<div style="
                margin-bottom:4px;
                padding:2px 6px;
                border-radius:999px;
                background:#111827;
                color:white;
                font-size:10px;
                font-weight:700;
                line-height:1.2;
                opacity:0.92;
              ">${statusText}</div>`
        : `<div style="height:18px;"></div>`
      }
        <div style="
          width:${selected ? 36 : 30}px;
          height:${selected ? 36 : 30}px;
          border-radius:10px;
          background:${bg};
          color:white;
          display:flex;
          align-items:center;
          justify-content:center;
          font-size:${selected ? 18 : 16}px;
          border:${border};
          box-shadow:0 2px 8px rgba(0,0,0,0.25);
          opacity:${opacity};
        ">
          🚌
        </div>
      </div>
    `,
    iconSize: [selected ? 40 : 34, selected ? 58 : 52],
    iconAnchor: [selected ? 20 : 17, selected ? 40 : 36],
    // popupAnchor: [0, -28],
    // popupAnchor: [0, -46],
  });
}

function computePlaybackVehicles(historyRows, playbackTimeMs) {
  const results = [];

  for (const vehicle of historyRows) {
    const obs = Array.isArray(vehicle.observations) ? vehicle.observations : [];
    if (obs.length === 0) continue;

    const sorted = [...obs].sort(
      (a, b) => toMillis(a.vehicle_timestamp) - toMillis(b.vehicle_timestamp)
    );

    const latestObservation = sorted[sorted.length - 1];
    const latestObservationMs = toMillis(latestObservation.vehicle_timestamp);

    if (obs.length === 1) {
      results.push({
        ...vehicle,
        lat: latestObservation.lat,
        lon: latestObservation.lon,
        isStopped: true,
        isStale:
          latestObservationMs < playbackTimeMs - STALE_THRESHOLD_SECONDS * 1000,
      });
      continue;
    }

    let prev = sorted[0];
    let next = sorted[sorted.length - 1];

    if (playbackTimeMs <= toMillis(sorted[0].vehicle_timestamp)) {
      prev = sorted[0];
      next = sorted[1];
    } else if (playbackTimeMs >= toMillis(sorted[sorted.length - 1].vehicle_timestamp)) {
      prev = sorted[sorted.length - 2];
      next = sorted[sorted.length - 1];
    } else {
      for (let i = 0; i < sorted.length - 1; i++) {
        const a = sorted[i];
        const b = sorted[i + 1];
        const ta = toMillis(a.vehicle_timestamp);
        const tb = toMillis(b.vehicle_timestamp);

        if (playbackTimeMs >= ta && playbackTimeMs <= tb) {
          prev = a;
          next = b;
          break;
        }
      }
    }

    const t0 = toMillis(prev.vehicle_timestamp);
    const t1 = toMillis(next.vehicle_timestamp);

    let lat = next.lat;
    let lon = next.lon;

    if (t1 > t0 && playbackTimeMs >= t0 && playbackTimeMs <= t1) {
      const ratio = (playbackTimeMs - t0) / (t1 - t0);
      lat = lerp(prev.lat, next.lat, ratio);
      lon = lerp(prev.lon, next.lon, ratio);
    }

    const movedMeters = distanceMeters(prev.lat, prev.lon, next.lat, next.lon);
    const isStopped = movedMeters < STOPPED_THRESHOLD_METERS;
    const isStale =
      latestObservationMs < playbackTimeMs - STALE_THRESHOLD_SECONDS * 1000;

    results.push({
      ...vehicle,
      lat,
      lon,
      isStopped,
      isStale,
      latestObservationTimestamp: latestObservation.vehicle_timestamp,
    });
  }

  return results;
}

function FitToVehicles({ vehicles, fitKey }) {
  const map = useMap();
  const hasFittedRef = useRef(false);

  useEffect(() => {
    if (!vehicles.length || hasFittedRef.current) return;

    const bounds = L.latLngBounds(vehicles.map((v) => [v.lat, v.lon]));
    map.fitBounds(bounds, { padding: [30, 30] });

    if (window.innerWidth > 900) {
      const currentZoom = map.getZoom();
      map.setZoom(Math.min(currentZoom + 1, 15));
    }

    hasFittedRef.current = true;
  }, [vehicles, map]);

  useEffect(() => {
    hasFittedRef.current = false;
  }, [fitKey]);

  return null;
}

function Filters({ mode, setMode }) {
  const modes = [
    { value: "featured", label: "Featured" },
    { value: "brt", label: "BRT / MAX" },
    { value: "bus", label: "Bus" },
    { value: "all", label: "All" },
  ];

  return (
    <div className="filters">
      {modes.map((m) => (
        <button
          key={m.value}
          className={mode === m.value ? "active" : ""}
          onClick={() => setMode(m.value)}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}

function VehicleDrawer({ vehicle, onClose }) {
  const [stops, setStops] = useState([]);
  const [alerts, setAlerts] = useState([]);

  useEffect(() => {
    if (!vehicle?.vehicle_id) {
      setStops([]);
      setAlerts([]);
      return;
    }

    Promise.all([
      fetch(`${API_BASE}/vehicles/${vehicle.vehicle_id}/stops`).then((r) => r.json()),
      fetch(`${API_BASE}/vehicles/${vehicle.vehicle_id}/alerts`).then((r) => r.json()),
    ])
      .then(([stopsData, alertsData]) => {
        setStops(Array.isArray(stopsData) ? stopsData : []);
        setAlerts(Array.isArray(alertsData) ? alertsData : []);
      })
      .catch(() => {
        setStops([]);
        setAlerts([]);
      });
  }, [vehicle]);

  if (!vehicle) {
    return (
      <div className="drawer empty">
        <div className="drawer-header">
          <h2>Calgary Transit Live</h2>
        </div>
        <p>Select a bus to highlight its route and see upcoming stops and alerts.</p>
      </div>
    );
  }

  return (
    <div className="drawer">
      <div className="drawer-header">
        <div>
          <div className={routeBadgeClass(vehicle)}>
            {vehicle.route_short_name} · {vehicle.route_category || modeLabel(vehicle.route_mode)}
          </div>
          <h2>{vehicle.route_long_name}</h2>
          <div className="subtle">{vehicle.trip_headsign}</div>
        </div>
        <button className="close-btn" onClick={onClose}>×</button>
      </div>

      <div className="meta-grid">
        <div>
          <div className="meta-label">Vehicle</div>
          <div>{vehicle.vehicle_id}</div>
        </div>
        <div>
          <div className="meta-label">Trip</div>
          <div>{vehicle.trip_id}</div>
        </div>
        <div>
          <div className="meta-label">Playback status</div>
          <div>
            {vehicle.isStale
              ? "Stale"
              : vehicle.isStopped
                ? "Stopped"
                : "Moving"}
          </div>
        </div>
        <div>
          <div className="meta-label">Mode</div>
          <div>{modeLabel(vehicle.route_mode)}</div>
        </div>
      </div>

      <h3>Upcoming stops</h3>
      <div className="list">
        {stops.length === 0 && (
          <div className="list-item">No stop predictions currently available.</div>
        )}
        {stops.slice(0, 8).map((s) => (
          <div key={`${s.trip_id}-${s.stop_sequence}`} className="list-item">
            <div className="title">
              {s.stop_sequence}. {s.stop_name}
            </div>
            <div className="meta">
              Stop {s.stop_id} · Arrival{" "}
              {s.arrival_time ? String(s.arrival_time).replace("T", " ") : "-"}
            </div>
          </div>
        ))}
      </div>

      <h3>Alerts</h3>
      <div className="list">
        {alerts.length === 0 && (
          <div className="list-item">No active route alerts.</div>
        )}
        {alerts.map((a) => (
          <div key={`${a.feed_entity_id}-${a.stop_id || ""}`} className="list-item">
            <div className="title">
              {a.route_short_name}
              {a.stop_name ? ` · ${a.stop_name}` : ""}
            </div>
            <div
              className="alert-html"
              dangerouslySetInnerHTML={{ __html: a.description_html || "" }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}



function App() {
  const [mode, setMode] = useState("featured");
  const [vehicleHistory, setVehicleHistory] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [routePaths, setRoutePaths] = useState([]);
  const [selectedVehicle, setSelectedVehicle] = useState(null);
  const [lastHistoryFetchMs, setLastHistoryFetchMs] = useState(null);
  const [refreshAgeSeconds, setRefreshAgeSeconds] = useState(0);
  const [latestDataTimestampMs, setLatestDataTimestampMs] = useState(null);
  const [historyFetchedAtMs, setHistoryFetchedAtMs] = useState(null);
  const [selectedContext, setSelectedContext] = useState(null);
  const [baseMap, setBaseMap] = useState("dark");
  // const [density, setDensity] = useState("all");


  useEffect(() => {
    const interval = setInterval(() => {
      if (!lastHistoryFetchMs) {
        setRefreshAgeSeconds(0);
        return;
      }
      setRefreshAgeSeconds(Math.max(0, Math.floor((Date.now() - lastHistoryFetchMs) / 1000)));
    }, 1000);

    return () => clearInterval(interval);
  }, [lastHistoryFetchMs]);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [historyRes, pathRes] = await Promise.all([
          // fetch(`${API_BASE}/vehicles/history?mode=${mode}&window_minutes=${HISTORY_WINDOW_MINUTES}`),
          fetch(`${API_BASE}/vehicles/history?mode=${mode}&window_minutes=${HISTORY_WINDOW_MINUTES}`),
          // fetch(`${API_BASE}/vehicles/history?mode=${mode}&density=${density}&window_minutes=${HISTORY_WINDOW_MINUTES}`),
          fetch(
            selectedVehicle?.route_short_name
              ? `${API_BASE}/routes/paths?mode=${mode}&routes=${encodeURIComponent(
                selectedVehicle.route_short_name
              )}`
              : `${API_BASE}/routes/paths?mode=featured`
          ),
        ]);

        const historyData = await historyRes.json();
        const pathData = await pathRes.json();

        let latestMs = null;

        if (Array.isArray(historyData)) {
          for (const vehicle of historyData) {
            const obs = Array.isArray(vehicle.observations) ? vehicle.observations : [];
            for (const point of obs) {
              const ms = toMillis(point.vehicle_timestamp);
              if (latestMs === null || ms > latestMs) latestMs = ms;
            }
          }
        }

        if (cancelled) return;

        setVehicleHistory(Array.isArray(historyData) ? historyData : []);
        setRoutePaths(Array.isArray(pathData) ? pathData : []);
        setLastHistoryFetchMs(Date.now());
        setLatestDataTimestampMs(latestMs);
        setHistoryFetchedAtMs(Date.now());
        setRefreshAgeSeconds(0);
      } catch {
        if (!cancelled) {
          setVehicleHistory([]);
          setRoutePaths([]);
        }
      }
    };

    load();
    const interval = setInterval(load, 30000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [mode, selectedVehicle?.route_short_name]);

  useEffect(() => {
    if (!selectedVehicle?.vehicle_id) {
      setSelectedContext(null);
      return;
    }

    let cancelled = false;

    const loadContext = async () => {
      try {
        const res = await fetch(`${API_BASE}/vehicles/${selectedVehicle.vehicle_id}/context`);
        const data = await res.json();
        if (!cancelled) {
          setSelectedContext(data);
        }
      } catch {
        if (!cancelled) {
          setSelectedContext(null);
        }
      }
    };

    loadContext();

    return () => {
      cancelled = true;
    };
  }, [selectedVehicle?.vehicle_id]);

  useEffect(() => {
    const tick = () => {
      if (!vehicleHistory.length || !latestDataTimestampMs || !historyFetchedAtMs) {
        setVehicles([]);
        if (selectedVehicle) setSelectedVehicle(null);
        return;
      }

      const elapsedSinceFetchMs = Date.now() - historyFetchedAtMs;

      const uncappedPlaybackTimeMs =
        latestDataTimestampMs -
        PLAYBACK_DELAY_SECONDS * 1000 +
        elapsedSinceFetchMs;

      const maxPlaybackTimeMs = latestDataTimestampMs - 5000;

      const playbackTimeMs = Math.min(uncappedPlaybackTimeMs, maxPlaybackTimeMs);

      const playbackVehicles = computePlaybackVehicles(vehicleHistory, playbackTimeMs);
      setVehicles(playbackVehicles);

      if (selectedVehicle) {
        const updatedSelected = playbackVehicles.find(
          (v) => v.vehicle_id === selectedVehicle.vehicle_id
        );
        setSelectedVehicle(updatedSelected || null);
      }
    };

    tick();
    const animationInterval = setInterval(tick, 1000);

    return () => clearInterval(animationInterval);
  }, [
    vehicleHistory,
    latestDataTimestampMs,
    historyFetchedAtMs,
    selectedVehicle?.vehicle_id,
  ]);

  const center = useMemo(() => [51.0447, -114.0719], []);
  const countLabel = `${vehicles.length} active buses`;

  return (
    <div className="app">
      <div className="topbar">
        <div className="topbar-text">
          <h1>Calgary Transit Live</h1>
          <div className="subtle">
            Delayed playback ~75s · tap a bus to highlight its route and view stops/alerts
          </div>
        </div>
        <div className="status-group">
          <div className="status-pill">{countLabel}</div>
          <div className="status-subtle">Last refresh {refreshAgeSeconds}s ago</div>
        </div>
      </div>

      <div className="filter-row">
        <Filters mode={mode} setMode={setMode} />
      </div>

      <div className="basemap-row">
        <div className="basemap-label">Map</div>
        <div className="basemap-switcher">
          {Object.entries(TILE_CONFIG).map(([key, cfg]) => (
            <button
              key={key}
              className={baseMap === key ? "active" : ""}
              onClick={() => setBaseMap(key)}
            >
              {cfg.label}
            </button>
          ))}
        </div>
      </div>



      <div className="content">
        <div className="map-wrap">
          <MapContainer center={center} zoom={11} className="map">



            <TileLayer
              attribution={TILE_CONFIG[baseMap].attribution}
              url={TILE_CONFIG[baseMap].url}
            />

            <FitToVehicles vehicles={vehicles} fitKey={mode} />


            {routePaths.map((route) => (
              <RouteLine
                key={`${route.route_short_name}-${route.shape_id}`}
                route={route}
                highlighted={selectedVehicle?.route_short_name === route.route_short_name}
              />
            ))}

            {selectedVehicle && selectedContext && (
              <SelectedCorridor
                context={selectedContext}
                vehicle={selectedVehicle}
              />
            )}

            {vehicles.map((v) => (
              <Marker
                key={v.vehicle_id}
                position={[v.lat, v.lon]}
                icon={createBusIcon(v, selectedVehicle?.vehicle_id === v.vehicle_id)}
                eventHandlers={{
                  click: () => setSelectedVehicle(v),
                }}
              >

              </Marker>
            ))}
          </MapContainer>
        </div>


        <div className={`drawer-wrap ${selectedVehicle ? "has-selection" : ""}`}>
          <VehicleDrawer
            vehicle={selectedVehicle}
            onClose={() => setSelectedVehicle(null)}
          />
        </div>
      </div>
    </div>
  );
}

export default App;