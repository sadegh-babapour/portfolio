// GTFS shapes are dense (a point every few metres). Douglas-Peucker simplification
// with a 2 m tolerance and coordinates rounded to 5 decimals (about 1 m) cut the
// payload by about 80% with no visible change on the map.
const METERS_PER_DEGREE_LAT = 111_132;
const CALGARY_LATITUDE = 51.05;
const METERS_PER_DEGREE_LON = METERS_PER_DEGREE_LAT * Math.cos((CALGARY_LATITUDE * Math.PI) / 180);
const SIMPLIFY_TOLERANCE_METERS = 2;

function roundCoordinate(value) {
  return Math.round(value * 1e5) / 1e5;
}

// positions: [[lat, lon], ...] in shape order.
function simplifyPath(positions, toleranceMeters = SIMPLIFY_TOLERANCE_METERS) {
  if (positions.length <= 2) {
    return positions.map(([lat, lon]) => [roundCoordinate(lat), roundCoordinate(lon)]);
  }
  const xs = positions.map(([, lon]) => lon * METERS_PER_DEGREE_LON);
  const ys = positions.map(([lat]) => lat * METERS_PER_DEGREE_LAT);
  const keep = new Uint8Array(positions.length);
  keep[0] = 1;
  keep[positions.length - 1] = 1;
  const stack = [[0, positions.length - 1]];

  while (stack.length > 0) {
    const [first, last] = stack.pop();
    const dx = xs[last] - xs[first];
    const dy = ys[last] - ys[first];
    const lengthSquared = dx * dx + dy * dy;
    let farthest = -1;
    let farthestDistance = 0;
    for (let index = first + 1; index < last; index += 1) {
      const t = lengthSquared > 0
        ? Math.max(0, Math.min(1, ((xs[index] - xs[first]) * dx + (ys[index] - ys[first]) * dy) / lengthSquared))
        : 0;
      const distance = Math.hypot(xs[first] + dx * t - xs[index], ys[first] + dy * t - ys[index]);
      if (distance > farthestDistance) {
        farthestDistance = distance;
        farthest = index;
      }
    }
    if (farthestDistance > toleranceMeters) {
      keep[farthest] = 1;
      stack.push([first, farthest], [farthest, last]);
    }
  }

  const simplified = [];
  for (let index = 0; index < positions.length; index += 1) {
    if (keep[index]) simplified.push([roundCoordinate(positions[index][0]), roundCoordinate(positions[index][1])]);
  }
  return simplified;
}

module.exports = {
  SIMPLIFY_TOLERANCE_METERS,
  simplifyPath,
};
