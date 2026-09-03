import assert from "node:assert/strict";
import test from "node:test";

import {
  isSameTripSelection,
  mergeRefreshedRouteSelection,
  routeAvailability,
  routeAvailabilityLabel,
} from "../src/stopRouteSelection.js";

test("route availability exposes only vehicles attached to this stop's arrivals", () => {
  const result = routeAvailability([
    { route_short_name: "77", trip_id: "a", vehicle_id: "1466" },
    { route_short_name: "77", trip_id: "b", vehicle_id: null },
    { route_short_name: "129", trip_id: "c", vehicle_id: "8169" },
  ], "77");

  assert.equal(result.availability, "live");
  assert.deepEqual(result.vehicleIds, ["1466"]);
  assert.equal(result.tripId, "a");
});

test("reselecting an exact trip does not require discarding its loaded path", () => {
  assert.equal(isSameTripSelection({ tripId: "trip-90" }, { tripId: "trip-90" }), true);
  assert.equal(isSameTripSelection({ tripId: "trip-90" }, { tripId: "next-90" }), false);
  assert.equal(isSameTripSelection({ tripId: "trip-90" }, null), false);
});

test("arrival refresh upgrades an open trip-only route when an exact vehicle appears", () => {
  const current = {
    route: "90",
    tripId: "trip-90",
    vehicleIds: [],
    availability: "trip",
  };
  const refreshed = {
    route: "90",
    tripId: "trip-90",
    vehicleIds: ["8106"],
    availability: "live",
  };

  assert.equal(mergeRefreshedRouteSelection(current, refreshed), refreshed);
  assert.equal(
    mergeRefreshedRouteSelection({ ...current, route: "77" }, refreshed).route,
    "77",
  );
});

test("route availability distinguishes schedule-only and no-upcoming routes", () => {
  assert.equal(routeAvailability([
    { route_short_name: "54", trip_id: "scheduled", vehicle_id: null },
  ], "54").availability, "trip");
  assert.equal(routeAvailability([], "706").availability, "none");
  assert.equal(routeAvailabilityLabel("trip"), "Trip only");
  assert.equal(routeAvailabilityLabel("none"), "No upcoming");
});
