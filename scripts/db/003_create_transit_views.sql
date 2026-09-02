BEGIN;

CREATE OR REPLACE VIEW transit.v_route_catalog_lookup AS
SELECT
    upper(trim(route_short_name)) AS route_short_name_norm,
    trim(route_short_name) AS route_short_name,
    trim(route_long_name) AS route_long_name,
    upper(trim(route_category)) AS route_category
FROM transit.route_catalog_raw;

CREATE OR REPLACE VIEW transit.v_latest_vehicle_positions AS
SELECT DISTINCT ON (vehicle_id)
    vehicle_id,
    trip_id,
    vehicle_timestamp,
    lat,
    lon
FROM transit.vehicle_positions_raw
ORDER BY vehicle_id, vehicle_timestamp DESC;

CREATE OR REPLACE VIEW transit.v_latest_vehicle_positions_enriched AS
SELECT
    lv.vehicle_id,
    lv.trip_id,
    lv.vehicle_timestamp,
    lv.lat,
    lv.lon,
    t.route_id AS static_route_id,
    r.route_short_name,
    r.route_long_name,
    t.trip_headsign,
    t.direction_id,
    t.shape_id
FROM transit.v_latest_vehicle_positions lv
LEFT JOIN transit.trips t ON t.trip_id = lv.trip_id
LEFT JOIN transit.routes r ON r.route_id = t.route_id;

CREATE OR REPLACE VIEW transit.v_latest_trip_updates AS
SELECT DISTINCT ON (trip_id)
    id,
    downloaded_at,
    feed_header_timestamp,
    feed_entity_id,
    trip_id,
    route_id,
    trip_schedule_relationship
FROM transit.trip_updates_raw
ORDER BY trip_id, feed_header_timestamp DESC, id DESC;

CREATE OR REPLACE VIEW transit.v_vehicle_positions_enriched AS
SELECT
    v.downloaded_at,
    v.feed_header_timestamp,
    v.feed_entity_id,
    v.trip_id,
    v.vehicle_id,
    v.lat,
    v.lon,
    v.vehicle_timestamp,
    t.route_id AS static_route_id,
    r.route_short_name,
    r.route_long_name,
    t.service_id,
    t.trip_headsign,
    t.direction_id,
    t.block_id,
    t.shape_id
FROM transit.vehicle_positions_raw v
LEFT JOIN transit.trips t ON t.trip_id = v.trip_id
LEFT JOIN transit.routes r ON r.route_id = t.route_id;

CREATE OR REPLACE VIEW transit.v_trip_updates_enriched AS
SELECT
    tu.downloaded_at,
    tu.feed_header_timestamp,
    tu.feed_entity_id,
    tu.trip_id,
    tu.route_id AS live_route_id,
    t.route_id AS static_route_id,
    r.route_short_name,
    r.route_long_name,
    t.trip_headsign,
    t.direction_id,
    stu.stop_sequence,
    stu.stop_id,
    s.stop_name,
    stu.arrival_time,
    stu.departure_time,
    stu.schedule_relationship
FROM transit.trip_updates_raw tu
LEFT JOIN transit.trips t ON t.trip_id = tu.trip_id
LEFT JOIN transit.routes r ON r.route_id = t.route_id
LEFT JOIN transit.trip_update_stop_times_raw stu
    ON stu.trip_update_raw_id = tu.id
LEFT JOIN transit.stops s ON s.stop_id = stu.stop_id;

CREATE OR REPLACE VIEW transit.v_alerts_enriched AS
SELECT
    a.downloaded_at,
    a.feed_header_timestamp,
    a.feed_entity_id,
    a.active_start,
    a.active_end,
    a.header_text,
    a.description_html,
    ie.agency_id,
    ie.route_id AS live_route_ref,
    ie.stop_id,
    r.route_id AS static_route_id,
    r.route_short_name,
    r.route_long_name,
    s.stop_name
FROM transit.alerts_raw a
LEFT JOIN transit.alert_informed_entities_raw ie ON ie.alert_raw_id = a.id
LEFT JOIN transit.routes r ON r.route_short_name = ie.route_id
LEFT JOIN transit.stops s ON s.stop_id = ie.stop_id;

