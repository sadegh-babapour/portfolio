import { useEffect, useMemo, useState } from "react";
import { CircleMarker, Pane, Polyline, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet-ant-path";

import { shapeSegmentToStop } from "./routeGeometry";


export default function SelectedCorridor({ context, vehicle, selectedStop }) {
  const map = useMap();
  const [pulseOn, setPulseOn] = useState(true);
  const nextStops = Array.isArray(context?.next_stops) ? context.next_stops : [];
  const destinationStop = selectedStop || nextStops[0] || null;
  const corridor = useMemo(
    () => shapeSegmentToStop(context?.shape_points, vehicle, destinationStop),
    [context?.shape_points, destinationStop, vehicle],
  );

  useEffect(() => {
    const interval = setInterval(() => setPulseOn((value) => !value), 700);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!map || vehicle?.isStale || corridor.length < 2) return;
    const layer = L.polyline.antPath(corridor, {
      delay: 1100,
      dashArray: [10, 20],
      weight: 6,
      color: "#2563eb",
      pulseColor: "#ffffff",
      paused: false,
      reverse: false,
      hardwareAccelerated: true,
      opacity: 0.82,
    });
    layer.addTo(map);
    return () => map.removeLayer(layer);
  }, [corridor, map, vehicle?.isStale]);

  if (!context || !vehicle) return null;

  return (
    <>
      {corridor.length >= 2 && (
        <Pane name="selected-corridor" style={{ zIndex: 650 }}>
          <Polyline
            positions={corridor}
            pathOptions={{ color: "#1d4ed8", weight: 8, opacity: 0.34 }}
          />
        </Pane>
      )}
      <Pane name="selected-stops" style={{ zIndex: 720 }}>
        {nextStops.map((stop) => (
          <Pane
            key={`next-pane-${stop.stop_id}-${stop.stop_sequence}`}
            name={`next-stop-${stop.stop_id}-${stop.stop_sequence}`}
            style={{ zIndex: 730 }}
          >
            {stop === destinationStop && (
              <CircleMarker
                center={[Number(stop.stop_lat), Number(stop.stop_lon)]}
                radius={pulseOn ? 15 : 10}
                pathOptions={{
                  color: "#f59e0b",
                  fillColor: "#f59e0b",
                  fillOpacity: 0,
                  weight: 2,
                  opacity: pulseOn ? 0.2 : 0.42,
                }}
              />
            )}
            <CircleMarker
              center={[Number(stop.stop_lat), Number(stop.stop_lon)]}
              radius={stop === destinationStop ? 7 : 5}
              pathOptions={{
                color: stop === destinationStop ? "#f59e0b" : "#fbbf24",
                fillColor: "#f59e0b",
                fillOpacity: stop === destinationStop ? 0.92 : 0.52,
                weight: 2,
              }}
            />
          </Pane>
        ))}
      </Pane>
    </>
  );
}
