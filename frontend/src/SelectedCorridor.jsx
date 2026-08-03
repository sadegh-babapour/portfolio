// import { useEffect, useMemo, useState } from "react";
// import { CircleMarker, Pane, Polyline, useMap } from "react-leaflet";
// import L from "leaflet";
// import "leaflet-ant-path";

// function dist2(a, b) {
//   const dx = a[0] - b[0];
//   const dy = a[1] - b[1];
//   return dx * dx + dy * dy;
// }

// function nearestIndex(points, target) {
//   let bestIdx = 0;
//   let bestDist = Infinity;

//   for (let i = 0; i < points.length; i++) {
//     const d = dist2(points[i], target);
//     if (d < bestDist) {
//       bestDist = d;
//       bestIdx = i;
//     }
//   }

//   return bestIdx;
// }

// function buildLocalShapeSegment(shapePoints, vehicle, nextStops) {
//   const rawPoints = (Array.isArray(shapePoints) ? shapePoints : [])
//     .map((p) => [Number(p.shape_pt_lat), Number(p.shape_pt_lon)])
//     .filter((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]));

//   if (rawPoints.length < 2) return [];

//   const busPoint = [vehicle.lat, vehicle.lon];
//   const busIdx = nearestIndex(rawPoints, busPoint);

//   let orderedPoints = rawPoints;

//   if (nextStops.length > 0) {
//     const nextTarget = [Number(nextStops[0].stop_lat), Number(nextStops[0].stop_lon)];
//     const forwardIdx = Math.min(busIdx + 10, rawPoints.length - 1);
//     const backwardIdx = Math.max(busIdx - 10, 0);

//     const forwardPoint = rawPoints[forwardIdx];
//     const backwardPoint = rawPoints[backwardIdx];

//     const forwardDist = dist2(forwardPoint, nextTarget);
//     const backwardDist = dist2(backwardPoint, nextTarget);

//     if (backwardDist < forwardDist) {
//       orderedPoints = [...rawPoints].reverse();
//     }
//   }

//   const orientedBusIdx = nearestIndex(orderedPoints, busPoint);

//   const start = Math.max(orientedBusIdx - 70, 0);
//   const end = Math.min(orientedBusIdx + 70, orderedPoints.length - 1);

//   return orderedPoints.slice(start, end + 1);
// }

// function makePath(points) {
//   return points.filter((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]));
// }

// export default function SelectedCorridor({ context, vehicle }) {
//   const map = useMap();
//   const [pulseOn, setPulseOn] = useState(true);

//   const previousStops = Array.isArray(context?.previous_stops) ? context.previous_stops : [];
//   const nextStops = Array.isArray(context?.next_stops) ? context.next_stops : [];
//   const shapePoints = Array.isArray(context?.shape_points) ? context.shape_points : [];

//   const localShapeSegment = useMemo(() => {
//     if (!context || !vehicle) return [];
//     return buildLocalShapeSegment(shapePoints, vehicle, nextStops);
//   }, [context, vehicle, shapePoints, nextStops]);

//   useEffect(() => {
//     const interval = setInterval(() => {
//       setPulseOn((v) => !v);
//     }, 700);

//     return () => clearInterval(interval);
//   }, []);

//   useEffect(() => {
//     if (!map || !context || !vehicle) return;

//     const behindPath = makePath([
//       ...previousStops.map((s) => [Number(s.stop_lat), Number(s.stop_lon)]),
//       [vehicle.lat, vehicle.lon],
//     ]);

//     const aheadPath = makePath([
//       [vehicle.lat, vehicle.lon],
//       ...nextStops.map((s) => [Number(s.stop_lat), Number(s.stop_lon)]),
//     ]);

//     const behindLayer =
//       behindPath.length >= 2
//         ? L.polyline.antPath(behindPath, {
//             delay: 650,
//             dashArray: [16, 18],
//             weight: 7,
//             color: "#111827",
//             pulseColor: "#ffffff",
//             paused: false,
//             reverse: false,
//             hardwareAccelerated: true,
//             opacity: 0.95,
//           })
//         : null;

//     const aheadLayer =
//       aheadPath.length >= 2
//         ? L.polyline.antPath(aheadPath, {
//             delay: 900,
//             dashArray: [10, 24],
//             weight: 5,
//             color: "#2563eb",
//             pulseColor: "#ffffff",
//             paused: false,
//             reverse: false,
//             hardwareAccelerated: true,
//             opacity: 0.42,
//           })
//         : null;

//     if (behindLayer) behindLayer.addTo(map);
//     if (aheadLayer) aheadLayer.addTo(map);

//     return () => {
//       if (behindLayer) map.removeLayer(behindLayer);
//       if (aheadLayer) map.removeLayer(aheadLayer);
//     };
//   }, [map, context, vehicle, previousStops, nextStops]);

//   if (!context || !vehicle) return null;

//   return (
//     <>
//       {localShapeSegment.length >= 2 && (
//         <Pane name="selected-local-shape" style={{ zIndex: 640 }}>
//           <Polyline
//             positions={localShapeSegment}
//             pathOptions={{
//               color: "#111827",
//               weight: 5,
//               opacity: 0.28,
//             }}
//           />
//         </Pane>
//       )}

