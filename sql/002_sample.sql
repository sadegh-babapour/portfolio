-- Run this once in Railway Postgres console

CREATE TABLE IF NOT EXISTS transit_daily_sample (
    sample_date  DATE        NOT NULL DEFAULT CURRENT_DATE,
    quadrant     TEXT        NOT NULL,
    vehicle_id   TEXT        NOT NULL,
    UNIQUE (sample_date, quadrant, vehicle_id)
);

CREATE INDEX IF NOT EXISTS idx_tds_date ON transit_daily_sample (sample_date, quadrant);