import { useEffect, useMemo, useRef, useState } from "react";
import {
  CircleMarker,
  MapContainer,
  Marker,
  TileLayer,
  useMap,
} from "react-leaflet";

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./App.css";
import { alertText } from "./alertText";
import { resolveTransitApiBase } from "./apiConfig";
import RouteLine from "./RouteLine";
import SelectedCorridor from "./SelectedCorridor";
import PortfolioNav from "./PortfolioNav";
import TransitSearch from "./TransitSearch";
import {
  computePlaybackVehicles,
  monotonicPlaybackTime,
  toMillis,
} from "./transitPlayback";



delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

const API_BASE = resolveTransitApiBase(import.meta.env.VITE_TRANSIT_API_BASE_URL);
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

function cookieValue(name) {
  const prefix = `${encodeURIComponent(name)}=`;
  const part = document.cookie.split("; ").find((value) => value.startsWith(prefix));
  return part ? decodeURIComponent(part.slice(prefix.length)) : "";
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
  const markerLabel = String(vehicle.route_short_name || "Bus")
    .replace(/[^a-z0-9-]/gi, "")
    .slice(0, 6) || "Bus";
  const directionArrow = Number.isFinite(vehicle.heading) && !vehicle.isStopped
    ? `<div style="
          height:12px;
          color:${bg};
          font-size:13px;
          line-height:12px;
          transform:rotate(${vehicle.heading}deg);
        ">▲</div>`
    : '<div style="height:12px;"></div>';

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
        ${directionArrow}
        <div style="
          width:${selected ? 36 : 30}px;
          height:${selected ? 36 : 30}px;
          border-radius:10px;
          background:${bg};
          color:white;
          display:flex;
          align-items:center;
          justify-content:center;
          font-family:Arial,sans-serif;
          font-size:${selected ? 13 : 12}px;
          font-weight:800;
          border:${border};
          box-shadow:0 2px 8px rgba(0,0,0,0.25);
          opacity:${opacity};
        ">
          ${markerLabel}
        </div>
      </div>
    `,
    iconSize: [selected ? 40 : 34, selected ? 70 : 64],
    iconAnchor: [selected ? 20 : 17, selected ? 48 : 44],
  });
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

function FollowVehicle({ vehicle, enabled }) {
  const map = useMap();

  useEffect(() => {
    if (!enabled || !vehicle) return;
    map.panTo([vehicle.lat, vehicle.lon], { animate: true, duration: 0.8 });
  }, [enabled, map, vehicle]);

  return null;
}

function FocusPoint({ point, zoom = 16 }) {
  const map = useMap();

  useEffect(() => {
    if (!point || !Number.isFinite(point[0]) || !Number.isFinite(point[1])) return;
    map.flyTo(point, zoom, { animate: true, duration: 0.8 });
  }, [map, point, zoom]);

  return null;
}

function arrivalLabel(value) {
  if (!value) return "Prediction unavailable";
  const arrival = new Date(value);
  const minutes = Math.max(0, Math.ceil((arrival.getTime() - Date.now()) / 60000));
  const time = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Edmonton",
    hour: "numeric",
    minute: "2-digit",
  }).format(arrival);
  return minutes <= 1 ? `Due · ${time}` : `${minutes} min · ${time}`;
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

function VehicleDrawer({
  vehicle,
  context,
  selectedTargetStop,
  onSelectStop,
  onClose,
  serviceStatus,
  following,
  onToggleFollow,
}) {
  const [alerts, setAlerts] = useState([]);
  const stops = Array.isArray(context?.next_stops) ? context.next_stops : [];

  useEffect(() => {
    if (!vehicle?.vehicle_id) {
      return;
    }
    fetch(`${API_BASE}/vehicles/${vehicle.vehicle_id}/alerts`)
      .then((response) => {
        if (!response.ok) throw new Error("Alerts unavailable");
        return response.json();
      })
      .then((alertsData) => setAlerts(Array.isArray(alertsData) ? alertsData : []))
      .catch(() => setAlerts([]));
  }, [vehicle]);

  if (!vehicle) {
    const emptyMessage = serviceStatus === "outside_operating_hours"
      ? "Live playback is offline outside Calgary polling hours (08:00–21:00 America/Edmonton). Please return during service hours."
      : serviceStatus === "degraded" || serviceStatus === "unavailable"
        ? "Live vehicle data is temporarily unavailable. The service is being checked."
        : "Select a bus to highlight its route and see upcoming stops and alerts.";
    return (
      <div className="drawer empty">
        <div className="drawer-header">
          <h2>Calgary Transit Live</h2>
        </div>
        <p>{emptyMessage}</p>
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
          <div className="meta-label">Toward</div>
          <div>{vehicle.trip_headsign || "Destination unavailable"}</div>
        </div>
        <div>
          <div className="meta-label">Playback</div>
          <div>About {PLAYBACK_DELAY_SECONDS} seconds delayed</div>
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

      <button
        type="button"
        className={`follow-btn ${following ? "active" : ""}`}
        aria-pressed={following}
        onClick={onToggleFollow}
      >
        {following ? "Following bus" : "Follow bus on map"}
      </button>

      <h3>Upcoming stops</h3>
      <div className="list">
        {stops.length === 0 && (
          <div className="list-item">No stop predictions currently available.</div>
        )}
        {stops.slice(0, 3).map((s) => (
          <button
            type="button"
            key={`${s.trip_id}-${s.stop_sequence}`}
            className={`list-item stop-choice ${selectedTargetStop?.stop_id === s.stop_id ? "active" : ""}`}
            onClick={() => onSelectStop(s)}
          >
            <div className="title">
              {s.stop_name}
            </div>
            <div className="meta">
              Stop {s.stop_id} · {arrivalLabel(s.arrival_time)}
            </div>
          </button>
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
            {a.header_text && <div className="title">{a.header_text}</div>}
            <div className="alert-text">{alertText(a.description_html)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StopDrawer({
  stop,
  onClose,
  onTrackArrival,
  authenticated,
  favorite,
  onToggleFavorite,
}) {
  const [arrivals, setArrivals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [favoriteError, setFavoriteError] = useState("");
  const [favoriteLoading, setFavoriteLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const response = await fetch(
          `${API_BASE}/stops/${encodeURIComponent(stop.stop_id)}/arrivals`,
        );
        if (!response.ok) throw new Error("Arrivals unavailable");
        const rows = await response.json();
        if (!cancelled) setArrivals(Array.isArray(rows) ? rows : []);
      } catch {
        if (!cancelled) setArrivals([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    const interval = window.setInterval(load, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [stop.stop_id]);

  return (
    <div className="drawer">
      <div className="drawer-header">
        <div>
          <div className="badge stop">Stop {stop.stop_code || stop.stop_id}</div>
          <h2>{stop.stop_name}</h2>
          <div className="subtle">Predicted arrivals in the next 15 minutes</div>
        </div>
        <button className="close-btn" onClick={onClose}>×</button>
      </div>
      {authenticated ? (
        <button
          type="button"
          className={`favorite-btn ${favorite ? "active" : ""}`}
          disabled={favoriteLoading}
          onClick={async () => {
            setFavoriteLoading(true);
            setFavoriteError("");
            try {
              await onToggleFavorite(stop.stop_id);
            } catch {
              setFavoriteError("Could not update this saved stop. Please try again.");
            } finally {
              setFavoriteLoading(false);
            }
          }}
        >
          {favoriteLoading ? "Saving…" : favorite ? "★ Saved stop" : "☆ Save stop"}
        </button>
      ) : (
        <div className="favorite-note">
          <a href="/account">Sign in</a> to save this stop. Nearby location is not stored.
        </div>
      )}
      {favoriteError && <div className="favorite-error">{favoriteError}</div>}
      <div className="list">
        {loading && <div className="list-item">Loading arrivals…</div>}
        {!loading && arrivals.length === 0 && (
          <div className="list-item">No live predictions are currently available.</div>
        )}
        {arrivals.map((arrival) => (
          <button
            type="button"
            key={`${arrival.trip_id}-${arrival.stop_sequence}`}
            className="list-item arrival-choice"
            onClick={() => onTrackArrival(arrival)}
          >
            <span className="arrival-route">{arrival.route_short_name || "Bus"}</span>
            <span>
              <strong>{arrivalLabel(arrival.arrival_time)}</strong>
              <small>{arrival.trip_headsign || arrival.route_long_name}</small>
            </span>
            <span className="arrival-action">
              {arrival.vehicle_id ? "Track" : "Route"}
            </span>
          </button>
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
  const [selectedTargetStop, setSelectedTargetStop] = useState(null);
  const [selectedPlaceStop, setSelectedPlaceStop] = useState(null);
  const [activeRoute, setActiveRoute] = useState(null);
  const [serviceStatus, setServiceStatus] = useState("loading");
  const [baseMap, setBaseMap] = useState("dark");
  const [following, setFollowing] = useState(false);
  const [userLocation, setUserLocation] = useState(null);
  const [authenticated, setAuthenticated] = useState(false);
  const [favoriteStops, setFavoriteStops] = useState(() => new Set());
  const playbackTimeRef = useRef(null);
  const pendingVehicleRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    const loadAccount = async () => {
      try {
        const sessionResponse = await fetch("/api/auth/session", { credentials: "same-origin" });
        if (!sessionResponse.ok) throw new Error("Session unavailable");
        const session = await sessionResponse.json();
        if (cancelled) return;
        setAuthenticated(session.authenticated === true);
        if (session.authenticated === true) {
          try {
            const favoritesResponse = await fetch("/api/auth/favorite-stops", {
              credentials: "same-origin",
            });
            if (!favoritesResponse.ok) throw new Error("Favorites unavailable");
            const payload = await favoritesResponse.json();
            if (!cancelled) setFavoriteStops(new Set(payload.stop_ids || []));
          } catch {
            if (!cancelled) setFavoriteStops(new Set());
          }
        }
      } catch {
        if (!cancelled) {
          setAuthenticated(false);
          setFavoriteStops(new Set());
        }
      }
    };
    loadAccount();
    return () => {
      cancelled = true;
    };
  }, []);

  const toggleFavoriteStop = async (stopId) => {
    const isFavorite = favoriteStops.has(stopId);
    const response = await fetch(
      isFavorite
        ? `/api/auth/favorite-stops/${encodeURIComponent(stopId)}`
        : "/api/auth/favorite-stops",
      {
        method: isFavorite ? "DELETE" : "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": cookieValue("portfolio_auth_csrf"),
        },
        ...(isFavorite ? {} : { body: JSON.stringify({ stop_id: stopId }) }),
      },
    );
    if (!response.ok) throw new Error("Favorite update failed");
    setFavoriteStops((current) => {
      const next = new Set(current);
      if (isFavorite) next.delete(stopId);
      else next.add(stopId);
      return next;
    });
  };


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
      const fetchJson = async (url) => {
        const response = await fetch(url);
        if (!response.ok) {
          throw new Error(`Transit request failed with HTTP ${response.status}`);
        }
        return response.json();
      };

      const [historyResult, pathResult, healthResult] = await Promise.allSettled([
        fetchJson(
          `${API_BASE}/vehicles/history?mode=${activeRoute ? "all" : mode}`
          + `&window_minutes=${HISTORY_WINDOW_MINUTES}`
          + (activeRoute ? `&routes=${encodeURIComponent(activeRoute)}` : "")
        ),
        fetchJson(
          selectedVehicle?.route_short_name
            ? `${API_BASE}/routes/paths?mode=${mode}&routes=${encodeURIComponent(
              selectedVehicle.route_short_name
            )}`
            : activeRoute
              ? `${API_BASE}/routes/paths?mode=all&routes=${encodeURIComponent(activeRoute)}`
              : `${API_BASE}/routes/paths?mode=${mode}`
        ),
        fetchJson(`${API_BASE}/health`),
      ]);

      if (cancelled) return;

      const hasFreshHistory =
        historyResult.status === "fulfilled" && Array.isArray(historyResult.value);
      const hasFreshPaths =
        pathResult.status === "fulfilled" && Array.isArray(pathResult.value);

      if (hasFreshHistory) {
        const historyData = historyResult.value;

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

        setVehicleHistory(historyData);
        setLastHistoryFetchMs(Date.now());
        setLatestDataTimestampMs(latestMs);
        setHistoryFetchedAtMs(Date.now());
        setRefreshAgeSeconds(0);
      }

      if (hasFreshPaths) {
        setRoutePaths(pathResult.value);
      }

      if (!hasFreshHistory) {
        setServiceStatus("unavailable");
      } else if (!hasFreshPaths || healthResult.status === "rejected") {
        setServiceStatus("degraded");
      } else {
        setServiceStatus(healthResult.value?.status || "healthy");
      }
    };

    load();
    const interval = setInterval(load, 30000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [activeRoute, mode, selectedVehicle?.route_short_name]);

  useEffect(() => {
    if (!selectedVehicle?.vehicle_id) {
      return;
    }

    let cancelled = false;

    const loadContext = async () => {
      try {
        const res = await fetch(`${API_BASE}/vehicles/${selectedVehicle.vehicle_id}/context`);
        if (!res.ok) throw new Error(`Vehicle context failed with HTTP ${res.status}`);
        const data = await res.json();
        if (!cancelled) {
          setSelectedContext(data);
          setSelectedTargetStop(Array.isArray(data.next_stops) ? data.next_stops[0] || null : null);
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
  }, [selectedVehicle?.vehicle_id, selectedVehicle?.trip_id]);

  useEffect(() => {
    const tick = () => {
      if (!vehicleHistory.length || !latestDataTimestampMs || !historyFetchedAtMs) {
        setVehicles([]);
        setSelectedVehicle((current) => (current ? null : current));
        return;
      }

      const playbackTimeMs = monotonicPlaybackTime({
        previousTimeMs: playbackTimeRef.current,
        latestDataTimeMs: latestDataTimestampMs,
        fetchedAtMs: historyFetchedAtMs,
        nowMs: Date.now(),
        delaySeconds: PLAYBACK_DELAY_SECONDS,
      });
      if (!Number.isFinite(playbackTimeMs)) return;
      playbackTimeRef.current = playbackTimeMs;

      const playbackVehicles = computePlaybackVehicles(vehicleHistory, playbackTimeMs);
      setVehicles(playbackVehicles);

      setSelectedVehicle((current) => {
        const pending = pendingVehicleRef.current;
        if (pending) {
          const requested = playbackVehicles.find(
            (vehicle) => vehicle.vehicle_id === pending.vehicle_id
              && (!pending.trip_id || vehicle.trip_id === pending.trip_id),
          );
          if (requested) {
            pendingVehicleRef.current = null;
            return requested;
          }
          return current;
        }
        if (!current) return current;
        const updatedSelected = playbackVehicles.find(
          (vehicle) => vehicle.vehicle_id === current.vehicle_id
            && vehicle.trip_id === current.trip_id
        );
        return updatedSelected || null;
      });
    };

    tick();
    const animationInterval = setInterval(tick, 1000);

    return () => clearInterval(animationInterval);
  }, [
    vehicleHistory,
    latestDataTimestampMs,
    historyFetchedAtMs,
  ]);

  const center = useMemo(() => [51.0447, -114.0719], []);
  const selectedPlacePoint = useMemo(() => {
    if (!selectedPlaceStop) return null;
    return [Number(selectedPlaceStop.stop_lat), Number(selectedPlaceStop.stop_lon)];
  }, [selectedPlaceStop]);
  const focusPoint = selectedPlacePoint || userLocation;
  const hasVehicleData = vehicles.length > 0;
  const countLabel = serviceStatus === "outside_operating_hours"
    ? "Outside live hours"
    : (serviceStatus === "degraded" || serviceStatus === "unavailable") && !hasVehicleData
      ? "Live data unavailable"
      : `${vehicles.length} active buses${serviceStatus === "healthy" ? "" : " · degraded"}`;
  const refreshLabel = serviceStatus === "outside_operating_hours"
    ? "Live polling runs 08:00–21:00 Calgary time"
    : `Last refresh ${refreshAgeSeconds}s ago`;

  return (
    <div className="app">
      <PortfolioNav />
      <div className="topbar">
        <div className="topbar-text">
          <h1>Calgary Transit Live</h1>
          <div className="subtle">
            {activeRoute
              ? `Tracking active route ${activeRoute} · choose a bus or stop`
              : "Delayed playback ~75s · search a route or stop, or tap a bus"}
          </div>
        </div>
        <div className="status-group">
          <div className="status-pill">{countLabel}</div>
          <div className="status-subtle">{refreshLabel}</div>
        </div>
      </div>

      <div className="filter-row">
        <Filters
          mode={mode}
          setMode={(nextMode) => {
            playbackTimeRef.current = null;
            setFollowing(false);
            setActiveRoute(null);
            setSelectedPlaceStop(null);
            setMode(nextMode);
          }}
        />
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
      <div className="transit-search-bar">
        <TransitSearch
          apiBase={API_BASE}
          activeRoute={activeRoute}
          onClearRoute={() => {
            playbackTimeRef.current = null;
            pendingVehicleRef.current = null;
            setActiveRoute(null);
            setSelectedContext(null);
            setSelectedTargetStop(null);
            setSelectedVehicle(null);
          }}
          onSelectRoute={(route) => {
            playbackTimeRef.current = null;
            pendingVehicleRef.current = null;
            setFollowing(false);
            setSelectedPlaceStop(null);
            setSelectedContext(null);
            setSelectedTargetStop(null);
            setSelectedVehicle(null);
            setActiveRoute(route.route_short_name);
            setMode("all");
          }}
          onSelectStop={(stop) => {
            pendingVehicleRef.current = null;
            setFollowing(false);
            setSelectedContext(null);
            setSelectedTargetStop(null);
            setSelectedVehicle(null);
            setSelectedPlaceStop(stop);
            setActiveRoute(null);
          }}
          onLocationResolved={setUserLocation}
        />
      </div>

      <div className="content">
        <div className="map-wrap">
          <MapContainer center={center} zoom={11} className="map">



            <TileLayer
              attribution={TILE_CONFIG[baseMap].attribution}
              url={TILE_CONFIG[baseMap].url}
            />

            <FitToVehicles vehicles={vehicles} fitKey={mode} />
            <FollowVehicle vehicle={selectedVehicle} enabled={following} />
            <FocusPoint point={focusPoint} />

            {userLocation && (
              <CircleMarker
                center={userLocation}
                radius={8}
                pathOptions={{
                  color: "#ffffff",
                  fillColor: "#2563eb",
                  fillOpacity: 1,
                  weight: 3,
                }}
              />
            )}

            {selectedPlacePoint && (
              <CircleMarker
                center={selectedPlacePoint}
                radius={10}
                pathOptions={{
                  color: "#111827",
                  fillColor: "#f59e0b",
                  fillOpacity: 0.95,
                  weight: 3,
                }}
              />
            )}


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
                selectedStop={selectedTargetStop}
              />
            )}

            {vehicles.map((v) => (
              <Marker
                key={`${v.vehicle_id}-${v.trip_id}`}
                position={[v.lat, v.lon]}
                icon={createBusIcon(
                  v,
                  selectedVehicle?.vehicle_id === v.vehicle_id
                    && selectedVehicle?.trip_id === v.trip_id,
                )}
                eventHandlers={{
                  click: () => {
                    pendingVehicleRef.current = null;
                    setSelectedContext(null);
                    setSelectedTargetStop(null);
                    setSelectedPlaceStop(null);
                    setFollowing(false);
                    setSelectedVehicle(v);
                  },
                }}
              />
            ))}
          </MapContainer>
        </div>


        <div className={`drawer-wrap ${selectedVehicle || selectedPlaceStop ? "has-selection" : ""}`}>
          {selectedPlaceStop ? (
            <StopDrawer
              key={selectedPlaceStop.stop_id}
              stop={selectedPlaceStop}
              onClose={() => setSelectedPlaceStop(null)}
              onTrackArrival={(arrival) => {
                playbackTimeRef.current = null;
                pendingVehicleRef.current = arrival.vehicle_id
                  ? { vehicle_id: arrival.vehicle_id, trip_id: arrival.trip_id }
                  : null;
                setSelectedPlaceStop(null);
                setSelectedContext(null);
                setSelectedTargetStop(null);
                setSelectedVehicle(null);
                setActiveRoute(arrival.route_short_name);
                setMode("all");
              }}
              authenticated={authenticated}
              favorite={favoriteStops.has(selectedPlaceStop.stop_id)}
              onToggleFavorite={toggleFavoriteStop}
            />
          ) : (
            <VehicleDrawer
              key={selectedVehicle ? `${selectedVehicle.vehicle_id}-${selectedVehicle.trip_id}` : "no-selection"}
              vehicle={selectedVehicle}
              context={selectedContext}
              selectedTargetStop={selectedTargetStop}
              onSelectStop={setSelectedTargetStop}
              serviceStatus={serviceStatus}
              following={following}
              onToggleFollow={() => setFollowing((value) => !value)}
              onClose={() => {
                pendingVehicleRef.current = null;
                setFollowing(false);
                setSelectedContext(null);
                setSelectedTargetStop(null);
                setSelectedVehicle(null);
              }}
            />
          )}
        </div>
      </div>
      <div className="data-source-note" role="note">
        <span>
          Live positions and arrival predictions come from the City of Calgary and may be
          delayed, incomplete, or unavailable. Bizqlab displays the latest usable source data.
        </span>
        <span className="data-source-links">
          <a
            href="https://data.calgary.ca/stories/s/Open-Calgary-Terms-of-Use/u45n-7awa/"
            target="_blank"
            rel="noreferrer"
          >
            City of Calgary Open Government Licence
          </a>
          <span aria-hidden="true">·</span>
          <span>Map © OpenStreetMap/CARTO</span>
        </span>
      </div>
    </div>
  );
}

export default App;
