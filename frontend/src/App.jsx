import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CircleMarker,
  MapContainer,
  Marker,
  Pane,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
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
import { defaultCorridorStop, upcomingStopById } from "./routeGeometry";
import { isShortBlankMapTap } from "./mapInteraction";
import { routeColor } from "./routeStyle";
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
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: "&copy; OpenStreetMap contributors",
    label: "Light",
    className: "",
  },
  dark: {
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: "&copy; OpenStreetMap contributors",
    label: "Dark",
    className: "osm-dark-tiles",
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
    iconSize: [selected ? 40 : 34, selected ? 58 : 52],
    iconAnchor: [selected ? 20 : 17, selected ? 42 : 38],
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

function FitNearbyStops({ location, stops }) {
  const map = useMap();

  useEffect(() => {
    if (!location || !Array.isArray(stops) || stops.length === 0) return;
    const points = [location, ...stops.map((stop) => [
      Number(stop.stop_lat),
      Number(stop.stop_lon),
    ])].filter((point) => point.every(Number.isFinite));
    if (points.length < 2) return;
    map.fitBounds(L.latLngBounds(points), {
      animate: true,
      duration: 0.8,
      maxZoom: 16,
      padding: [44, 44],
    });
  }, [location, map, stops]);

  return null;
}

function MapSelectionGesture({ enabled, onClear }) {
  const map = useMap();
  const gestureRef = useRef(null);

  useEffect(() => {
    const container = map.getContainer();
    const pointerDown = (event) => {
      gestureRef.current = {
        pointerId: event.pointerId,
        startedAt: performance.now(),
        startX: event.clientX,
        startY: event.clientY,
        durationMs: null,
        moved: false,
      };
    };
    const pointerMove = (event) => {
      const gesture = gestureRef.current;
      if (!gesture || gesture.pointerId !== event.pointerId) return;
      if (Math.hypot(event.clientX - gesture.startX, event.clientY - gesture.startY) > 8) {
        gesture.moved = true;
      }
    };
    const pointerUp = (event) => {
      const gesture = gestureRef.current;
      if (!gesture || gesture.pointerId !== event.pointerId) return;
      gesture.durationMs = performance.now() - gesture.startedAt;
    };
    const pointerCancel = () => {
      gestureRef.current = null;
    };

    container.addEventListener("pointerdown", pointerDown, true);
    container.addEventListener("pointermove", pointerMove, true);
    container.addEventListener("pointerup", pointerUp, true);
    container.addEventListener("pointercancel", pointerCancel, true);
    return () => {
      container.removeEventListener("pointerdown", pointerDown, true);
      container.removeEventListener("pointermove", pointerMove, true);
      container.removeEventListener("pointerup", pointerUp, true);
      container.removeEventListener("pointercancel", pointerCancel, true);
    };
  }, [map]);

  useMapEvents({
    click(event) {
      const gesture = gestureRef.current;
      const target = event.originalEvent?.target;
      const interactiveTarget = target instanceof Element
        && Boolean(target.closest(".leaflet-interactive, .leaflet-marker-icon, .leaflet-control"));
      if (enabled && isShortBlankMapTap({
        durationMs: gesture?.durationMs,
        moved: gesture?.moved,
        interactiveTarget,
      })) {
        onClear();
      }
      gestureRef.current = null;
    },
  });

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

function Filters({ mode, setMode, disabled = false }) {
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
          disabled={disabled}
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
  trackedDestinationStop,
  onSelectStop,
  onClose,
  serviceStatus,
  following,
  onToggleFollow,
  trackingLocked,
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
  }, [vehicle?.vehicle_id]);

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

      {trackingLocked ? (
        <div className="tracking-lock-note">
          This bus remains selected. The map fits it once, then keeps your pan and zoom choices.
        </div>
      ) : (
        <button
          type="button"
          className={`follow-btn ${following ? "active" : ""}`}
          aria-pressed={following}
          onClick={onToggleFollow}
        >
          {following ? "Following bus" : "Follow bus on map"}
        </button>
      )}

      {trackedDestinationStop && (
        <div className="tracking-target" role="status">
          <strong>{selectedTargetStop ? "Tracking this bus to your stop" : "Tracking destination is no longer upcoming"}</strong>
          <span>
            {trackedDestinationStop.stop_name}
            {trackedDestinationStop.stop_code
              ? ` · Stop ${trackedDestinationStop.stop_code}`
              : ""}
          </span>
        </div>
      )}

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
            disabled={trackingLocked}
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
  const [routes, setRoutes] = useState([]);
  const [selectedRoute, setSelectedRoute] = useState("all");
  const [loading, setLoading] = useState(true);
  const [favoriteError, setFavoriteError] = useState("");
  const [favoriteLoading, setFavoriteLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const stopId = encodeURIComponent(stop.stop_id);
        const [arrivalResult, routeResult] = await Promise.allSettled([
          fetch(`${API_BASE}/stops/${stopId}/arrivals?window_minutes=180`),
          fetch(`${API_BASE}/stops/${stopId}/routes`),
        ]);
        if (!cancelled && arrivalResult.status === "fulfilled" && arrivalResult.value.ok) {
          const rows = await arrivalResult.value.json();
          setArrivals(Array.isArray(rows) ? rows : []);
        }
        if (!cancelled && routeResult.status === "fulfilled" && routeResult.value.ok) {
          const rows = await routeResult.value.json();
          setRoutes(Array.isArray(rows) ? rows : []);
        }
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

  const routeOptions = useMemo(() => {
    const byRoute = new Map();
    for (const route of [...routes, ...arrivals]) {
      const routeNumber = String(route.route_short_name || "").trim();
      if (routeNumber && !byRoute.has(routeNumber)) {
        byRoute.set(routeNumber, {
          route_short_name: routeNumber,
          route_long_name: route.route_long_name || "",
        });
      }
    }
    return [...byRoute.values()].sort((left, right) =>
      left.route_short_name.localeCompare(right.route_short_name, undefined, { numeric: true })
    );
  }, [arrivals, routes]);
  const visibleArrivals = selectedRoute === "all"
    ? arrivals
    : arrivals.filter((arrival) => arrival.route_short_name === selectedRoute);

  return (
    <div className="drawer">
      <div className="drawer-header">
        <div>
          <div className="badge stop">Stop {stop.stop_code || stop.stop_id}</div>
          <h2>{stop.stop_name}</h2>
          <div className="subtle">Next three arrivals per route within three hours</div>
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
      {routeOptions.length > 0 && (
        <div className="stop-route-picker" aria-label="Routes serving this stop">
          <button
            type="button"
            className={selectedRoute === "all" ? "active" : ""}
            onClick={() => setSelectedRoute("all")}
          >
            All
          </button>
          {routeOptions.map((route) => (
            <button
              type="button"
              key={route.route_short_name}
              className={selectedRoute === route.route_short_name ? "active" : ""}
              title={route.route_long_name || undefined}
              onClick={() => setSelectedRoute(route.route_short_name)}
            >
              {route.route_short_name}
            </button>
          ))}
        </div>
      )}
      <div className="list">
        {loading && <div className="list-item">Loading arrivals…</div>}
        {!loading && visibleArrivals.length === 0 && (
          <div className="list-item">
            {selectedRoute === "all"
              ? "No scheduled or live arrivals are available in the next three hours."
              : `No Route ${selectedRoute} arrival is available in the next three hours.`}
          </div>
        )}
        {visibleArrivals.map((arrival) => (
          <button
            type="button"
            key={`${arrival.trip_id}-${arrival.stop_sequence}`}
            className="list-item arrival-choice"
            onClick={() => onTrackArrival(arrival)}
          >
            <span className="arrival-route">{arrival.route_short_name || "Bus"}</span>
            <span>
              <strong>{arrivalLabel(arrival.arrival_time)}</strong>
              <small>
                {arrival.trip_headsign || arrival.route_long_name || "Destination unavailable"}
                {` · ${arrival.prediction_source === "scheduled" ? "Scheduled" : "Live prediction"}`}
              </small>
            </span>
            <span className="arrival-action">
              {arrival.vehicle_id ? "Track" : "Show route"}
            </span>
          </button>
        ))}
      </div>
      <div className="teletext-note">
        <a
          href="https://www.calgarytransit.com/rider-information/rider-tools.html"
          target="_blank"
          rel="noreferrer"
        >
          Calgary Teletext
        </a>
        : send stop number{selectedRoute === "all" ? " and route" : ""}{" "}
        <strong>
          {stop.stop_code || stop.stop_id}
          {selectedRoute === "all" ? " [route]" : ` ${selectedRoute}`}
        </strong>{" "}
        to <strong>74000</strong> for Calgary Transit's official next times.
      </div>
    </div>
  );
}

function SavedStops({ stops, loading, failed, onSelect }) {
  return (
    <div className="saved-stops-row" aria-label="Saved stops">
      <span className="saved-stops-label">Saved stops</span>
      {loading && <span className="subtle">Loading…</span>}
      {!loading && failed && <span className="subtle">Temporarily unavailable.</span>}
      {!loading && !failed && stops.length === 0 && (
        <span className="subtle">Save a stop to keep it here.</span>
      )}
      {stops.map((stop) => (
        <button type="button" key={stop.stop_id} onClick={() => onSelect(stop)}>
          ★ {stop.stop_code || stop.stop_id} · {stop.stop_name}
        </button>
      ))}
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
  const [trackedDestinationStop, setTrackedDestinationStop] = useState(null);
  const [activeRoute, setActiveRoute] = useState(null);
  const [serviceStatus, setServiceStatus] = useState("loading");
  const [baseMap, setBaseMap] = useState("dark");
  const [following, setFollowing] = useState(false);
  const [userLocation, setUserLocation] = useState(null);
  const [nearbyStops, setNearbyStops] = useState([]);
  const [authenticated, setAuthenticated] = useState(false);
  const [favoriteStops, setFavoriteStops] = useState(() => new Set());
  const [favoriteHydration, setFavoriteHydration] = useState({
    key: "",
    stops: [],
    failed: false,
  });
  const playbackTimeRef = useRef(null);
  const pendingVehicleRef = useRef(null);
  const drawerRef = useRef(null);
  const trackingRequested = Boolean(trackedDestinationStop);
  const trackingLocked = trackingRequested && Boolean(selectedVehicle);
  const hasDrawerSelection = Boolean(selectedVehicle || selectedPlaceStop);

  const clearSelection = useCallback(() => {
    pendingVehicleRef.current = null;
    setFollowing(false);
    setSelectedContext(null);
    setSelectedTargetStop(null);
    setSelectedPlaceStop(null);
    setTrackedDestinationStop(null);
    setSelectedVehicle(null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const ids = [...favoriteStops];
    if (!authenticated || ids.length === 0) return undefined;
    const hydrationKey = ids.join(",");
    fetch(`${API_BASE}/stops?ids=${encodeURIComponent(ids.join(","))}`)
      .then((response) => {
        if (!response.ok) throw new Error("Saved stops unavailable");
        return response.json();
      })
      .then((rows) => {
        if (!cancelled) {
          setFavoriteHydration({
            key: hydrationKey,
            stops: Array.isArray(rows) ? rows : [],
            failed: false,
          });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setFavoriteHydration({ key: hydrationKey, stops: [], failed: true });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [authenticated, favoriteStops]);

  useEffect(() => {
    if (!selectedVehicle && !selectedPlaceStop) return undefined;
    const dismissEscape = (event) => {
      if (event.key === "Escape") clearSelection();
    };
    document.addEventListener("keydown", dismissEscape);
    return () => {
      document.removeEventListener("keydown", dismissEscape);
    };
  }, [clearSelection, selectedPlaceStop, selectedVehicle]);

  useEffect(() => {
    if (!hasDrawerSelection || window.innerWidth > 1050) return;
    const frame = window.requestAnimationFrame(() => {
      const drawer = drawerRef.current;
      if (!drawer) return;
      const drawerTop = drawer.getBoundingClientRect().top + window.scrollY;
      const revealTop = Math.max(0, drawerTop - window.innerHeight + 112);
      if (revealTop > window.scrollY) {
        window.scrollTo({ top: revealTop, behavior: "smooth" });
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [hasDrawerSelection, selectedPlaceStop?.stop_id, selectedVehicle?.trip_id, selectedVehicle?.vehicle_id]);

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
          const nextStops = Array.isArray(data.next_stops) ? data.next_stops : [];
          setSelectedContext(data);
          setSelectedTargetStop(
            trackedDestinationStop
              ? upcomingStopById(nextStops, trackedDestinationStop)
              : defaultCorridorStop(nextStops),
          );
        }
      } catch {
        if (!cancelled) {
          setSelectedContext(null);
        }
      }
    };

    loadContext();
    const interval = window.setInterval(loadContext, 15_000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [
    selectedVehicle?.vehicle_id,
    selectedVehicle?.trip_id,
    trackedDestinationStop,
  ]);

  useEffect(() => {
    const tick = () => {
      if (!vehicleHistory.length || !latestDataTimestampMs || !historyFetchedAtMs) {
        setVehicles([]);
        setSelectedVehicle((current) => (current && trackedDestinationStop ? current : null));
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

      const pending = pendingVehicleRef.current;
      if (pending) {
        const requested = playbackVehicles.find(
          (vehicle) => vehicle.vehicle_id === pending.vehicle_id
            && (!pending.trip_id || vehicle.trip_id === pending.trip_id),
        ) || playbackVehicles.find(
          (vehicle) => vehicle.vehicle_id === pending.vehicle_id,
        );
        if (requested) {
          pendingVehicleRef.current = null;
          setSelectedPlaceStop(null);
          setSelectedVehicle(requested);
        }
        return;
      }

      setSelectedVehicle((current) => {
        if (!current) return current;
        const updatedSelected = playbackVehicles.find(
          (vehicle) => vehicle.vehicle_id === current.vehicle_id
            && vehicle.trip_id === current.trip_id
        );
        return updatedSelected || (trackedDestinationStop ? current : null);
      });
    };

    tick();
    const animationInterval = setInterval(tick, 1000);

    return () => clearInterval(animationInterval);
  }, [
    vehicleHistory,
    latestDataTimestampMs,
    historyFetchedAtMs,
    trackedDestinationStop,
  ]);

  const center = useMemo(() => [51.0447, -114.0719], []);
  const selectedPlacePoint = useMemo(() => {
    if (!selectedPlaceStop) return null;
    return [Number(selectedPlaceStop.stop_lat), Number(selectedPlaceStop.stop_lon)];
  }, [selectedPlaceStop]);
  const focusPoint = selectedPlacePoint || (nearbyStops.length ? null : userLocation);
  const visibleVehicles = trackingLocked ? [selectedVehicle] : vehicles;
  const visibleRoutePaths = trackingLocked
    ? routePaths.filter((route) => route.route_short_name === selectedVehicle.route_short_name)
    : routePaths;
  const beaconColor = baseMap === "dark" ? "#f8fafc" : "#111827";
  const favoriteHydrationKey = [...favoriteStops].join(",");
  const favoriteStopDetails = favoriteHydration.key === favoriteHydrationKey
    ? favoriteHydration.stops
    : [];
  const favoritesLoading = Boolean(favoriteHydrationKey)
    && favoriteHydration.key !== favoriteHydrationKey;
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
          disabled={trackingRequested}
          setMode={(nextMode) => {
            playbackTimeRef.current = null;
            clearSelection();
            setActiveRoute(null);
            setNearbyStops([]);
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
          disabled={trackingRequested}
          activeRoute={activeRoute}
          onClearRoute={() => {
            playbackTimeRef.current = null;
            clearSelection();
            setActiveRoute(null);
          }}
          onSelectRoute={(route) => {
            playbackTimeRef.current = null;
            clearSelection();
            setActiveRoute(route.route_short_name);
            setMode("all");
          }}
          onSelectStop={(stop) => {
            clearSelection();
            setSelectedPlaceStop(stop);
            setActiveRoute(null);
          }}
          onLocationResolved={setUserLocation}
          onNearbyStopsResolved={(stops) => {
            clearSelection();
            setActiveRoute(null);
            setNearbyStops(stops);
          }}
          nearbyCount={nearbyStops.length}
          onClearNearby={() => setNearbyStops([])}
        />
        {trackingRequested && (
          <div className="tracking-search-lock" role="status">
            Close the tracked bus to search or change route filters.
          </div>
        )}
      </div>
      {authenticated && (
        <SavedStops
          stops={favoriteStopDetails}
          loading={favoritesLoading}
          failed={favoriteHydration.key === favoriteHydrationKey && favoriteHydration.failed}
          onSelect={(stop) => {
            clearSelection();
            setSelectedPlaceStop(stop);
            setActiveRoute(null);
          }}
        />
      )}

      <div className="transit-workspace">
        <div className="content">
        <div className="map-wrap">
          <MapContainer center={center} zoom={11} className="map">



            <TileLayer
              key={baseMap}
              attribution={TILE_CONFIG[baseMap].attribution}
              className={TILE_CONFIG[baseMap].className}
              url={TILE_CONFIG[baseMap].url}
            />

            <FitToVehicles vehicles={vehicles} fitKey={`${mode}-${activeRoute || "all"}`} />
            <FollowVehicle vehicle={selectedVehicle} enabled={following && !trackingLocked} />
            <FocusPoint point={focusPoint} />
            <FitNearbyStops location={userLocation} stops={trackingRequested ? [] : nearbyStops} />
            <MapSelectionGesture
              enabled={Boolean(selectedVehicle) && !trackingRequested}
              onClear={clearSelection}
            />

            {userLocation && (
              <Pane name="user-location" style={{ zIndex: 760 }}>
                <CircleMarker
                  center={userLocation}
                  radius={18}
                  interactive={false}
                  className="user-location-pulse"
                  pathOptions={{
                    color: beaconColor,
                    fillColor: beaconColor,
                    fillOpacity: 0.12,
                    opacity: 0.42,
                    weight: 2,
                  }}
                />
                <CircleMarker
                  center={userLocation}
                  radius={7}
                  interactive={false}
                  pathOptions={{
                    color: baseMap === "dark" ? "#111827" : "#ffffff",
                    fillColor: beaconColor,
                    fillOpacity: 0.94,
                    weight: 3,
                  }}
                />
              </Pane>
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

            {!trackingRequested && nearbyStops.length > 0 && (
              <Pane name="nearby-stops" style={{ zIndex: 740 }}>
                {nearbyStops.map((stop) => (
                  <CircleMarker
                    key={stop.stop_id}
                    center={[Number(stop.stop_lat), Number(stop.stop_lon)]}
                    radius={10}
                    pathOptions={{
                      color: "#ffffff",
                      fillColor: "#0f766e",
                      fillOpacity: 0.95,
                      weight: 3,
                    }}
                    eventHandlers={{
                      click: () => {
                        clearSelection();
                        setSelectedPlaceStop(stop);
                      },
                    }}
                    bubblingMouseEvents={false}
                  >
                    <Tooltip direction="top" offset={[0, -8]}>
                      Stop {stop.stop_code || stop.stop_id} · {stop.stop_name}
                    </Tooltip>
                  </CircleMarker>
                ))}
              </Pane>
            )}


            {visibleRoutePaths.map((route) => (
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
                trackingLocked={trackingLocked}
              />
            )}

            {visibleVehicles.map((v) => (
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
                    if (trackingRequested) return;
                    clearSelection();
                    setSelectedVehicle(v);
                  },
                }}
                bubblingMouseEvents={false}
              />
            ))}
          </MapContainer>
        </div>

        </div>
        <div
          ref={drawerRef}
          className={`drawer-wrap ${selectedVehicle || selectedPlaceStop ? "has-selection" : ""}`}
        >
          {(selectedVehicle || selectedPlaceStop) && <div className="drawer-handle" aria-hidden="true" />}
          {selectedPlaceStop ? (
            <StopDrawer
              key={selectedPlaceStop.stop_id}
              stop={selectedPlaceStop}
              onClose={clearSelection}
              onTrackArrival={(arrival) => {
                playbackTimeRef.current = null;
                setSelectedContext(null);
                setSelectedTargetStop(null);
                setSelectedVehicle(null);
                setActiveRoute(arrival.route_short_name);
                setMode("all");
                if (arrival.vehicle_id) {
                  pendingVehicleRef.current = {
                    vehicle_id: arrival.vehicle_id,
                    trip_id: arrival.trip_id,
                  };
                  setTrackedDestinationStop(selectedPlaceStop);
                } else {
                  pendingVehicleRef.current = null;
                  setTrackedDestinationStop(null);
                }
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
              trackedDestinationStop={trackedDestinationStop}
              onSelectStop={setSelectedTargetStop}
              serviceStatus={serviceStatus}
              following={following}
              onToggleFollow={() => setFollowing((value) => !value)}
              trackingLocked={trackingLocked}
              onClose={clearSelection}
            />
          )}
        </div>
      </div>
      <div className="data-source-note" role="note">
        <span>
          Live positions and arrival predictions come from the City of Calgary and may be
          delayed, incomplete, or unavailable. Bizqlab displays the latest usable source data.
          Live LRT vehicle locations are not shown because the City feed does not provide them.
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
          <span>Map © OpenStreetMap contributors</span>
        </span>
      </div>
    </div>
  );
}

export default App;
