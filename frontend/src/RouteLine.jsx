import { memo } from "react";
import { Polyline } from "react-leaflet";
import { routeColor } from "./routeStyle";

// Memoised: the map re-renders every second for bus positions, and hundreds of
// unchanged route lines should not restyle on each of those renders.
function RouteLine({ route, highlighted = false }) {
  if (!route?.positions?.length) return null;

  return (
    <Polyline
      positions={route.positions}
      pathOptions={{
        color: routeColor(route),
        weight: highlighted ? 7 : 4,
        opacity: highlighted ? 0.12 : 0.72,
      }}
      interactive={false}
    />
  );
}

export default memo(RouteLine);
