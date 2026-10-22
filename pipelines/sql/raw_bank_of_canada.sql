-- Raw layer for the Bank of Canada loader. Safe to run on every load: it only
-- creates what does not exist yet. dbt reads these tables; only the loader writes them.

CREATE SCHEMA IF NOT EXISTS raw;

-- One row per loader run, for every source: when, what happened, how many rows.
CREATE TABLE IF NOT EXISTS raw.load_runs (
    run_id bigserial PRIMARY KEY,
    source text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'succeeded', 'failed')),
    start_date date,
    rows_read integer,
    rows_inserted integer,
    rows_updated integer,
    error text
);

CREATE TABLE IF NOT EXISTS raw.boc_series (
    series_id text PRIMARY KEY,
    label text NOT NULL,
    description text NOT NULL,
    unit text,
    frequency text,
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at timestamptz NOT NULL DEFAULT now()
);

-- Grain: one row per series per date. Values stay exactly as published (numeric,
-- not float). last_changed_at moves only when the Bank revises a value.
CREATE TABLE IF NOT EXISTS raw.boc_observations (
    series_id text NOT NULL,
    obs_date date NOT NULL,
    value numeric NOT NULL,
    first_loaded_at timestamptz NOT NULL DEFAULT now(),
    last_changed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (series_id, obs_date)
);
