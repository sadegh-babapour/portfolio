import { useEffect, useState } from "react";


export default function TransitSearch({
  apiBase,
  activeRoute,
  onClearRoute,
  onSelectRoute,
  onSelectStop,
  onLocationResolved,
  onNearbyStopsResolved,
  nearbyCount,
  onClearNearby,
}) {
  const [query, setQuery] = useState("");
  const [routes, setRoutes] = useState([]);
  const [stops, setStops] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [locationLoading, setLocationLoading] = useState(false);
  const [locationMessage, setLocationMessage] = useState("");

  useEffect(() => {
    const normalized = query.trim();
    if (!open || normalized.length < 1) {
      return undefined;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const encoded = encodeURIComponent(normalized);
        const [routeResponse, stopResponse] = await Promise.all([
          fetch(`${apiBase}/routes/search?q=${encoded}`, { signal: controller.signal }),
          fetch(`${apiBase}/stops/search?q=${encoded}`, { signal: controller.signal }),
        ]);
        if (!routeResponse.ok || !stopResponse.ok) throw new Error("Search unavailable");
        const [routeRows, stopRows] = await Promise.all([
          routeResponse.json(),
          stopResponse.json(),
        ]);
        setRoutes(Array.isArray(routeRows) ? routeRows : []);
        setStops(Array.isArray(stopRows) ? stopRows : []);
      } catch (error) {
        if (error.name !== "AbortError") {
          setRoutes([]);
          setStops([]);
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 250);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [apiBase, open, query]);

  const chooseRoute = (route) => {
    setQuery(route.route_short_name);
    setOpen(false);
    setLoading(false);
    onSelectRoute(route);
  };
  const chooseStop = (stop) => {
    setQuery(stop.stop_code || stop.stop_name);
    setOpen(false);
    setLoading(false);
    onSelectStop(stop);
  };

  const findNearby = () => {
    if (!navigator.geolocation) {
      setLocationMessage("Location is unavailable in this browser. Search for a stop instead.");
      setOpen(false);
      return;
    }
    setLocationLoading(true);
    setLocationMessage("");
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        const location = [coords.latitude, coords.longitude];
        onLocationResolved?.(location);
        try {
          const response = await fetch(`${apiBase}/stops/nearby`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              lat: coords.latitude,
              lon: coords.longitude,
              limit: 8,
              radius_meters: 800,
            }),
          });
          if (!response.ok) throw new Error("Nearby stops unavailable");
          const rows = await response.json();
          const nearbyRows = Array.isArray(rows) ? rows : [];
          setQuery("");
          setRoutes([]);
          setStops([]);
          setOpen(false);
          onNearbyStopsResolved?.(nearbyRows);
          setLocationMessage(
            nearbyRows.length
              ? `Showing ${nearbyRows.length} stops within 800 m. Tap a stop marker on the map.`
              : "No Calgary stops were found within 800 m.",
          );
        } catch {
          onNearbyStopsResolved?.([]);
          setLocationMessage("Nearby stops are unavailable. Search by stop name or number.");
          setOpen(false);
        } finally {
          setLocationLoading(false);
        }
      },
      () => {
        setLocationLoading(false);
        setLocationMessage("Location was not shared. You can still search by stop name or number.");
        setOpen(false);
      },
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 300_000 },
    );
  };

  return (
    <div className="transit-search" role="search">
      <label className="sr-only" htmlFor="transit-search-input">
        Search Calgary routes or stops
      </label>
      <div className="search-input-row">
        <span aria-hidden="true">⌕</span>
        <input
          id="transit-search-input"
          type="search"
          value={query}
          placeholder="Route 23, destination, or stop"
          autoComplete="off"
          aria-expanded={open}
          aria-controls="transit-search-results"
          onFocus={() => setOpen(true)}
          onChange={(event) => {
            const nextQuery = event.target.value;
            setQuery(nextQuery);
            setOpen(true);
            if (!nextQuery.trim()) {
              setRoutes([]);
              setStops([]);
              setLoading(false);
            }
            if (nextQuery.trim()) {
              setLocationMessage("");
              onClearNearby?.();
            }
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setOpen(false);
              setLoading(false);
            }
          }}
        />
        <button
          type="button"
          className="nearby-button"
          onClick={findNearby}
          disabled={locationLoading}
        >
          {locationLoading ? "Locating…" : "Near me"}
        </button>
        {activeRoute && (
          <button
            type="button"
            className="search-clear"
            onClick={() => {
              setQuery("");
              setRoutes([]);
              setStops([]);
              setLoading(false);
              onClearRoute();
            }}
          >
            All routes
          </button>
        )}
      </div>
      {locationMessage && (
        <div className="nearby-status" role="status">
          <span>{locationMessage}</span>
          {nearbyCount > 0 && (
            <button
              type="button"
              onClick={() => {
                setLocationMessage("");
                onClearNearby?.();
              }}
            >
              Clear
            </button>
          )}
        </div>
      )}
      {open && query.trim() && (
        <div id="transit-search-results" className="search-results">
          {loading && <div className="search-message">Searching…</div>}
          {!loading && routes.length === 0 && stops.length === 0 && (
            <div className="search-message">No matching active routes or stops.</div>
          )}
          {routes.length > 0 && (
            <div className="search-group">
              <div className="search-heading">Active routes</div>
              {routes.map((route) => (
                <button
                  type="button"
                  key={route.route_short_name}
                  className="search-result"
                  onClick={() => chooseRoute(route)}
                >
                  <strong>{route.route_short_name}</strong>
                  <span>
                    {route.route_long_name} · {route.active_vehicle_count} active
                  </span>
                  {route.headsigns?.length > 0 && (
                    <small>Toward {route.headsigns.slice(0, 3).join(" / ")}</small>
                  )}
                </button>
              ))}
            </div>
          )}
          {stops.length > 0 && (
            <div className="search-group">
              <div className="search-heading">Stops</div>
              {stops.map((stop) => (
                <button
                  type="button"
                  key={stop.stop_id}
                  className="search-result"
                  onClick={() => chooseStop(stop)}
                >
                  <strong>{stop.stop_code || "Stop"}</strong>
                  <span>
                    {stop.stop_name}
                    {Number.isFinite(Number(stop.distance_meters))
                      ? ` · ${Number(stop.distance_meters)} m away`
                      : ""}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