CREATE OR REPLACE VIEW transit.v_trip_upcoming_stops AS
SELECT
    tu.trip_id,
    tu.route_id AS live_route_id,
    t.route_id AS static_route_id,
    r.route_short_name,
    r.route_long_name,
    t.trip_headsign,
    t.direction_id,
    stu.stop_sequence,
    stu.stop_id,
    s.stop_name,
    stu.arrival_time,
    stu.departure_time,
    stu.schedule_relationship
FROM transit.trip_updates_current tu
LEFT JOIN transit.trips t ON t.trip_id = tu.trip_id
LEFT JOIN transit.routes r ON r.route_id = t.route_id
LEFT JOIN transit.trip_update_stop_times_current stu ON stu.trip_id = tu.trip_id
LEFT JOIN transit.stops s ON s.stop_id = stu.stop_id;

CREATE OR REPLACE VIEW transit.v_active_alerts AS
SELECT
    a.feed_entity_id,
    a.active_start,
    a.active_end,
    a.header_text,
    a.description_html,
    ie.agency_id,
    ie.route_id AS live_route_ref,
    ie.stop_id,
    r.route_id AS static_route_id,
    r.route_short_name,
    r.route_long_name,
    s.stop_name
FROM transit.alerts_current a
LEFT JOIN transit.alert_informed_entities_current ie
    ON ie.feed_entity_id = a.feed_entity_id
LEFT JOIN transit.routes r ON r.route_short_name = ie.route_id
LEFT JOIN transit.stops s ON s.stop_id = ie.stop_id
WHERE a.active_end IS NULL OR a.active_end >= now();

CREATE OR REPLACE VIEW transit.v_vehicle_dashboard AS
WITH latest_tripupdates AS (
    SELECT trip_id, route_id
    FROM transit.trip_updates_current
), classified AS (
    SELECT
        v.vehicle_id,
        v.trip_id,
        v.vehicle_timestamp,
        v.vehicle_timestamp AT TIME ZONE 'America/Edmonton'
            AS vehicle_timestamp_edmonton,
        v.lat,
        v.lon,
        t.route_id AS static_route_id,
        coalesce(r.route_short_name, lr.route_short_name, ltu.route_id) AS route_short_name,
        coalesce(r.route_long_name, lr.route_long_name, rc.route_long_name) AS route_long_name,
        t.trip_headsign,
        t.direction_id,
        t.shape_id,
        coalesce(
            rc.route_category,
            CASE
                WHEN coalesce(r.route_long_name, lr.route_long_name, rc.route_long_name)
                    ILIKE 'MAX %' THEN 'MAX'
                WHEN coalesce(r.route_short_name, lr.route_short_name, ltu.route_id)
                    IN ('MG', 'MO', 'MP', 'MT', 'MY')
                    THEN 'MAX'
                WHEN coalesce(r.route_short_name, lr.route_short_name, ltu.route_id)
                    IN ('201', '202')
                    THEN 'LRT'
                ELSE NULL
            END
        ) AS route_category,
        t.trip_id IS NOT NULL AS matched_to_static,
        ltu.trip_id IS NOT NULL AS has_trip_update
    FROM transit.vehicle_positions_current v
    LEFT JOIN transit.trips t ON t.trip_id = v.trip_id
    LEFT JOIN transit.routes r ON r.route_id = t.route_id
    LEFT JOIN latest_tripupdates ltu ON ltu.trip_id = v.trip_id
    LEFT JOIN transit.routes lr ON lr.route_id = ltu.route_id
    LEFT JOIN transit.v_route_catalog_lookup rc
        ON upper(trim(coalesce(r.route_short_name, lr.route_short_name, ltu.route_id)))
            = rc.route_short_name_norm
)
SELECT
    classified.*,
    CASE
        WHEN NOT matched_to_static AND NOT has_trip_update THEN 'unmatched_live'
        WHEN NOT has_trip_update THEN 'matched_no_tripupdate'
        ELSE 'in_service'
    END AS vehicle_status,
    CASE
        WHEN route_category = 'LRT' THEN 'lrt'
        WHEN route_category IN ('BRT', 'MAX', 'EXPRESS') THEN 'brt'
        WHEN coalesce(route_category, 'REGULAR')
            IN ('REGULAR', 'SCHOOL', 'SPECIAL') THEN 'bus'
        ELSE 'unknown'
    END AS route_mode
FROM classified;

COMMIT;
