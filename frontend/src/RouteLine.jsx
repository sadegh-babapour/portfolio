import { Polyline } from "react-leaflet";

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

export default function RouteLine({ route, highlighted = false }) {
  if (!route?.positions?.length) return null;

  return (
    <Polyline
      positions={route.positions}
      pathOptions={{
        color: routeColor(route),
        weight: highlighted ? 5 : 3,
        opacity: highlighted ? 0.7 : 0.5,
      }}
    />
  );
}