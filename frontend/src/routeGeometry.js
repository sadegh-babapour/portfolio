function validCoordinate(point) {
  return Array.isArray(point)
    && Number.isFinite(point[0])
    && Number.isFinite(point[1]);
}


export function shapeCoordinates(shapePoints) {
  if (!Array.isArray(shapePoints)) return [];
  return shapePoints
    .map((point) => [Number(point.shape_pt_lat), Number(point.shape_pt_lon)])
    .filter(validCoordinate);
}


export function projectToPolyline(points, target, startSegment = 0) {
  if (!validCoordinate(target) || !Array.isArray(points) || points.length < 2) return null;
  const longitudeScale = Math.cos(target[0] * Math.PI / 180);
  let best = null;

  for (let index = Math.max(0, startSegment); index < points.length - 1; index += 1) {
    const first = points[index];
    const second = points[index + 1];
    if (!validCoordinate(first) || !validCoordinate(second)) continue;
    const firstX = first[1] * longitudeScale;
    const firstY = first[0];
    const deltaX = (second[1] - first[1]) * longitudeScale;
    const deltaY = second[0] - first[0];
    const lengthSquared = deltaX ** 2 + deltaY ** 2;
    const rawRatio = lengthSquared === 0
      ? 0
      : (((target[1] * longitudeScale - firstX) * deltaX)
        + ((target[0] - firstY) * deltaY)) / lengthSquared;
    const ratio = Math.max(0, Math.min(1, rawRatio));
    const point = [
      first[0] + (second[0] - first[0]) * ratio,
      first[1] + (second[1] - first[1]) * ratio,
    ];
    const distanceSquared =
      ((target[1] - point[1]) * longitudeScale) ** 2
      + (target[0] - point[0]) ** 2;
    if (best === null || distanceSquared < best.distanceSquared) {
      best = { point, segmentIndex: index, ratio, distanceSquared };
    }
  }
  return best;
}


export function shapeSegmentToStop(shapePoints, vehicle, stop) {
  const points = shapeCoordinates(shapePoints);
  const vehiclePoint = [Number(vehicle?.lat), Number(vehicle?.lon)];
  const stopPoint = [Number(stop?.stop_lat), Number(stop?.stop_lon)];
  if (points.length < 2 || !validCoordinate(vehiclePoint) || !validCoordinate(stopPoint)) {
    return [];
  }
  const vehicleProjection = projectToPolyline(points, vehiclePoint);
  if (!vehicleProjection) return [];
  const stopProjection = projectToPolyline(points, stopPoint, vehicleProjection.segmentIndex);
  if (!stopProjection) return [];

  const segment = [vehicleProjection.point];
  for (
    let index = vehicleProjection.segmentIndex + 1;
    index <= stopProjection.segmentIndex;
    index += 1
  ) {
    segment.push(points[index]);
  }
  segment.push(stopProjection.point);
  return segment.filter((point, index) => (
    index === 0
    || point[0] !== segment[index - 1][0]
    || point[1] !== segment[index - 1][1]
  ));
}
