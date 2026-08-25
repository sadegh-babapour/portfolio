import { useEffect, useMemo, useState } from "react";
import {
  MapContainer,
  Marker,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { alertText } from "./alertText";
import "./App.css";

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

const API_BASE = "http://localhost:4000/api";

function FitToVehicles({ vehicles }) {
  const map = useMap();

  useEffect(() => {
    if (!vehicles.length) return;
    const bounds = L.latLngBounds(vehicles.map((v) => [v.lat, v.lon]));
    map.fitBounds(bounds, { padding: [30, 30] });
  }, [vehicles, map]);

  return null;
}

function Filters({ mode, setMode }) {
  const modes = [
    { value: "all", label: "All" },
    { value: "lrt", label: "LRT" },
    { value: "brt", label: "BRT / MAX" },
    { value: "bus", label: "Bus" },
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

function VehicleDetails({ vehicleId }) {
  const [stops, setStops] = useState([]);
  const [alerts, setAlerts] = useState([]);

  useEffect(() => {
    if (!vehicleId) {
      return;
    }

    Promise.all([
      fetch(`${API_BASE}/vehicles/${vehicleId}/stops`).then((r) => r.json()),
      fetch(`${API_BASE}/vehicles/${vehicleId}/alerts`).then((r) => r.json()),
    ])
      .then(([stopsData, alertsData]) => {
        setStops(Array.isArray(stopsData) ? stopsData : []);
        setAlerts(Array.isArray(alertsData) ? alertsData : []);
      })
      .catch(() => {
        setStops([]);
        setAlerts([]);
      });
  }, [vehicleId]);

  if (!vehicleId) {
    return <div className="panel">Select a vehicle.</div>;
  }

  const header = stops[0];

  return (
    <div className="panel">
      <h2>Vehicle {vehicleId}</h2>
      {header && (
        <>
          <div><strong>Route:</strong> {header.route_short_name} — {header.route_long_name}</div>
          <div><strong>Headsign:</strong> {header.trip_headsign}</div>
          <h3>Upcoming stops</h3>
          <div className="list">
            {stops.slice(0, 10).map((s) => (
              <div key={`${s.trip_id}-${s.stop_sequence}`} className="list-item">
                <div className="title">
                  {s.stop_sequence}. {s.stop_name}
                </div>
                <div className="meta">
                  Stop {s.stop_id} · Arrival {s.arrival_time || "-"}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      <h3>Alerts</h3>
      <div className="list">
        {alerts.length === 0 && <div className="list-item">No active route alerts.</div>}
        {alerts.map((a) => (
          <div key={a.feed_entity_id + "-" + (a.stop_id || "")} className="list-item">
            <div className="title">
              {a.route_short_name} {a.stop_name ? `· ${a.stop_name}` : ""}
            </div>
            {a.header_text && <div className="title">{a.header_text}</div>}
            <div className="alert-text">{alertText(a.description_html)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function DashboardPage() {
  const [mode, setMode] = useState("all");
  const [vehicles, setVehicles] = useState([]);
  const [selectedVehicleId, setSelectedVehicleId] = useState(null);

  useEffect(() => {
    let cancelled = false;

    const load = () => {
      fetch(`${API_BASE}/vehicles?mode=${mode}`)
        .then((r) => r.json())
        .then((data) => {
          if (!cancelled) setVehicles(Array.isArray(data) ? data : []);
        })
        .catch(() => {
          if (!cancelled) setVehicles([]);
        });
    };

    load();
    const interval = setInterval(load, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [mode]);

  const center = useMemo(() => [51.0447, -114.0719], []);

  return (
    <div className="app">
      <div className="topbar">
        <h1>Calgary Transit Live Dashboard</h1>
        <Filters mode={mode} setMode={setMode} />
      </div>

      <div className="layout">
        <div className="map-wrap">
          <MapContainer center={center} zoom={11} className="map">
            <TileLayer
              attribution='&copy; OpenStreetMap contributors'
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <FitToVehicles vehicles={vehicles} />
            {vehicles.map((v) => (
              <Marker
                key={v.vehicle_id}
                position={[v.lat, v.lon]}
                eventHandlers={{
                  click: () => setSelectedVehicleId(v.vehicle_id),
                }}
              >
                <Popup>
                  <div>
                    <strong>Vehicle {v.vehicle_id}</strong>
                    <br />
                    Route: {v.route_short_name} — {v.route_long_name}
                    <br />
                    Headsign: {v.trip_headsign}
                  </div>
                </Popup>
              </Marker>
            ))}
          </MapContainer>
        </div>

        <VehicleDetails vehicleId={selectedVehicleId} />
      </div>
    </div>
  );
}

export default DashboardPage;
