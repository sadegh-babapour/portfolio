import { useEffect } from "react";
import { CircleMarker, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet-ant-path";

function routeColor(route) {
  const shortName = route.route_short_name;

  if (shortName === "300") return "#b45309";
  if (shortName === "MP") return "#9333ea";
  if (shortName === "MO") return "#ea580c";
  if (shortName === "MG") return "#16a34a";
  if (shortName === "MT") return "#0f766e";
  if (shortName === "MY") return "#ca8a04";

  if (route.route_mode === "brt") return "#7c3aed";
  return "#2563eb";
}

export default function SelectedRouteAntPath({ route, enabled = true }) {
  const map = useMap();

  useEffect(() => {
    if (!map || !enabled || !route?.positions?.length) return;

    const antPolyline = L.polyline.antPath(route.positions, {
      delay: 850,
      dashArray: [16, 20],
      weight: 6,
      color: routeColor(route),
      pulseColor: "#ffffff",
      paused: false,
      reverse: false,
      hardwareAccelerated: true,
      opacity: 0.9,
    });

    antPolyline.addTo(map);

    return () => {
      map.removeLayer(antPolyline);
    };
  }, [map, route, enabled]);

  if (!enabled || !route?.positions?.length) return null;

  const start = route.positions[0];
  const end = route.positions[route.positions.length - 1];

  return (
    <>
      <CircleMarker
        center={start}
        radius={6}
        pathOptions={{
          color: "#111827",
          fillColor: "#10b981",
          fillOpacity: 0.9,
          weight: 2,
        }}
      />
      <CircleMarker
        center={end}
        radius={6}
        pathOptions={{
          color: "#111827",
          fillColor: "#ef4444",
          fillOpacity: 0.9,
          weight: 2,
        }}
      />
    </>
  );
}