BEGIN;

CREATE TABLE IF NOT EXISTS transit.static_gtfs_import_state (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    source_url text NOT NULL,
    source_etag text,
    archive_sha256 text NOT NULL,
    checked_at timestamptz NOT NULL,
    loaded_at timestamptz NOT NULL,
    max_service_date date
);

COMMIT;
