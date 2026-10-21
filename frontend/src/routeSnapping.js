// Moves buses along their route's shape between two reports instead of in a straight
// line, so they stay on the road at corners. Reports are about 45 s apart, and a
// straight line between them cuts across blocks.
//
// Each bus is matched to its own trip's shape when the page has loaded it (`tripShapes`,
// by shape_id from vehicle history). Otherwise it uses the one shape the page draws per
// route (the direction a recent bus was on): buses going the other way usually share
// the same streets, and where the directions split a report lies off that shape and
// the bus keeps the straight line.

const METERS_PER_DEGREE_LAT = 111_132;
const CALGARY_LATITUDE = 51.05;
const METERS_PER_DEGREE_LON = METERS_PER_DEGREE_LAT * Math.cos((CALGARY_LATITUDE * Math.PI) / 180);


function buildShape(route) {
  const positions = Array.isArray(route?.positions) ? route.positions : [];
  const xs = [];
  const ys = [];
  const along = [];
  for (const [lat, lon] of positions) {
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;
    const x = lon * METERS_PER_DEGREE_LON;
    const y = lat * METERS_PER_DEGREE_LAT;
    const last = xs.length - 1;
    if (last >= 0 && x === xs[last] && y === ys[last]) continue;
    along.push(last < 0 ? 0 : along[last] + Math.hypot(x - xs[last], y - ys[last]));
    xs.push(x);
    ys.push(y);
  }
  return xs.length >= 2 ? { id: `${route.route_short_name}|${route.shape_id}`, xs, ys, along } : null;
}


// The nearest point of each pass of the shape within `maxOffset` metres, as
// { along, offset }. A shape that runs past the point once gives one; a loop or an
// out-and-back gives one per pass. Using only the nearest point of each pass keeps a
// report in the same place for the pair before it and the pair after it, so buses do
// not jump when one pair of reports hands over to the next.
function nearbyProjections(shape, x, y, maxOffset) {
  const { xs, ys, along } = shape;
  const projections = [];
  for (let index = 0; index < xs.length - 1; index += 1) {
    const dx = xs[index + 1] - xs[index];
    const dy = ys[index + 1] - ys[index];
    const lengthSquared = dx * dx + dy * dy;
    const t = Math.max(0, Math.min(1, ((x - xs[index]) * dx + (y - ys[index]) * dy) / lengthSquared));
    projections.push({
      along: along[index] + t * Math.sqrt(lengthSquared),
      offset: Math.hypot(xs[index] + dx * t - x, ys[index] + dy * t - y),
    });
  }
  const passes = [];
  let pass = null;
  for (const projection of projections) {
    if (projection.offset > maxOffset) {
      pass = null;
    } else if (!pass) {
      pass = projection;
      passes.push(pass);
    } else if (projection.offset < pass.offset) {
      Object.assign(pass, projection);
    }
  }
  return passes;
}


function pointAt(shape, distance) {
  const { xs, ys, along } = shape;
  let low = 0;
  let high = along.length - 1;
  while (high - low > 1) {
    const middle = (low + high) >> 1;
    if (along[middle] <= distance) low = middle;
    else high = middle;
  }
  const span = along[high] - along[low];
  const t = span > 0 ? Math.max(0, Math.min(1, (distance - along[low]) / span)) : 0;
  return {
    x: xs[low] + (xs[high] - xs[low]) * t,
    y: ys[low] + (ys[high] - ys[low]) * t,
    dx: xs[high] - xs[low],
    dy: ys[high] - ys[low],
  };
}


export function createRouteSnapper(routePaths, {
  tripShapes = [],
  maxOffsetMeters = 35,
  maxDetourRatio = 2.5,
  detourSlackMeters = 120,
  // Faster than any Calgary bus: a road distance needing more than this between two
  // reports means the wrong pass of a loop, so that pass is skipped.
  maxSpeedMetersPerSecond = 30,
  cacheLimit = 5000,
} = {}) {
  const shapesByRoute = new Map();
  for (const route of Array.isArray(routePaths) ? routePaths : []) {
    const shape = buildShape(route);
    if (!shape) continue;
    const name = String(route.route_short_name);
    shapesByRoute.set(name, [...(shapesByRoute.get(name) || []), shape]);
  }
  const shapesById = new Map();
  for (const tripShape of Array.isArray(tripShapes) ? tripShapes : []) {
    const shape = buildShape({ route_short_name: "trip", ...tripShape });
    if (shape) shapesById.set(String(tripShape.shape_id), shape);
  }
  // A pair of reports always maps to the same stretch of road, so remember it.
  const pairs = new Map();

  function snapPair(shapes, previous, next) {
    if (!shapes) return null;
    const ax = previous.lon * METERS_PER_DEGREE_LON;
    const ay = previous.lat * METERS_PER_DEGREE_LAT;
    const bx = next.lon * METERS_PER_DEGREE_LON;
    const by = next.lat * METERS_PER_DEGREE_LAT;
    const straight = Math.hypot(bx - ax, by - ay);
    const seconds = (Date.parse(next.vehicle_timestamp) - Date.parse(previous.vehicle_timestamp)) / 1000;
    const maxGap = Math.min(
      straight * maxDetourRatio + detourSlackMeters,
      Number.isFinite(seconds) && seconds > 0 ? Math.max(straight, maxSpeedMetersPerSecond * seconds) : Infinity,
    );
    let best = null;
    for (const shape of shapes) {
      const fromCandidates = nearbyProjections(shape, ax, ay, maxOffsetMeters);
      const toCandidates = nearbyProjections(shape, bx, by, maxOffsetMeters);
      // Choose the closest pair along the road: on a loop or out-and-back shape the
      // same street appears twice, and the far pass would send the bus the long way.
      for (const from of fromCandidates) {
        for (const to of toCandidates) {
          const gap = Math.abs(to.along - from.along);
          if (gap > maxGap) continue;
          const score = gap + from.offset + to.offset;
          if (!best || score < best.score) best = { shape, from: from.along, to: to.along, score };
        }
      }
    }
    return best;
  }

  return {
    // Position `ratio` of the way from `previous` to `next` along the road, or null
    // when the reports do not fit the route's shape (use the straight line then).
    position(vehicle, previous, next, ratio) {
      const key = [
        vehicle.route_short_name, vehicle.shape_id, vehicle.vehicle_id, vehicle.trip_id,
        previous.vehicle_timestamp, previous.lat, previous.lon,
        next.vehicle_timestamp, next.lat, next.lon,
      ].join("|");
      let pair = pairs.get(key);
      if (pair === undefined) {
        const ownShape = vehicle.shape_id ? shapesById.get(String(vehicle.shape_id)) : null;
        pair = (ownShape && snapPair([ownShape], previous, next))
          || snapPair(shapesByRoute.get(String(vehicle.route_short_name)), previous, next);
        if (pairs.size >= cacheLimit) pairs.clear();
        pairs.set(key, pair);
      }
      if (!pair) return null;
      const point = pointAt(pair.shape, pair.from + (pair.to - pair.from) * ratio);
      // Heading follows the road, in the bus's direction of travel along the shape.
      const sign = pair.to >= pair.from ? 1 : -1;
      const heading = (Math.atan2(point.dx * sign, point.dy * sign) * 180) / Math.PI;
      return {
        lat: point.y / METERS_PER_DEGREE_LAT,
        lon: point.x / METERS_PER_DEGREE_LON,
        heading: (heading + 360) % 360,
      };
    },
  };
}
