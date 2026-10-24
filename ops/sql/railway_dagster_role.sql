-- The Dagster service's own login on Railway (openspec/changes/dagster-railway).
--
-- Run once by the owner, as the database's admin role, in the site's database, then
-- give the role a password at the prompt (never in a file or on a command line):
--   \i ops/sql/railway_dagster_role.sql
--   \password bizqlab_dagster
-- Safe to run again: it only creates what is missing and re-applies the limits.
--
-- The role owns the warehouse (raw, staging, marts) and Dagster's run history
-- (dagster), and nothing else. It gets no USAGE on portfolio or transit, so it can't
-- read the site's users, sessions or messages. orchestration/definitions.py refuses
-- to run as any role that can.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bizqlab_dagster') THEN
        CREATE ROLE bizqlab_dagster LOGIN;
    END IF;
END $$;
ALTER ROLE bizqlab_dagster LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    CONNECTION LIMIT 20;
-- Dagster creates its tables without a schema name; this puts them in `dagster`.
ALTER ROLE bizqlab_dagster SET search_path = dagster;

-- CREATE on the database because the loader's `CREATE SCHEMA IF NOT EXISTS raw` is
-- checked against it even when raw exists. It lets the role make new schemas, never
-- enter existing ones.
DO $$
BEGIN
    EXECUTE format('GRANT CONNECT, CREATE ON DATABASE %I TO bizqlab_dagster', current_database());
END $$;

CREATE SCHEMA IF NOT EXISTS raw AUTHORIZATION bizqlab_dagster;
CREATE SCHEMA IF NOT EXISTS staging AUTHORIZATION bizqlab_dagster;
CREATE SCHEMA IF NOT EXISTS marts AUTHORIZATION bizqlab_dagster;
CREATE SCHEMA IF NOT EXISTS dagster AUTHORIZATION bizqlab_dagster;
ALTER SCHEMA raw OWNER TO bizqlab_dagster;
ALTER SCHEMA staging OWNER TO bizqlab_dagster;
ALTER SCHEMA marts OWNER TO bizqlab_dagster;
ALTER SCHEMA dagster OWNER TO bizqlab_dagster;
