export function routeAvailability(arrivals, routeNumber) {
  const routeArrivals = arrivals.filter(
    (arrival) => String(arrival.route_short_name || "") === String(routeNumber),
  );
  const vehicleIds = [...new Set(
    routeArrivals.map((arrival) => arrival.vehicle_id).filter(Boolean),
  )];
  const representative = routeArrivals[0] || null;

  return {
    availability: vehicleIds.length > 0
      ? "live"
      : representative
        ? "trip"
        : "none",
    vehicleIds,
    tripId: representative?.trip_id || null,
    arrival: representative,
  };
}

export function routeAvailabilityLabel(availability) {
  if (availability === "live") return "Live";
  if (availability === "trip") return "Trip only";
  return "No upcoming";
}

export function isSameTripSelection(current, next) {
  return Boolean(next?.tripId) && next.tripId === current?.tripId;
}

export function mergeRefreshedRouteSelection(current, refreshed) {
  if (!current || current.route !== refreshed?.route) return current;
  const currentVehicles = current.vehicleIds || [];
  const refreshedVehicles = refreshed.vehicleIds || [];
  if (
    current.tripId === refreshed.tripId
    && current.availability === refreshed.availability
    && currentVehicles.length === refreshedVehicles.length
    && currentVehicles.every((id, index) => id === refreshedVehicles[index])
  ) {
    return current;
  }
  return refreshed;
}
