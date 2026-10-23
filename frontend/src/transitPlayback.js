// Why the buses glide instead of jumping (docs/lessons/09).
//
// Calgary's feed is late and lumpy: each bus reports about every 45 s, reports arrive in
// batches about once a minute, and they are 40-100 s old when we fetch them. Drawing each
// report as it arrives makes buses sit still, then leap.
//
// So the map plays the recent past, like a video with a buffer:
// 1. createPlaybackClock (below) runs a clock about 2 minutes behind real time, far enough
//    back that both reports around "playback now" have almost always arrived. It moves at
//    wall-clock speed, nudges itself by at most 10% toward its target, and never goes back.
// 2. computePlaybackVehicles places each bus between its report before and its report
//    after the playback time; routeSnapping.js bends that path along the road.
// 3. App.jsx recomputes positions once a second, and a 1 s CSS transition (App.css,
//    .bus-marker-glide) slides each marker to its new spot, so motion is continuous.
//    glideGuard.js pauses the slide while Leaflet zooms; reduced-motion turns it off.
const EARTH_RADIUS_METERS = 6371000;


export function toMillis(value) {
  return new Date(value).getTime();
}


export function distanceMeters(lat1, lon1, lat2, lon2) {
  const toRadians = (degrees) => (degrees * Math.PI) / 180;
  const latitudeDelta = toRadians(lat2 - lat1);
  const longitudeDelta = toRadians(lon2 - lon1);
  const firstLatitude = toRadians(lat1);
  const secondLatitude = toRadians(lat2);
  const haversine =
    Math.sin(latitudeDelta / 2) ** 2
    + Math.cos(firstLatitude)
      * Math.cos(secondLatitude)
      * Math.sin(longitudeDelta / 2) ** 2;
  return 2 * EARTH_RADIUS_METERS * Math.atan2(Math.sqrt(haversine), Math.sqrt(1 - haversine));
}


export function bearingDegrees(lat1, lon1, lat2, lon2) {
  const toRadians = (degrees) => (degrees * Math.PI) / 180;
  const firstLatitude = toRadians(lat1);
  const secondLatitude = toRadians(lat2);
  const longitudeDelta = toRadians(lon2 - lon1);
  const y = Math.sin(longitudeDelta) * Math.cos(secondLatitude);
  const x =
    Math.cos(firstLatitude) * Math.sin(secondLatitude)
    - Math.sin(firstLatitude) * Math.cos(secondLatitude) * Math.cos(longitudeDelta);
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}


// A playback clock that runs at wall-clock speed instead of restarting on every refresh.
// The feed publishes in batches (about every 60 s here) while the page refreshes every
// 30 s, so "time since the last fetch" resets without new data and froze the map, then
// jumped it. This clock stays a steady distance behind the slowest recent batch and
// steers gently (at most `maxRateAdjust`) toward it rather than freezing or jumping.
export function createPlaybackClock({
  marginSeconds = 45,
  liveBufferSeconds = 5,
  lagWindowSeconds = 300,
  firstLagPaddingSeconds = 30,
  maxRateAdjust = 0.1,
  steerSeconds = 30,
  snapSeconds = 60,
} = {}) {
  let lagSamples = [];
  let latestDataTimeMs = null;
  let timeMs = null;
  let lastNowMs = null;

  return {
    observe({ latestDataTimeMs: latest, fetchedAtMs }) {
      if (!Number.isFinite(latest) || !Number.isFinite(fetchedAtMs)) return;
      latestDataTimeMs = latest;
      lagSamples.push({ atMs: fetchedAtMs, lagMs: fetchedAtMs - latest });
      lagSamples = lagSamples.filter((sample) => sample.atMs > fetchedAtMs - lagWindowSeconds * 1000);
    },

    // Snap to the target on the next tick (for example after the route filter changes).
    reset() {
      timeMs = null;
      lastNowMs = null;
    },

    tick(nowMs) {
      if (!Number.isFinite(nowMs) || latestDataTimeMs === null || lagSamples.length === 0) return null;
      // One sample cannot show the batch cycle yet, so pad it.
      const lagMs = Math.max(...lagSamples.map((sample) => sample.lagMs))
        + (lagSamples.length === 1 ? firstLagPaddingSeconds * 1000 : 0);
      const ceilingMs = latestDataTimeMs - liveBufferSeconds * 1000;
      const targetMs = Math.min(nowMs - lagMs - marginSeconds * 1000, ceilingMs);

      if (timeMs === null || Math.abs(targetMs - timeMs) > snapSeconds * 1000) {
        timeMs = targetMs;
      } else {
        const elapsedMs = Math.max(0, nowMs - lastNowMs);
        const steer = (targetMs - timeMs) / (steerSeconds * 1000);
        const rate = 1 + Math.max(-maxRateAdjust, Math.min(maxRateAdjust, steer));
        // Never run past the newest data, and never move backwards.
        timeMs = Math.min(timeMs + elapsedMs * rate, Math.max(timeMs, ceilingMs));
      }
      lastNowMs = nowMs;
      return timeMs;
    },
  };
}


