export function routeColor(vehicleOrRoute = {}) {
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
