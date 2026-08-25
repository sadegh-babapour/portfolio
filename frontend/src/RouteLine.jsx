import { Polyline } from "react-leaflet";
import { routeColor } from "./routeStyle";

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