export function computePlaybackVehicles(
  historyRows,
  playbackTimeMs,
  { stoppedThresholdMeters = 20, staleThresholdSeconds = 120, snapper = null } = {},
) {
  const results = [];

  for (const vehicle of historyRows) {
    const observations = Array.isArray(vehicle.observations) ? vehicle.observations : [];
    if (observations.length === 0) continue;
    const sorted = [...observations].sort(
      (first, second) => toMillis(first.vehicle_timestamp) - toMillis(second.vehicle_timestamp),
    );
    const latest = sorted.at(-1);
    const latestTimeMs = toMillis(latest.vehicle_timestamp);

    if (sorted.length === 1 || playbackTimeMs <= toMillis(sorted[0].vehicle_timestamp)) {
      const first = sorted[0];
      results.push({
        ...vehicle,
        lat: first.lat,
        lon: first.lon,
        heading: null,
        isStopped: true,
        isStale: latestTimeMs < playbackTimeMs - staleThresholdSeconds * 1000,
        latestObservationTimestamp: latest.vehicle_timestamp,
      });
      continue;
    }

    let previous = sorted.at(-2);
    let next = latest;
    if (playbackTimeMs < latestTimeMs) {
      for (let index = 0; index < sorted.length - 1; index += 1) {
        if (playbackTimeMs <= toMillis(sorted[index + 1].vehicle_timestamp)) {
          previous = sorted[index];
          next = sorted[index + 1];
          break;
        }
      }
    }

    const previousTimeMs = toMillis(previous.vehicle_timestamp);
    const nextTimeMs = toMillis(next.vehicle_timestamp);
    const ratio = nextTimeMs > previousTimeMs && playbackTimeMs < nextTimeMs
      ? Math.max(0, (playbackTimeMs - previousTimeMs) / (nextTimeMs - previousTimeMs))
      : 1;
    const movedMeters = distanceMeters(previous.lat, previous.lon, next.lat, next.lon);
    // Follow the road when the reports fit the route's shape (routeSnapping.js).
    const onRoad = snapper && movedMeters >= stoppedThresholdMeters
      ? snapper.position(vehicle, previous, next, ratio)
      : null;

    results.push({
      ...vehicle,
      lat: onRoad ? onRoad.lat : previous.lat + (next.lat - previous.lat) * ratio,
      lon: onRoad ? onRoad.lon : previous.lon + (next.lon - previous.lon) * ratio,
      heading: onRoad
        ? onRoad.heading
        : movedMeters >= 5
          ? bearingDegrees(previous.lat, previous.lon, next.lat, next.lon)
          : null,
      isStopped: movedMeters < stoppedThresholdMeters,
      isStale: latestTimeMs < playbackTimeMs - staleThresholdSeconds * 1000,
      latestObservationTimestamp: latest.vehicle_timestamp,
    });
  }

  return results;
}
