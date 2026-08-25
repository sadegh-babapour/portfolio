import assert from "node:assert/strict";
import test from "node:test";

import {
  computePlaybackVehicles,
  monotonicPlaybackTime,
} from "../src/transitPlayback.js";


test("refreshed history never moves the playback clock backwards", () => {
  assert.equal(
    monotonicPlaybackTime({
      previousTimeMs: 10_000,
      latestDataTimeMs: 80_000,
      fetchedAtMs: 20_000,
      nowMs: 20_000,
      delaySeconds: 75,
    }),
    10_000,
  );
});

test("playback uses the first observation before the history window begins", () => {
  const [vehicle] = computePlaybackVehicles([
    {
      vehicle_id: "bus-1",
      trip_id: "trip-1",
      observations: [
        { vehicle_timestamp: "2026-08-24T12:00:30Z", lat: 51, lon: -114 },
        { vehicle_timestamp: "2026-08-24T12:01:00Z", lat: 52, lon: -115 },
      ],
    },
  ], Date.parse("2026-08-24T12:00:00Z"));

  assert.equal(vehicle.lat, 51);
  assert.equal(vehicle.lon, -114);
});

test("moving observations produce an interpolated position and direction", () => {
  const [vehicle] = computePlaybackVehicles([
    {
      vehicle_id: "bus-1",
      trip_id: "trip-1",
      observations: [
        { vehicle_timestamp: "2026-08-24T12:00:00Z", lat: 51, lon: -114 },
        { vehicle_timestamp: "2026-08-24T12:01:00Z", lat: 51.01, lon: -114 },
      ],
    },
  ], Date.parse("2026-08-24T12:00:30Z"));

  assert.equal(vehicle.lat, 51.004999999999995);
  assert.equal(Math.round(vehicle.heading), 0);
  assert.equal(vehicle.isStopped, false);
});
