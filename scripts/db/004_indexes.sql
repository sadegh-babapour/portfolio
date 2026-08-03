BEGIN;

CREATE INDEX IF NOT EXISTS idx_calendar_dates_service_id
    ON transit.calendar_dates (service_id);
CREATE INDEX IF NOT EXISTS idx_calendar_dates_date
    ON transit.calendar_dates (date);
CREATE INDEX IF NOT EXISTS idx_trips_route_id ON transit.trips (route_id);
CREATE INDEX IF NOT EXISTS idx_trips_service_id ON transit.trips (service_id);
CREATE INDEX IF NOT EXISTS idx_trips_shape_id ON transit.trips (shape_id);
CREATE INDEX IF NOT EXISTS idx_shapes_shape_id ON transit.shapes (shape_id);
CREATE INDEX IF NOT EXISTS idx_shapes_shape_id_seq
    ON transit.shapes (shape_id, shape_pt_sequence);
CREATE INDEX IF NOT EXISTS idx_stop_times_trip_id ON transit.stop_times (trip_id);
CREATE INDEX IF NOT EXISTS idx_stop_times_stop_id ON transit.stop_times (stop_id);
CREATE INDEX IF NOT EXISTS idx_stop_times_trip_seq
    ON transit.stop_times (trip_id, stop_sequence);

CREATE INDEX IF NOT EXISTS idx_vehicle_positions_vehicle_id
    ON transit.vehicle_positions_raw (vehicle_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_positions_trip_id
    ON transit.vehicle_positions_raw (trip_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_positions_vehicle_ts
    ON transit.vehicle_positions_raw (vehicle_timestamp);
CREATE UNIQUE INDEX IF NOT EXISTS uq_vehicle_positions_obs
    ON transit.vehicle_positions_raw (trip_id, vehicle_id, vehicle_timestamp);
CREATE INDEX IF NOT EXISTS idx_vehicle_positions_current_trip_id
    ON transit.vehicle_positions_current (trip_id);

CREATE INDEX IF NOT EXISTS idx_trip_updates_trip_id
    ON transit.trip_updates_raw (trip_id);
CREATE INDEX IF NOT EXISTS idx_trip_updates_route_id
    ON transit.trip_updates_raw (route_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_trip_updates_obs
    ON transit.trip_updates_raw (feed_entity_id, feed_header_timestamp);
CREATE INDEX IF NOT EXISTS idx_trip_update_stop_times_parent
    ON transit.trip_update_stop_times_raw (trip_update_raw_id);
CREATE INDEX IF NOT EXISTS idx_trip_update_stop_times_stop_id
    ON transit.trip_update_stop_times_raw (stop_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_trip_update_stop_times_obs
    ON transit.trip_update_stop_times_raw
    (trip_update_raw_id, stop_sequence, stop_id, arrival_time, departure_time);
CREATE INDEX IF NOT EXISTS idx_trip_update_stop_times_current_stop_id
    ON transit.trip_update_stop_times_current (stop_id);

CREATE INDEX IF NOT EXISTS idx_alerts_active_start
    ON transit.alerts_raw (active_start);
CREATE INDEX IF NOT EXISTS idx_alerts_active_end
    ON transit.alerts_raw (active_end);
CREATE UNIQUE INDEX IF NOT EXISTS uq_alerts_obs
    ON transit.alerts_raw (feed_entity_id, feed_header_timestamp);
CREATE INDEX IF NOT EXISTS idx_alert_informed_entities_alert
    ON transit.alert_informed_entities_raw (alert_raw_id);
CREATE INDEX IF NOT EXISTS idx_alert_informed_entities_route
    ON transit.alert_informed_entities_raw (route_id);
CREATE INDEX IF NOT EXISTS idx_alert_informed_entities_stop
    ON transit.alert_informed_entities_raw (stop_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_alert_informed_entities_obs
    ON transit.alert_informed_entities_raw
    (alert_raw_id, coalesce(agency_id, ''), coalesce(route_id, ''),
     coalesce(stop_id, ''));
CREATE INDEX IF NOT EXISTS idx_alert_informed_entities_current_route_id
    ON transit.alert_informed_entities_current (route_id);
CREATE INDEX IF NOT EXISTS idx_alert_informed_entities_current_stop_id
    ON transit.alert_informed_entities_current (stop_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_alert_informed_entities_current
    ON transit.alert_informed_entities_current
    (feed_entity_id, coalesce(agency_id, ''), coalesce(route_id, ''),
     coalesce(stop_id, ''));

COMMIT;
