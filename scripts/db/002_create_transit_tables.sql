BEGIN;

CREATE TABLE IF NOT EXISTS transit.routes (
    route_id text PRIMARY KEY,
    route_short_name text,
    route_long_name text,
    route_desc text,
    route_type integer,
    route_url text,
    route_color text,
    route_text_color text
);

CREATE TABLE IF NOT EXISTS transit.trips (
    route_id text NOT NULL,
    service_id text NOT NULL,
    trip_id text PRIMARY KEY,
    trip_headsign text,
    direction_id integer,
    block_id text,
    shape_id text
);

CREATE TABLE IF NOT EXISTS transit.calendar (
    service_id text PRIMARY KEY,
    monday integer,
    tuesday integer,
    wednesday integer,
    thursday integer,
    friday integer,
    saturday integer,
    sunday integer,
    start_date date,
    end_date date
);

CREATE TABLE IF NOT EXISTS transit.calendar_dates (
    service_id text NOT NULL,
    date date NOT NULL,
    exception_type integer NOT NULL
);

CREATE TABLE IF NOT EXISTS transit.stops (
    stop_id text PRIMARY KEY,
    stop_code text,
    stop_name text,
    stop_desc text,
    stop_lat double precision,
    stop_lon double precision,
    zone_id text,
    stop_url text,
    location_type integer
);

CREATE TABLE IF NOT EXISTS transit.shapes (
    shape_id text NOT NULL,
    shape_pt_lat double precision NOT NULL,
    shape_pt_lon double precision NOT NULL,
    shape_pt_sequence integer NOT NULL,
    shape_dist_traveled double precision
);

CREATE TABLE IF NOT EXISTS transit.stop_times (
    trip_id text NOT NULL,
    arrival_time text,
    departure_time text,
    stop_id text NOT NULL,
    stop_sequence integer NOT NULL,
    pickup_type integer,
    drop_off_type integer,
    shape_dist_traveled double precision,
    timepoint integer
);

CREATE TABLE IF NOT EXISTS transit.route_catalog_raw (
    route_category text,
    route_short_name text,
    route_long_name text,
    create_dt_utc text,
    mod_dt_utc text,
    globalid text,
    multilinestring text
);

CREATE TABLE IF NOT EXISTS transit.vehicle_positions_raw (
    id bigserial PRIMARY KEY,
    downloaded_at timestamptz NOT NULL DEFAULT now(),
    feed_header_timestamp timestamptz,
    feed_entity_id text NOT NULL,
    trip_id text NOT NULL,
    vehicle_id text NOT NULL,
    lat double precision NOT NULL,
    lon double precision NOT NULL,
    vehicle_timestamp timestamptz NOT NULL,
    raw_sha256 text
);

CREATE TABLE IF NOT EXISTS transit.vehicle_positions_current (
    vehicle_id text PRIMARY KEY,
    trip_id text NOT NULL,
    feed_entity_id text,
    vehicle_timestamp timestamptz NOT NULL,
    feed_header_timestamp timestamptz,
    lat double precision NOT NULL,
    lon double precision NOT NULL,
    raw_sha256 text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transit.trip_updates_raw (
    id bigserial PRIMARY KEY,
    downloaded_at timestamptz NOT NULL DEFAULT now(),
    feed_header_timestamp timestamptz,
    feed_entity_id text NOT NULL,
    trip_id text NOT NULL,
    route_id text,
    trip_schedule_relationship integer,
    raw_sha256 text
);

CREATE TABLE IF NOT EXISTS transit.trip_update_stop_times_raw (
    id bigserial PRIMARY KEY,
    trip_update_raw_id bigint NOT NULL
        REFERENCES transit.trip_updates_raw(id) ON DELETE CASCADE,
    stop_sequence integer,
    stop_id text,
    arrival_time timestamptz,
    departure_time timestamptz,
    schedule_relationship integer
);

CREATE TABLE IF NOT EXISTS transit.trip_updates_current (
    trip_id text PRIMARY KEY,
    feed_entity_id text,
    route_id text,
    trip_schedule_relationship integer,
    feed_header_timestamp timestamptz,
    raw_sha256 text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transit.trip_update_stop_times_current (
    trip_id text NOT NULL,
    stop_sequence integer NOT NULL,
    stop_id text,
    arrival_time timestamptz,
    departure_time timestamptz,
    schedule_relationship integer,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trip_id, stop_sequence)
);

CREATE TABLE IF NOT EXISTS transit.alerts_raw (
    id bigserial PRIMARY KEY,
    downloaded_at timestamptz NOT NULL DEFAULT now(),
    feed_header_timestamp timestamptz,
    feed_entity_id text NOT NULL,
    active_start timestamptz,
    active_end timestamptz,
    header_text text,
    description_html text,
    raw_sha256 text
);

CREATE TABLE IF NOT EXISTS transit.alert_informed_entities_raw (
    id bigserial PRIMARY KEY,
    alert_raw_id bigint NOT NULL
        REFERENCES transit.alerts_raw(id) ON DELETE CASCADE,
    agency_id text,
    route_id text,
    stop_id text
);

CREATE TABLE IF NOT EXISTS transit.alerts_current (
    feed_entity_id text PRIMARY KEY,
    active_start timestamptz,
    active_end timestamptz,
    header_text text,
    description_html text,
    feed_header_timestamp timestamptz,
    raw_sha256 text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS transit.alert_informed_entities_current (
    id bigserial PRIMARY KEY,
    feed_entity_id text NOT NULL,
    agency_id text,
    route_id text,
    stop_id text
);

COMMIT;
