import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import AntPath from "./AntPath";

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

const sampleRoutes = [
  {
    id: "lrt-202",
    label: "Route 202 – CTrain Blue Line style sample",
    mode: "lrt",
    color: "#2563eb",
    points: [
      [51.0447, -114.0719],
      [51.0478, -114.0615],
      [51.0529, -114.0518],
      [51.0568, -114.0417],
      [51.0598, -114.0304],
    ],
  },
  {
    id: "brt-300",
    label: "Route 300 – BRT sample",
    mode: "brt",
    color: "#7c3aed",
    points: [
      [51.1134, -114.0206],
      [51.1011, -114.0315],
      [51.0881, -114.0471],
      [51.0724, -114.0613],
      [51.0530, -114.0714],
    ],
  },
  {
    id: "max-purple",
    label: "MAX Purple style sample",
    mode: "brt",
    color: "#9333ea",
    points: [
      [51.0452, -113.9981],
      [51.0462, -114.0152],
      [51.0470, -114.0328],
      [51.0478, -114.0501],
      [51.0484, -114.0710],
    ],
  },
];

export default function TestRoutesPage() {
  return (
    <div style={{ height: "100vh", width: "100%" }}>
      <MapContainer
        center={[51.0447, -114.0719]}
        zoom={11}
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {sampleRoutes.map((route) => (
          <AntPath
            key={route.id}
            positions={route.points}
            options={{
              color: route.color,
              pulseColor: "#ffffff",
              weight: route.mode === "lrt" ? 6 : 5,
              delay: route.mode === "lrt" ? 900 : 700,
            }}
          />
        ))}

        {sampleRoutes.map((route) => (
          <Marker key={`${route.id}-start`} position={route.points[0]}>
            <Popup>{route.label} — start</Popup>
          </Marker>
        ))}

        {sampleRoutes.map((route) => (
          <Marker
            key={`${route.id}-end`}
            position={route.points[route.points.length - 1]}
          >
            <Popup>{route.label} — end</Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}