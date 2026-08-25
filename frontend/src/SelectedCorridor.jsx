import { useEffect, useRef } from "react";
import { CircleMarker, Pane, Polyline, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet-ant-path";

import {
  resolveCorridorStop,
  corridorViewportPoints,
  shapeSegmentToStop,
  stopsThroughDestination,
} from "./routeGeometry";
import { routeColor } from "./routeStyle";


export default function SelectedCorridor({ context, vehicle, selectedStop, trackingLocked = false }) {
  const map = useMap();
  const fittedSelectionRef = useRef("");
  const antPathRef = useRef(null);
  const nextStops = Array.isArray(context?.next_stops) ? context.next_stops : [];
  const destinationStop = trackingLocked && !selectedStop
    ? null
    : resolveCorridorStop(nextStops, selectedStop);
  const displayedStops = trackingLocked && !destinationStop
    ? []
    : stopsThroughDestination(nextStops, destinationStop);
  const corridorColor = routeColor(vehicle);
  const corridor = shapeSegmentToStop(context?.shape_points, vehicle, destinationStop);
  const progressKey = trackingLocked
    ? `${nextStops[0]?.stop_id || "none"}-${nextStops[0]?.stop_sequence || "none"}`
    : "preview";
  const latestCorridorRef = useRef(corridor);
  const hasCorridor = corridor.length >= 2;

  useEffect(() => {
    latestCorridorRef.current = corridor;
  }, [corridor]);

  useEffect(() => {
    if (!map || vehicle?.isStale || !hasCorridor) return;
    const layer = L.polyline.antPath(latestCorridorRef.current, {
      delay: 1600,
      dashArray: [12, 24],
      weight: 6,
      color: "transparent",
      pulseColor: corridorColor,
      paused: false,
      reverse: false,
      hardwareAccelerated: true,
      opacity: 0.82,
    });
    layer.addTo(map);
    antPathRef.current = layer;
    return () => {
      antPathRef.current = null;
      map.removeLayer(layer);
    };
  }, [corridorColor, hasCorridor, map, vehicle?.isStale]);

  useEffect(() => {
    if (hasCorridor) antPathRef.current?.setLatLngs(corridor);
  }, [corridor, hasCorridor]);

  useEffect(() => {
    if (!map || corridor.length < 2 || !destinationStop) return;
    const selectionKey = `${vehicle.vehicle_id}-${vehicle.trip_id}-${destinationStop.stop_id}-${progressKey}`;
    if (fittedSelectionRef.current === selectionKey) return;
    fittedSelectionRef.current = selectionKey;
    map.fitBounds(L.latLngBounds(corridorViewportPoints(corridor, vehicle, destinationStop)), {
      animate: true,
      duration: 0.8,
      maxZoom: 15,
      padding: [32, 32],
    });
  }, [corridor, destinationStop, map, progressKey, vehicle, vehicle.trip_id, vehicle.vehicle_id]);

  useEffect(() => {
    if (!trackingLocked || !destinationStop || corridor.length < 2) return undefined;
    const restoreTrackingView = () => {
      map.fitBounds(L.latLngBounds(corridorViewportPoints(corridor, vehicle, destinationStop)), {
        animate: true,
        duration: 0.65,
        maxZoom: 15,
        padding: window.innerWidth <= 1050 ? [26, 26] : [38, 38],
      });
    };
    map.on("dragend", restoreTrackingView);
    return () => map.off("dragend", restoreTrackingView);
  }, [corridor, destinationStop, map, trackingLocked, vehicle]);

  if (!context || !vehicle) return null;

  return (
    <>
      {corridor.length >= 2 && (
        <Pane name="selected-corridor" style={{ zIndex: 650 }}>
          <Polyline
            positions={corridor}
            interactive={false}
            pathOptions={{ color: corridorColor, weight: 8, opacity: 0.26 }}
          />
        </Pane>
      )}
      <Pane name="selected-stops" style={{ zIndex: 720 }}>
        {displayedStops.map((stop) => (
          <Pane
            key={`next-pane-${stop.stop_id}-${stop.stop_sequence}`}
            name={`next-stop-${stop.stop_id}-${stop.stop_sequence}`}
            style={{ zIndex: 730 }}
          >
            {stop === destinationStop && (
              <CircleMarker
                interactive={false}
                center={[Number(stop.stop_lat), Number(stop.stop_lon)]}
                radius={13}
                pathOptions={{
                  color: "#f59e0b",
                  fillColor: "#f59e0b",
                  fillOpacity: 0,
                  weight: 2,
                  opacity: 0.42,
                }}
              />
            )}
            <CircleMarker
              interactive={false}
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
