// import { useEffect } from "react";
// import { useMap } from "react-leaflet";
// import L from "leaflet";
// import "leaflet-ant-path";

// function routeColor(route) {
//   if (route.route_short_name === "300") return "#b45309";
//   if (["MP", "MO", "MG", "MT", "MY"].includes(route.route_short_name)) return "#7c3aed";
//   if (route.route_mode === "brt") return "#7c3aed";
//   return "#2563eb";
// }

// export default function AntPath({ route, highlighted = false }) {
//   const map = useMap();

//   useEffect(() => {
//     if (!map || !route?.positions?.length) return;

//     const antPolyline = L.polyline.antPath(route.positions, {
//       delay: highlighted ? 700 : 950,
//       dashArray: highlighted ? [16, 20] : [12, 24],
//       weight: highlighted ? 7 : 4,
//       color: routeColor(route),
//       pulseColor: "#ffffff",
//       paused: false,
//       reverse: false,
//       hardwareAccelerated: true,
//       opacity: highlighted ? 0.95 : 0.55,
//     });

//     antPolyline.addTo(map);

//     return () => {
//       map.removeLayer(antPolyline);
//     };
//   }, [map, route, highlighted]);

//   return null;
// }
import { useEffect } from "react";
import { useMap } from "react-leaflet";
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

export default function AntPath({ route, highlighted = false }) {
  const map = useMap();

  useEffect(() => {
    if (!map || !route?.positions?.length) return;


    const antPolyline = L.polyline.antPath(route.positions, {
      delay: 2500,
      dashArray: [50, 20],
      weight: 3,
      color: routeColor(route),
      pulseColor: "#ffffff",
      paused: false,
      reverse: false,
      hardwareAccelerated: true,
      opacity: 0.28,
    });

    antPolyline.addTo(map);

    return () => {
      map.removeLayer(antPolyline);
    };
  }, [map, route, highlighted]);

  return null;
}