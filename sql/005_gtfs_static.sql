-- Run once in Railway Postgres console

ALTER TABLE vehicle_positions_raw
    ADD COLUMN IF NOT EXISTS trip_id TEXT;

ALTER TABLE vehicle_positions_latest
    ADD COLUMN IF NOT EXISTS trip_id   TEXT,
    ADD COLUMN IF NOT EXISTS headsign  TEXT;

CREATE TABLE IF NOT EXISTS gtfs_trips (
    trip_id          TEXT PRIMARY KEY,
    route_id         TEXT,
    route_short_name TEXT,
    headsign         TEXT,
    direction_id     SMALLINT,
    shape_id         TEXT,
    service_id       TEXT
);
CREATE INDEX IF NOT EXISTS idx_gtfs_trips_route ON gtfs_trips (route_short_name);

CREATE TABLE IF NOT EXISTS gtfs_stops (
    stop_id    TEXT PRIMARY KEY,
    stop_code  TEXT,
    stop_name  TEXT,
    stop_lat   DOUBLE PRECISION,
    stop_lon   DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS gtfs_stop_times (
    trip_id          TEXT NOT NULL,
    stop_sequence    INTEGER NOT NULL,
    stop_id          TEXT NOT NULL,
    arrival_time     TEXT,
    departure_time   TEXT,
    shape_dist       REAL,
    timepoint        SMALLINT,
    PRIMARY KEY (trip_id, stop_sequence)
);
CREATE INDEX IF NOT EXISTS idx_gst_stop ON gtfs_stop_times (stop_id);
CREATE INDEX IF NOT EXISTS idx_gst_trip ON gtfs_stop_times (trip_id);