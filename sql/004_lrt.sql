-- Run once in Railway Postgres console

-- LRT stations table
CREATE TABLE IF NOT EXISTS lrt_stations (
    station_id    SERIAL PRIMARY KEY,
    station_name  TEXT NOT NULL,
    lat           DOUBLE PRECISION NOT NULL,
    lon           DOUBLE PRECISION NOT NULL,
    line          TEXT NOT NULL,        -- 'red', 'blue', 'both'
    sequence      INTEGER NOT NULL,     -- order along the line
    is_terminal   BOOLEAN DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_lrt_stations_line ON lrt_stations (line);

-- LRT route shapes table (better than CSV, from shapes.txt)
CREATE TABLE IF NOT EXISTS lrt_shapes (
    shape_id      TEXT NOT NULL,
    sequence      INTEGER NOT NULL,
    lat           DOUBLE PRECISION NOT NULL,
    lon           DOUBLE PRECISION NOT NULL,
    line          TEXT NOT NULL,        -- 'red' or 'blue'
    PRIMARY KEY (shape_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_lrt_shapes_line ON lrt_shapes (line);