//       <Pane name="selected-stops" style={{ zIndex: 700 }}>
//         {previousStops.map((stop) => (
//           <CircleMarker
//             key={`prev-${stop.stop_id}-${stop.stop_sequence}`}
//             center={[Number(stop.stop_lat), Number(stop.stop_lon)]}
//             radius={6}
//             pathOptions={{
//               color: "#6b7280",
//               fillColor: "#6b7280",
//               fillOpacity: 0.35,
//               weight: 1,
//             }}
//           />
//         ))}

//         {nextStops.map((stop, idx) => (
//           <Pane
//             key={`next-pane-${stop.stop_id}-${stop.stop_sequence}`}
//             name={`next-stop-${stop.stop_id}-${stop.stop_sequence}`}
//             style={{ zIndex: 720 }}
//           >
//             {idx === 0 && (
//               <CircleMarker
//                 center={[Number(stop.stop_lat), Number(stop.stop_lon)]}
//                 radius={pulseOn ? 28 : 20}
//                 pathOptions={{
//                   color: "#ffffff",
//                 fillColor: "#00ca00",
//                 fillOpacity: 0,
//                 weight: 4,
//                 opacity: pulseOn ? 0.15 : 0.35,
//                 }}
//               />
//             )}

//             <CircleMarker
//               center={[Number(stop.stop_lat), Number(stop.stop_lon)]}
//               radius={idx === 0 ? 7 : 6}
//               pathOptions={{
//                 color: "#6effab",
//               fillColor: "#11b91a",
//               fillOpacity: 0,
//               weight: idx === 0 ? 14 : 10,
//               opacity: idx === 0 ? 0.95 : 0.75,
//               }}
//             />
//           </Pane>
//         ))}
//       </Pane>
//     </>
//   );
// }
import { useEffect, useState } from "react";
import { CircleMarker, Pane, Polyline, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet-ant-path";

function makePath(points) {
  return points.filter((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]));
}

export default function SelectedCorridor({ context, vehicle }) {
  const map = useMap();
  const [pulseOn, setPulseOn] = useState(true);

  useEffect(() => {
    const interval = setInterval(() => {
      setPulseOn((v) => !v);
    }, 700);

    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!map || !context || !vehicle || vehicle.isStale) return;

    const nextStops = Array.isArray(context.next_stops) ? context.next_stops : [];

    const aheadPath = makePath([
      [vehicle.lat, vehicle.lon],
      ...nextStops.map((s) => [Number(s.stop_lat), Number(s.stop_lon)]),
    ]);

    const aheadLayer =
      aheadPath.length >= 2
        ? L.polyline.antPath(aheadPath, {
            delay: 1400,
            dashArray: [8, 22],
            weight: 6,
            color: "#2563eb",
            pulseColor: "#ffffff",
            paused: false,
            reverse: false,
            hardwareAccelerated: true,
            opacity: 0.7,
          })
        : null;

    if (aheadLayer) aheadLayer.addTo(map);

    return () => {
      if (aheadLayer) map.removeLayer(aheadLayer);
    };
  }, [map, context, vehicle]);

  if (!context || !vehicle) return null;

  const previousStops = Array.isArray(context.previous_stops) ? context.previous_stops : [];
  const nextStops = Array.isArray(context.next_stops) ? context.next_stops : [];

  const behindPath = makePath([
    ...previousStops.map((s) => [Number(s.stop_lat), Number(s.stop_lon)]),
    [vehicle.lat, vehicle.lon],
  ]);

  return (
    <>
      {behindPath.length >= 2 && (
        <Pane name="selected-behind-line" style={{ zIndex: 650 }}>
          <Polyline
            positions={behindPath}
            pathOptions={{
              color: "#111827",
              weight: 6,
              opacity: 0.85,
            }}
          />
        </Pane>
      )}

      <Pane name="selected-stops" style={{ zIndex: 720 }}>
        {previousStops.map((stop) => (
          <CircleMarker
            key={`prev-${stop.stop_id}-${stop.stop_sequence}`}
            center={[Number(stop.stop_lat), Number(stop.stop_lon)]}
            radius={6}
            pathOptions={{
              color: "#6b7280",
              fillColor: "#6b7280",
              fillOpacity: 0.3,
              weight: 1,
            }}
          />
        ))}

        {nextStops.map((stop, idx) => (
          <Pane
            key={`next-pane-${stop.stop_id}-${stop.stop_sequence}`}
            name={`next-stop-${stop.stop_id}-${stop.stop_sequence}`}
            style={{ zIndex: 730 }}
          >
            {idx === 0 && (
              <CircleMarker
                center={[Number(stop.stop_lat), Number(stop.stop_lon)]}
                radius={pulseOn ? 14 : 9}
                pathOptions={{
                  color: "#f59e0b",
                  fillColor: "#f59e0b",
                  fillOpacity: 0,
                  weight: 2,
                  opacity: pulseOn ? 0.18 : 0.38,
                }}
              />
            )}

            <CircleMarker
              center={[Number(stop.stop_lat), Number(stop.stop_lon)]}
              radius={idx === 0 ? 7 : 6}
              pathOptions={{
                color: "#f59e0b",
                fillColor: "#f59e0b",
                fillOpacity: 0,
                weight: idx === 0 ? 3 : 2,
                opacity: idx === 0 ? 0.95 : 0.75,
              }}
            />
          </Pane>
        ))}
      </Pane>
    </>
  );
}