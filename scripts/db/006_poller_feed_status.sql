BEGIN;

-- One row per realtime feed, rewritten by the poller on every pass, so the health checks
-- can compare what Calgary published with what we stored (docs/runbooks, /api/health).
CREATE TABLE IF NOT EXISTS transit.poller_feed_status (
    feed_name text PRIMARY KEY,
    finished_at timestamptz NOT NULL,
    seconds_since_previous double precision,
    duration_seconds double precision NOT NULL,
    feed_header_timestamp timestamptz,
    entities_in_feed integer NOT NULL,
    rows_written integer NOT NULL,
    timestamps_from_header integer NOT NULL DEFAULT 0
);

COMMIT;
