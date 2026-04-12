-- ============================================================
-- Calgary Transit Live Map — database schema
-- Run this ONCE in the Railway Postgres console after provisioning.
-- ============================================================

-- Enable pg_cron (Railway Postgres supports this — must be enabled
-- in the Railway dashboard under your Postgres service → Settings → Extensions,
-- or just run the line below; Railway auto-enables it on first use).
CREATE EXTENSION IF NOT EXISTS pg_cron;


-- ------------------------------------------------------------
-- 1. RAW positions table
--    Every poll writes here. pg_cron trims it every 10 minutes.
--    We keep 2 hours of history — enough for ghost trails and
--    short-window speed averages without blowing up storage.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vehicle_positions_raw (
    id            BIGSERIAL PRIMARY KEY,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    vehicle_id    TEXT        NOT NULL,
    route_id      TEXT,
    lat           DOUBLE PRECISION NOT NULL,
    lon           DOUBLE PRECISION NOT NULL,
    bearing       SMALLINT,
    speed         REAL,                      -- metres/second from feed
    occupancy     TEXT                        -- EMPTY, MANY_SEATS, FULL, etc.
);

-- Index for the cleanup job and for ghost-trail queries
CREATE INDEX IF NOT EXISTS idx_vpr_fetched_at   ON vehicle_positions_raw (fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_vpr_vehicle_time ON vehicle_positions_raw (vehicle_id, fetched_at DESC);


-- ------------------------------------------------------------
-- 2. LATEST positions table
--    One row per vehicle, always current.
--    The map reads ONLY this table — fast, tiny, always fresh.
--    Updated via INSERT ... ON CONFLICT DO UPDATE on every poll.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vehicle_positions_latest (
    vehicle_id    TEXT PRIMARY KEY,
    route_id      TEXT,
    lat           DOUBLE PRECISION NOT NULL,
    lon           DOUBLE PRECISION NOT NULL,
    bearing       SMALLINT,
    speed         REAL,
    prev_lat      DOUBLE PRECISION,           -- position from previous poll (ghost dot)
    prev_lon      DOUBLE PRECISION,
    is_stale      BOOLEAN NOT NULL DEFAULT false,  -- true = same position as last fetch
    quadrant      TEXT,                        -- NE / NW / SE / SW
    last_seen     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_vpl_route    ON vehicle_positions_latest (route_id);
CREATE INDEX IF NOT EXISTS idx_vpl_quadrant ON vehicle_positions_latest (quadrant);


-- ------------------------------------------------------------
-- 3. pg_cron job — trim raw table every 10 minutes
--    Keeps only the last 2 hours. Runs silently in the background.
-- ------------------------------------------------------------
SELECT cron.schedule(
    'trim-vehicle-positions-raw',       -- job name (unique)
    '*/10 * * * *',                     -- every 10 minutes
    $$
        DELETE FROM vehicle_positions_raw
        WHERE fetched_at < now() - INTERVAL '2 hours';
    $$
);


-- ------------------------------------------------------------
-- Verification — run these after the above to confirm setup:
--
--   SELECT * FROM cron.job;
--   \d vehicle_positions_raw
--   \d vehicle_positions_latest
-- ------------------------------------------------------------