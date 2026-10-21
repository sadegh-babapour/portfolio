import assert from "node:assert/strict";
import test from "node:test";

import { readFileSync } from "node:fs";

import {
  computePlaybackVehicles,
  createPlaybackClock,
  distanceMeters,
} from "../src/transitPlayback.js";


const replayFixture = JSON.parse(
  readFileSync(new URL("./fixtures/playback_replay_2026-10-21.json", import.meta.url), "utf8"),
);

// Rebuild what each recorded fetch returned.
function replaySnapshots() {
  return replayFixture.snapshots.map(({ fetched_at: fetchedAt, ranges }) => ({
    fetchedAtMs: Date.parse(fetchedAt),
    rows: replayFixture.vehicles
      .filter((vehicle) => ranges[`${vehicle.vehicle_id}|${vehicle.trip_id}`])
      .map((vehicle) => {
        const [first, last] = ranges[`${vehicle.vehicle_id}|${vehicle.trip_id}`];
        return {
          vehicle_id: vehicle.vehicle_id,
          trip_id: vehicle.trip_id,
          route_short_name: vehicle.route_short_name,
          observations: vehicle.observations
            .filter(([timestamp]) => timestamp >= first && timestamp <= last)
            .map(([timestamp, lat, lon]) => ({ vehicle_timestamp: timestamp, lat, lon })),
        };
      }),
  }));
}

function latestTimestampMs(rows) {
  return Math.max(...rows.flatMap((row) => row.observations.map((point) => Date.parse(point.vehicle_timestamp))));
}


test("a refresh without newer data does not stall the playback clock", () => {
  const clock = createPlaybackClock({ marginSeconds: 10 });
  clock.observe({ latestDataTimeMs: 100_000, fetchedAtMs: 110_000 });
  clock.observe({ latestDataTimeMs: 100_000, fetchedAtMs: 140_000 });
  const first = clock.tick(140_000);
  clock.observe({ latestDataTimeMs: 100_000, fetchedAtMs: 141_000 });
  const second = clock.tick(141_000);

  assert.ok(second > first, "the clock keeps moving across a refresh with the same data");
  assert.ok(second - first <= 1_100, "and it moves at about wall-clock speed");
});

test("a new feed batch does not make the playback clock jump", () => {
  const clock = createPlaybackClock({ marginSeconds: 0 });
  clock.observe({ latestDataTimeMs: 100_000, fetchedAtMs: 140_000 });
  let previous = clock.tick(140_000);
  for (let nowMs = 141_000; nowMs <= 200_000; nowMs += 1_000) {
    if (nowMs === 170_000) clock.observe({ latestDataTimeMs: 160_000, fetchedAtMs: nowMs });
    const current = clock.tick(nowMs);
    assert.ok(current >= previous, "never backwards");
    assert.ok(current - previous <= 1_100, `step at ${nowMs} was ${current - previous} ms`);
    previous = current;
  }
});

test("the playback clock never runs past the newest data", () => {
  const clock = createPlaybackClock({ marginSeconds: 0, firstLagPaddingSeconds: 0, liveBufferSeconds: 5 });
  clock.observe({ latestDataTimeMs: 100_000, fetchedAtMs: 101_000 });
  let time = null;
  for (let nowMs = 101_000; nowMs <= 400_000; nowMs += 1_000) time = clock.tick(nowMs);

  assert.equal(time, 95_000);
});

test("reset snaps the playback clock to its target on the next tick", () => {
  const clock = createPlaybackClock({ marginSeconds: 10, firstLagPaddingSeconds: 0 });
  clock.observe({ latestDataTimeMs: 100_000, fetchedAtMs: 130_000 });
  clock.tick(130_000);
  clock.observe({ latestDataTimeMs: 50_000, fetchedAtMs: 131_000 });
  clock.reset();

  // Slowest recent batch: 131 s - 50 s = 81 s behind; minus the 10 s margin.
  assert.equal(clock.tick(131_000), 40_000);
});

test("replayed live data plays smoothly with few frozen buses", () => {
  const snapshots = replaySnapshots();
  const clock = createPlaybackClock();
  const lastShown = new Map();
  let previousTimeMs = null;
  let clockJumps = 0;
  let frozenTicks = 0;
  let movingTicks = 0;
  const steps = [];

  for (let index = 0; index < snapshots.length - 1; index += 1) {
    const { fetchedAtMs, rows } = snapshots[index];
    clock.observe({ latestDataTimeMs: latestTimestampMs(rows), fetchedAtMs });
    for (let nowMs = fetchedAtMs; nowMs < snapshots[index + 1].fetchedAtMs; nowMs += 1_000) {
      const timeMs = clock.tick(nowMs);
      if (previousTimeMs !== null && timeMs - previousTimeMs > 1_500) clockJumps += 1;
      previousTimeMs = timeMs;
      for (const vehicle of computePlaybackVehicles(rows, timeMs)) {
        const key = `${vehicle.vehicle_id}|${vehicle.trip_id}`;
        const before = lastShown.get(key);
        lastShown.set(key, vehicle);
        // Skip the first two minutes while the clock learns the feed's batch cycle.
        if (!before || index < 4 || vehicle.isStopped) continue;
        const step = distanceMeters(before.lat, before.lon, vehicle.lat, vehicle.lon);
        movingTicks += 1;
        if (step < 0.01) frozenTicks += 1;
        steps.push(step);
      }
    }
  }

  // The 2026-10-20 clock scored 23 jumps, 45% frozen, p99 162 m and max 859 m on this recording.
  steps.sort((a, b) => a - b);
  const p99 = steps[Math.floor(steps.length * 0.99)];
  assert.equal(clockJumps, 0);
  assert.ok(frozenTicks / movingTicks < 0.05, `${frozenTicks} of ${movingTicks} moving ticks frozen`);
  assert.ok(p99 < 40, `99th-percentile one-second step ${Math.round(p99)} m`);
  assert.ok(steps.at(-1) < 300, `largest one-second step ${Math.round(steps.at(-1))} m`);
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
