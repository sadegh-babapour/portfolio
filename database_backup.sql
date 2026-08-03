--
-- PostgreSQL database dump
--

\restrict CWCrH22cJFDgLOC1g9uYOmdE9BWdVu8ey0v6saBNu5SftX0yw7G7aCCRLmwiLzN

-- Dumped from database version 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: transit; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA transit;


ALTER SCHEMA transit OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alert_informed_entities_current; Type: TABLE; Schema: transit; Owner: postgres
--

CREATE TABLE transit.alert_informed_entities_current (
    id bigint NOT NULL,
    feed_entity_id text NOT NULL,
    agency_id text,
    route_id text,
    stop_id text
);


ALTER TABLE transit.alert_informed_entities_current OWNER TO postgres;

--
-- Name: alert_informed_entities_current_id_seq; Type: SEQUENCE; Schema: transit; Owner: postgres
--

CREATE SEQUENCE transit.alert_informed_entities_current_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE transit.alert_informed_entities_current_id_seq OWNER TO postgres;

--
-- Name: alert_informed_entities_current_id_seq; Type: SEQUENCE OWNED BY; Schema: transit; Owner: postgres
--

ALTER SEQUENCE transit.alert_informed_entities_current_id_seq OWNED BY transit.alert_informed_entities_current.id;


--
-- Name: alert_informed_entities_raw; Type: TABLE; Schema: transit; Owner: postgres
--

CREATE TABLE transit.alert_informed_entities_raw (
    id bigint NOT NULL,
    alert_raw_id bigint NOT NULL,
    agency_id text,
    route_id text,
    stop_id text
);


ALTER TABLE transit.alert_informed_entities_raw OWNER TO postgres;

--
-- Name: alert_informed_entities_raw_id_seq; Type: SEQUENCE; Schema: transit; Owner: postgres
--

CREATE SEQUENCE transit.alert_informed_entities_raw_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE transit.alert_informed_entities_raw_id_seq OWNER TO postgres;

--
-- Name: alert_informed_entities_raw_id_seq; Type: SEQUENCE OWNED BY; Schema: transit; Owner: postgres
--

ALTER SEQUENCE transit.alert_informed_entities_raw_id_seq OWNED BY transit.alert_informed_entities_raw.id;


--
-- Name: alerts_current; Type: TABLE; Schema: transit; Owner: postgres
--

CREATE TABLE transit.alerts_current (
    feed_entity_id text NOT NULL,
    active_start timestamp with time zone,
    active_end timestamp with time zone,
    header_text text,
    description_html text,
    feed_header_timestamp timestamp with time zone,
    raw_sha256 text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE transit.alerts_current OWNER TO postgres;

--
-- Name: alerts_raw; Type: TABLE; Schema: transit; Owner: postgres
--

CREATE TABLE transit.alerts_raw (
    id bigint NOT NULL,
    downloaded_at timestamp with time zone DEFAULT now() NOT NULL,
    feed_header_timestamp timestamp with time zone,
    feed_entity_id text NOT NULL,
    active_start timestamp with time zone,
    active_end timestamp with time zone,
    header_text text,
    description_html text,
    raw_sha256 text
);


ALTER TABLE transit.alerts_raw OWNER TO postgres;

--
-- Name: alerts_raw_id_seq; Type: SEQUENCE; Schema: transit; Owner: postgres
--

CREATE SEQUENCE transit.alerts_raw_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE transit.alerts_raw_id_seq OWNER TO postgres;

--
-- Name: alerts_raw_id_seq; Type: SEQUENCE OWNED BY; Schema: transit; Owner: postgres
--

ALTER SEQUENCE transit.alerts_raw_id_seq OWNED BY transit.alerts_raw.id;


--
-- Name: calendar; Type: TABLE; Schema: transit; Owner: postgres
--

CREATE TABLE transit.calendar (
    service_id text NOT NULL,
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


ALTER TABLE transit.calendar OWNER TO postgres;

--
-- Name: calendar_dates; Type: TABLE; Schema: transit; Owner: postgres
--

CREATE TABLE transit.calendar_dates (
    service_id text NOT NULL,
    date date NOT NULL,
    exception_type integer NOT NULL
);


ALTER TABLE transit.calendar_dates OWNER TO postgres;

--
-- Name: route_catalog_raw; Type: TABLE; Schema: transit; Owner: postgres
--

CREATE TABLE transit.route_catalog_raw (
    route_category text,
    route_short_name text,
    route_long_name text,
    create_dt_utc text,
    mod_dt_utc text,
    globalid text,
    multilinestring text
);


ALTER TABLE transit.route_catalog_raw OWNER TO postgres;

--
-- Name: routes; Type: TABLE; Schema: transit; Owner: postgres
--

CREATE TABLE transit.routes (
    route_id text NOT NULL,
    route_short_name text,
    route_long_name text,
    route_desc text,
    route_type integer,
    route_url text,
    route_color text,
    route_text_color text
);


ALTER TABLE transit.routes OWNER TO postgres;

--
-- Name: shapes; Type: TABLE; Schema: transit; Owner: postgres
--

CREATE TABLE transit.shapes (
    shape_id text NOT NULL,
    shape_pt_lat double precision NOT NULL,
    shape_pt_lon double precision NOT NULL,
    shape_pt_sequence integer NOT NULL,
    shape_dist_traveled double precision
);


ALTER TABLE transit.shapes OWNER TO postgres;

--
-- Name: stop_times; Type: TABLE; Schema: transit; Owner: postgres
--

CREATE TABLE transit.stop_times (
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


ALTER TABLE transit.stop_times OWNER TO postgres;

--
-- Name: stops; Type: TABLE; Schema: transit; Owner: postgres
--

CREATE TABLE transit.stops (
    stop_id text NOT NULL,
    stop_code text,
    stop_name text,
    stop_desc text,
    stop_lat double precision,
    stop_lon double precision,
    zone_id text,
    stop_url text,
    location_type integer
);


ALTER TABLE transit.stops OWNER TO postgres;

--
-- Name: trip_update_stop_times_current; Type: TABLE; Schema: transit; Owner: postgres
--

CREATE TABLE transit.trip_update_stop_times_current (
    trip_id text NOT NULL,
    stop_sequence integer NOT NULL,
    stop_id text,
    arrival_time timestamp with time zone,
    departure_time timestamp with time zone,
    schedule_relationship integer,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE transit.trip_update_stop_times_current OWNER TO postgres;

--
-- Name: trip_update_stop_times_raw; Type: TABLE; Schema: transit; Owner: postgres
--

CREATE TABLE transit.trip_update_stop_times_raw (
    id bigint NOT NULL,
    trip_update_raw_id bigint NOT NULL,
    stop_sequence integer,
    stop_id text,
    arrival_time timestamp with time zone,
    departure_time timestamp with time zone,
    schedule_relationship integer
);


ALTER TABLE transit.trip_update_stop_times_raw OWNER TO postgres;

--
-- Name: trip_update_stop_times_raw_id_seq; Type: SEQUENCE; Schema: transit; Owner: postgres
--

CREATE SEQUENCE transit.trip_update_stop_times_raw_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE transit.trip_update_stop_times_raw_id_seq OWNER TO postgres;

--
-- Name: trip_update_stop_times_raw_id_seq; Type: SEQUENCE OWNED BY; Schema: transit; Owner: postgres
--

ALTER SEQUENCE transit.trip_update_stop_times_raw_id_seq OWNED BY transit.trip_update_stop_times_raw.id;


--
-- Name: trip_updates_current; Type: TABLE; Schema: transit; Owner: postgres
--

CREATE TABLE transit.trip_updates_current (
    trip_id text NOT NULL,
    feed_entity_id text,
    route_id text,
    trip_schedule_relationship integer,
    feed_header_timestamp timestamp with time zone,
    raw_sha256 text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE transit.trip_updates_current OWNER TO postgres;

--
-- Name: trip_updates_raw; Type: TABLE; Schema: transit; Owner: postgres
--

CREATE TABLE transit.trip_updates_raw (
    id bigint NOT NULL,
    downloaded_at timestamp with time zone DEFAULT now() NOT NULL,
    feed_header_timestamp timestamp with time zone,
    feed_entity_id text NOT NULL,
    trip_id text NOT NULL,
    route_id text,
    trip_schedule_relationship integer,
    raw_sha256 text
);


ALTER TABLE transit.trip_updates_raw OWNER TO postgres;

--
-- Name: trip_updates_raw_id_seq; Type: SEQUENCE; Schema: transit; Owner: postgres
--

CREATE SEQUENCE transit.trip_updates_raw_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE transit.trip_updates_raw_id_seq OWNER TO postgres;

--
-- Name: trip_updates_raw_id_seq; Type: SEQUENCE OWNED BY; Schema: transit; Owner: postgres
--

ALTER SEQUENCE transit.trip_updates_raw_id_seq OWNED BY transit.trip_updates_raw.id;


--
-- Name: trips; Type: TABLE; Schema: transit; Owner: postgres
--

CREATE TABLE transit.trips (
    route_id text NOT NULL,
    service_id text NOT NULL,
    trip_id text NOT NULL,
    trip_headsign text,
    direction_id integer,
    block_id text,
    shape_id text
);


ALTER TABLE transit.trips OWNER TO postgres;

--
-- Name: v_active_alerts; Type: VIEW; Schema: transit; Owner: postgres
--

CREATE VIEW transit.v_active_alerts AS
 SELECT a.feed_entity_id,
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
   FROM (((transit.alerts_current a
     LEFT JOIN transit.alert_informed_entities_current ie ON ((ie.feed_entity_id = a.feed_entity_id)))
     LEFT JOIN transit.routes r ON ((r.route_short_name = ie.route_id)))
     LEFT JOIN transit.stops s ON ((s.stop_id = ie.stop_id)))
  WHERE ((a.active_end IS NULL) OR (a.active_end >= now()));


ALTER VIEW transit.v_active_alerts OWNER TO postgres;

--
-- Name: v_alerts_enriched; Type: VIEW; Schema: transit; Owner: postgres
--

CREATE VIEW transit.v_alerts_enriched AS
 SELECT a.downloaded_at,
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
   FROM (((transit.alerts_raw a
     LEFT JOIN transit.alert_informed_entities_raw ie ON ((ie.alert_raw_id = a.id)))
     LEFT JOIN transit.routes r ON ((r.route_short_name = ie.route_id)))
     LEFT JOIN transit.stops s ON ((s.stop_id = ie.stop_id)));


ALTER VIEW transit.v_alerts_enriched OWNER TO postgres;

--
-- Name: v_latest_trip_updates; Type: VIEW; Schema: transit; Owner: postgres
--

CREATE VIEW transit.v_latest_trip_updates AS
 SELECT DISTINCT ON (trip_id) id,
    downloaded_at,
    feed_header_timestamp,
    feed_entity_id,
    trip_id,
    route_id,
    trip_schedule_relationship
   FROM transit.trip_updates_raw
  ORDER BY trip_id, feed_header_timestamp DESC, id DESC;


ALTER VIEW transit.v_latest_trip_updates OWNER TO postgres;

--
-- Name: vehicle_positions_raw; Type: TABLE; Schema: transit; Owner: postgres
--

CREATE TABLE transit.vehicle_positions_raw (
    id bigint NOT NULL,
    downloaded_at timestamp with time zone DEFAULT now() NOT NULL,
    feed_header_timestamp timestamp with time zone,
    feed_entity_id text NOT NULL,
    trip_id text NOT NULL,
    vehicle_id text NOT NULL,
    lat double precision NOT NULL,
    lon double precision NOT NULL,
    vehicle_timestamp timestamp with time zone NOT NULL,
    raw_sha256 text
);


ALTER TABLE transit.vehicle_positions_raw OWNER TO postgres;

--
-- Name: v_latest_vehicle_positions; Type: VIEW; Schema: transit; Owner: postgres
--

CREATE VIEW transit.v_latest_vehicle_positions AS
 SELECT DISTINCT ON (vehicle_id) vehicle_id,
    trip_id,
    vehicle_timestamp,
    lat,
    lon
   FROM transit.vehicle_positions_raw
  ORDER BY vehicle_id, vehicle_timestamp DESC;


ALTER VIEW transit.v_latest_vehicle_positions OWNER TO postgres;

--
-- Name: v_latest_vehicle_positions_enriched; Type: VIEW; Schema: transit; Owner: postgres
--

CREATE VIEW transit.v_latest_vehicle_positions_enriched AS
 SELECT lv.vehicle_id,
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
   FROM ((transit.v_latest_vehicle_positions lv
     LEFT JOIN transit.trips t ON ((t.trip_id = lv.trip_id)))
     LEFT JOIN transit.routes r ON ((r.route_id = t.route_id)));


ALTER VIEW transit.v_latest_vehicle_positions_enriched OWNER TO postgres;

--
-- Name: v_latest_vehicle_positions_frontend; Type: VIEW; Schema: transit; Owner: postgres
--

CREATE VIEW transit.v_latest_vehicle_positions_frontend AS
 WITH latest_tripupdates AS (
         SELECT DISTINCT trip_updates_raw.trip_id
           FROM transit.trip_updates_raw
        )
 SELECT lv.vehicle_id,
    lv.trip_id,
    lv.vehicle_timestamp,
    (lv.vehicle_timestamp AT TIME ZONE 'America/Edmonton'::text) AS vehicle_timestamp_edmonton,
    lv.lat,
    lv.lon,
    t.route_id AS static_route_id,
    r.route_short_name,
    r.route_long_name,
    t.trip_headsign,
    t.direction_id,
    t.shape_id,
        CASE
            WHEN (t.trip_id IS NOT NULL) THEN true
            ELSE false
        END AS matched_to_static,
        CASE
            WHEN (ltu.trip_id IS NOT NULL) THEN true
            ELSE false
        END AS has_trip_update,
        CASE
            WHEN (t.trip_id IS NULL) THEN 'unmatched_live'::text
            WHEN (ltu.trip_id IS NULL) THEN 'matched_no_tripupdate'::text
            ELSE 'in_service'::text
        END AS vehicle_status
   FROM (((transit.v_latest_vehicle_positions lv
     LEFT JOIN transit.trips t ON ((t.trip_id = lv.trip_id)))
     LEFT JOIN transit.routes r ON ((r.route_id = t.route_id)))
     LEFT JOIN latest_tripupdates ltu ON ((ltu.trip_id = lv.trip_id)));


ALTER VIEW transit.v_latest_vehicle_positions_frontend OWNER TO postgres;

--
-- Name: v_latest_vehicle_positions_frontend_v2; Type: VIEW; Schema: transit; Owner: postgres
--

CREATE VIEW transit.v_latest_vehicle_positions_frontend_v2 AS
 WITH latest_tripupdates AS (
         SELECT DISTINCT trip_updates_raw.trip_id
           FROM transit.trip_updates_raw
        )
 SELECT lv.vehicle_id,
    lv.trip_id,
    lv.vehicle_timestamp,
    (lv.vehicle_timestamp AT TIME ZONE 'America/Edmonton'::text) AS vehicle_timestamp_edmonton,
    lv.lat,
    lv.lon,
    t.route_id AS static_route_id,
    r.route_short_name,
    r.route_long_name,
    t.trip_headsign,
    t.direction_id,
    t.shape_id,
        CASE
            WHEN (t.trip_id IS NOT NULL) THEN true
            ELSE false
        END AS matched_to_static,
        CASE
            WHEN (ltu.trip_id IS NOT NULL) THEN true
            ELSE false
        END AS has_trip_update,
        CASE
            WHEN (t.trip_id IS NULL) THEN 'unmatched_live'::text
            WHEN (ltu.trip_id IS NULL) THEN 'matched_no_tripupdate'::text
            ELSE 'in_service'::text
        END AS vehicle_status
   FROM (((transit.v_latest_vehicle_positions lv
     LEFT JOIN transit.trips t ON ((t.trip_id = lv.trip_id)))
     LEFT JOIN transit.routes r ON ((r.route_id = t.route_id)))
     LEFT JOIN latest_tripupdates ltu ON ((ltu.trip_id = lv.trip_id)));


ALTER VIEW transit.v_latest_vehicle_positions_frontend_v2 OWNER TO postgres;

--
-- Name: v_route_catalog_lookup; Type: VIEW; Schema: transit; Owner: postgres
--

CREATE VIEW transit.v_route_catalog_lookup AS
 SELECT upper(TRIM(BOTH FROM route_short_name)) AS route_short_name_norm,
    TRIM(BOTH FROM route_short_name) AS route_short_name,
    TRIM(BOTH FROM route_long_name) AS route_long_name,
    upper(TRIM(BOTH FROM route_category)) AS route_category
   FROM transit.route_catalog_raw;


ALTER VIEW transit.v_route_catalog_lookup OWNER TO postgres;

--
-- Name: v_trip_upcoming_stops; Type: VIEW; Schema: transit; Owner: postgres
--

CREATE VIEW transit.v_trip_upcoming_stops AS
 SELECT tu.trip_id,
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
   FROM ((((transit.trip_updates_current tu
     LEFT JOIN transit.trips t ON ((t.trip_id = tu.trip_id)))
     LEFT JOIN transit.routes r ON ((r.route_id = t.route_id)))
     LEFT JOIN transit.trip_update_stop_times_current stu ON ((stu.trip_id = tu.trip_id)))
     LEFT JOIN transit.stops s ON ((s.stop_id = stu.stop_id)));


ALTER VIEW transit.v_trip_upcoming_stops OWNER TO postgres;

--
-- Name: v_trip_updates_enriched; Type: VIEW; Schema: transit; Owner: postgres
--

CREATE VIEW transit.v_trip_updates_enriched AS
 SELECT tu.downloaded_at,
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
   FROM ((((transit.trip_updates_raw tu
     LEFT JOIN transit.trips t ON ((t.trip_id = tu.trip_id)))
     LEFT JOIN transit.routes r ON ((r.route_id = t.route_id)))
     LEFT JOIN transit.trip_update_stop_times_raw stu ON ((stu.trip_update_raw_id = tu.id)))
     LEFT JOIN transit.stops s ON ((s.stop_id = stu.stop_id)));


ALTER VIEW transit.v_trip_updates_enriched OWNER TO postgres;

--
-- Name: vehicle_positions_current; Type: TABLE; Schema: transit; Owner: postgres
--

CREATE TABLE transit.vehicle_positions_current (
    vehicle_id text NOT NULL,
    trip_id text NOT NULL,
    feed_entity_id text,
    vehicle_timestamp timestamp with time zone NOT NULL,
    feed_header_timestamp timestamp with time zone,
    lat double precision NOT NULL,
    lon double precision NOT NULL,
    raw_sha256 text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE transit.vehicle_positions_current OWNER TO postgres;

--
-- Name: v_vehicle_dashboard; Type: VIEW; Schema: transit; Owner: postgres
--

CREATE VIEW transit.v_vehicle_dashboard AS
 WITH latest_tripupdates AS (
         SELECT DISTINCT trip_updates_current.trip_id
           FROM transit.trip_updates_current
        )
 SELECT v.vehicle_id,
    v.trip_id,
    v.vehicle_timestamp,
    (v.vehicle_timestamp AT TIME ZONE 'America/Edmonton'::text) AS vehicle_timestamp_edmonton,
    v.lat,
    v.lon,
    t.route_id AS static_route_id,
    r.route_short_name,
    r.route_long_name,
    t.trip_headsign,
    t.direction_id,
    t.shape_id,
    COALESCE(rc.route_category,
        CASE
            WHEN (r.route_long_name ~~* 'MAX %'::text) THEN 'MAX'::text
            WHEN (r.route_short_name = ANY (ARRAY['MG'::text, 'MO'::text, 'MP'::text, 'MT'::text, 'MY'::text])) THEN 'MAX'::text
            WHEN (r.route_short_name = ANY (ARRAY['201'::text, '202'::text])) THEN 'LRT'::text
            ELSE NULL::text
        END) AS route_category,
        CASE
            WHEN (t.trip_id IS NOT NULL) THEN true
            ELSE false
        END AS matched_to_static,
        CASE
            WHEN (ltu.trip_id IS NOT NULL) THEN true
            ELSE false
        END AS has_trip_update,
        CASE
            WHEN (t.trip_id IS NULL) THEN 'unmatched_live'::text
            WHEN (ltu.trip_id IS NULL) THEN 'matched_no_tripupdate'::text
            ELSE 'in_service'::text
        END AS vehicle_status,
        CASE
            WHEN (COALESCE(rc.route_category,
            CASE
                WHEN (r.route_long_name ~~* 'MAX %'::text) THEN 'MAX'::text
                WHEN (r.route_short_name = ANY (ARRAY['MG'::text, 'MO'::text, 'MP'::text, 'MT'::text, 'MY'::text])) THEN 'MAX'::text
                WHEN (r.route_short_name = ANY (ARRAY['201'::text, '202'::text])) THEN 'LRT'::text
                ELSE NULL::text
            END) = 'LRT'::text) THEN 'lrt'::text
            WHEN (COALESCE(rc.route_category,
            CASE
                WHEN (r.route_long_name ~~* 'MAX %'::text) THEN 'MAX'::text
                WHEN (r.route_short_name = ANY (ARRAY['MG'::text, 'MO'::text, 'MP'::text, 'MT'::text, 'MY'::text])) THEN 'MAX'::text
                ELSE NULL::text
            END) = ANY (ARRAY['BRT'::text, 'MAX'::text, 'EXPRESS'::text])) THEN 'brt'::text
            WHEN (COALESCE(rc.route_category, 'REGULAR'::text) = ANY (ARRAY['REGULAR'::text, 'SCHOOL'::text, 'SPECIAL'::text])) THEN 'bus'::text
            ELSE 'unknown'::text
        END AS route_mode
   FROM ((((transit.vehicle_positions_current v
     LEFT JOIN transit.trips t ON ((t.trip_id = v.trip_id)))
     LEFT JOIN transit.routes r ON ((r.route_id = t.route_id)))
     LEFT JOIN transit.v_route_catalog_lookup rc ON ((upper(TRIM(BOTH FROM r.route_short_name)) = rc.route_short_name_norm)))
     LEFT JOIN latest_tripupdates ltu ON ((ltu.trip_id = v.trip_id)));


ALTER VIEW transit.v_vehicle_dashboard OWNER TO postgres;

--
-- Name: v_vehicle_positions_enriched; Type: VIEW; Schema: transit; Owner: postgres
--

CREATE VIEW transit.v_vehicle_positions_enriched AS
 SELECT v.downloaded_at,
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
   FROM ((transit.vehicle_positions_raw v
     LEFT JOIN transit.trips t ON ((t.trip_id = v.trip_id)))
     LEFT JOIN transit.routes r ON ((r.route_id = t.route_id)));


ALTER VIEW transit.v_vehicle_positions_enriched OWNER TO postgres;

--
-- Name: vehicle_positions_raw_id_seq; Type: SEQUENCE; Schema: transit; Owner: postgres
--

CREATE SEQUENCE transit.vehicle_positions_raw_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE transit.vehicle_positions_raw_id_seq OWNER TO postgres;

--
-- Name: vehicle_positions_raw_id_seq; Type: SEQUENCE OWNED BY; Schema: transit; Owner: postgres
--

ALTER SEQUENCE transit.vehicle_positions_raw_id_seq OWNED BY transit.vehicle_positions_raw.id;


--
-- Name: alert_informed_entities_current id; Type: DEFAULT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.alert_informed_entities_current ALTER COLUMN id SET DEFAULT nextval('transit.alert_informed_entities_current_id_seq'::regclass);


--
-- Name: alert_informed_entities_raw id; Type: DEFAULT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.alert_informed_entities_raw ALTER COLUMN id SET DEFAULT nextval('transit.alert_informed_entities_raw_id_seq'::regclass);


--
-- Name: alerts_raw id; Type: DEFAULT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.alerts_raw ALTER COLUMN id SET DEFAULT nextval('transit.alerts_raw_id_seq'::regclass);


--
-- Name: trip_update_stop_times_raw id; Type: DEFAULT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.trip_update_stop_times_raw ALTER COLUMN id SET DEFAULT nextval('transit.trip_update_stop_times_raw_id_seq'::regclass);


--
-- Name: trip_updates_raw id; Type: DEFAULT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.trip_updates_raw ALTER COLUMN id SET DEFAULT nextval('transit.trip_updates_raw_id_seq'::regclass);


--
-- Name: vehicle_positions_raw id; Type: DEFAULT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.vehicle_positions_raw ALTER COLUMN id SET DEFAULT nextval('transit.vehicle_positions_raw_id_seq'::regclass);


--
-- Name: alert_informed_entities_current alert_informed_entities_current_pkey; Type: CONSTRAINT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.alert_informed_entities_current
    ADD CONSTRAINT alert_informed_entities_current_pkey PRIMARY KEY (id);


--
-- Name: alert_informed_entities_raw alert_informed_entities_raw_pkey; Type: CONSTRAINT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.alert_informed_entities_raw
    ADD CONSTRAINT alert_informed_entities_raw_pkey PRIMARY KEY (id);


--
-- Name: alerts_current alerts_current_pkey; Type: CONSTRAINT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.alerts_current
    ADD CONSTRAINT alerts_current_pkey PRIMARY KEY (feed_entity_id);


--
-- Name: alerts_raw alerts_raw_pkey; Type: CONSTRAINT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.alerts_raw
    ADD CONSTRAINT alerts_raw_pkey PRIMARY KEY (id);


--
-- Name: calendar calendar_pkey; Type: CONSTRAINT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.calendar
    ADD CONSTRAINT calendar_pkey PRIMARY KEY (service_id);


--
-- Name: routes routes_pkey; Type: CONSTRAINT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.routes
    ADD CONSTRAINT routes_pkey PRIMARY KEY (route_id);


--
-- Name: stops stops_pkey; Type: CONSTRAINT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.stops
    ADD CONSTRAINT stops_pkey PRIMARY KEY (stop_id);


--
-- Name: trip_update_stop_times_current trip_update_stop_times_current_pkey; Type: CONSTRAINT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.trip_update_stop_times_current
    ADD CONSTRAINT trip_update_stop_times_current_pkey PRIMARY KEY (trip_id, stop_sequence);


--
-- Name: trip_update_stop_times_raw trip_update_stop_times_raw_pkey; Type: CONSTRAINT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.trip_update_stop_times_raw
    ADD CONSTRAINT trip_update_stop_times_raw_pkey PRIMARY KEY (id);


--
-- Name: trip_updates_current trip_updates_current_pkey; Type: CONSTRAINT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.trip_updates_current
    ADD CONSTRAINT trip_updates_current_pkey PRIMARY KEY (trip_id);


--
-- Name: trip_updates_raw trip_updates_raw_pkey; Type: CONSTRAINT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.trip_updates_raw
    ADD CONSTRAINT trip_updates_raw_pkey PRIMARY KEY (id);


--
-- Name: trips trips_pkey; Type: CONSTRAINT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.trips
    ADD CONSTRAINT trips_pkey PRIMARY KEY (trip_id);


--
-- Name: vehicle_positions_current vehicle_positions_current_pkey; Type: CONSTRAINT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.vehicle_positions_current
    ADD CONSTRAINT vehicle_positions_current_pkey PRIMARY KEY (vehicle_id);


--
-- Name: vehicle_positions_raw vehicle_positions_raw_pkey; Type: CONSTRAINT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.vehicle_positions_raw
    ADD CONSTRAINT vehicle_positions_raw_pkey PRIMARY KEY (id);


--
-- Name: idx_alert_inf_alert_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_alert_inf_alert_id ON transit.alert_informed_entities_raw USING btree (alert_raw_id);


--
-- Name: idx_alert_inf_route_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_alert_inf_route_id ON transit.alert_informed_entities_raw USING btree (route_id);


--
-- Name: idx_alert_inf_stop_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_alert_inf_stop_id ON transit.alert_informed_entities_raw USING btree (stop_id);


--
-- Name: idx_alert_informed_entities_alert; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_alert_informed_entities_alert ON transit.alert_informed_entities_raw USING btree (alert_raw_id);


--
-- Name: idx_alert_informed_entities_current_route_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_alert_informed_entities_current_route_id ON transit.alert_informed_entities_current USING btree (route_id);


--
-- Name: idx_alert_informed_entities_current_stop_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_alert_informed_entities_current_stop_id ON transit.alert_informed_entities_current USING btree (stop_id);


--
-- Name: idx_alert_informed_entities_route; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_alert_informed_entities_route ON transit.alert_informed_entities_raw USING btree (route_id);


--
-- Name: idx_alert_informed_entities_stop; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_alert_informed_entities_stop ON transit.alert_informed_entities_raw USING btree (stop_id);


--
-- Name: idx_alerts_active_end; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_alerts_active_end ON transit.alerts_raw USING btree (active_end);


--
-- Name: idx_alerts_active_start; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_alerts_active_start ON transit.alerts_raw USING btree (active_start);


--
-- Name: idx_calendar_dates_date; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_calendar_dates_date ON transit.calendar_dates USING btree (date);


--
-- Name: idx_calendar_dates_service_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_calendar_dates_service_id ON transit.calendar_dates USING btree (service_id);


--
-- Name: idx_shapes_shape_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_shapes_shape_id ON transit.shapes USING btree (shape_id);


--
-- Name: idx_shapes_shape_id_seq; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_shapes_shape_id_seq ON transit.shapes USING btree (shape_id, shape_pt_sequence);


--
-- Name: idx_stop_times_stop_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_stop_times_stop_id ON transit.stop_times USING btree (stop_id);


--
-- Name: idx_stop_times_trip_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_stop_times_trip_id ON transit.stop_times USING btree (trip_id);


--
-- Name: idx_stop_times_trip_seq; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_stop_times_trip_seq ON transit.stop_times USING btree (trip_id, stop_sequence);


--
-- Name: idx_trip_update_stop_times_current_stop_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_trip_update_stop_times_current_stop_id ON transit.trip_update_stop_times_current USING btree (stop_id);


--
-- Name: idx_trip_update_stop_times_parent; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_trip_update_stop_times_parent ON transit.trip_update_stop_times_raw USING btree (trip_update_raw_id);


--
-- Name: idx_trip_update_stop_times_stop_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_trip_update_stop_times_stop_id ON transit.trip_update_stop_times_raw USING btree (stop_id);


--
-- Name: idx_trip_updates_route_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_trip_updates_route_id ON transit.trip_updates_raw USING btree (route_id);


--
-- Name: idx_trip_updates_trip_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_trip_updates_trip_id ON transit.trip_updates_raw USING btree (trip_id);


--
-- Name: idx_trips_route_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_trips_route_id ON transit.trips USING btree (route_id);


--
-- Name: idx_trips_service_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_trips_service_id ON transit.trips USING btree (service_id);


--
-- Name: idx_trips_shape_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_trips_shape_id ON transit.trips USING btree (shape_id);


--
-- Name: idx_tu_stop_times_stop_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_tu_stop_times_stop_id ON transit.trip_update_stop_times_raw USING btree (stop_id);


--
-- Name: idx_tu_stop_times_trip_update_raw_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_tu_stop_times_trip_update_raw_id ON transit.trip_update_stop_times_raw USING btree (trip_update_raw_id);


--
-- Name: idx_vehicle_positions_current_trip_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_vehicle_positions_current_trip_id ON transit.vehicle_positions_current USING btree (trip_id);


--
-- Name: idx_vehicle_positions_trip_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_vehicle_positions_trip_id ON transit.vehicle_positions_raw USING btree (trip_id);


--
-- Name: idx_vehicle_positions_vehicle_id; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_vehicle_positions_vehicle_id ON transit.vehicle_positions_raw USING btree (vehicle_id);


--
-- Name: idx_vehicle_positions_vehicle_ts; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE INDEX idx_vehicle_positions_vehicle_ts ON transit.vehicle_positions_raw USING btree (vehicle_timestamp);


--
-- Name: uq_alert_informed_entities_current; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE UNIQUE INDEX uq_alert_informed_entities_current ON transit.alert_informed_entities_current USING btree (feed_entity_id, COALESCE(agency_id, ''::text), COALESCE(route_id, ''::text), COALESCE(stop_id, ''::text));


--
-- Name: uq_alert_informed_entities_obs; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE UNIQUE INDEX uq_alert_informed_entities_obs ON transit.alert_informed_entities_raw USING btree (alert_raw_id, COALESCE(agency_id, ''::text), COALESCE(route_id, ''::text), COALESCE(stop_id, ''::text));


--
-- Name: uq_alerts_obs; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE UNIQUE INDEX uq_alerts_obs ON transit.alerts_raw USING btree (feed_entity_id, feed_header_timestamp);


--
-- Name: uq_trip_update_stop_times_obs; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE UNIQUE INDEX uq_trip_update_stop_times_obs ON transit.trip_update_stop_times_raw USING btree (trip_update_raw_id, stop_sequence, stop_id, arrival_time, departure_time);


--
-- Name: uq_trip_updates_obs; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE UNIQUE INDEX uq_trip_updates_obs ON transit.trip_updates_raw USING btree (feed_entity_id, feed_header_timestamp);


--
-- Name: uq_vehicle_positions_obs; Type: INDEX; Schema: transit; Owner: postgres
--

CREATE UNIQUE INDEX uq_vehicle_positions_obs ON transit.vehicle_positions_raw USING btree (trip_id, vehicle_id, vehicle_timestamp);


--
-- Name: alert_informed_entities_raw alert_informed_entities_raw_alert_raw_id_fkey; Type: FK CONSTRAINT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.alert_informed_entities_raw
    ADD CONSTRAINT alert_informed_entities_raw_alert_raw_id_fkey FOREIGN KEY (alert_raw_id) REFERENCES transit.alerts_raw(id) ON DELETE CASCADE;


--
-- Name: trip_update_stop_times_raw trip_update_stop_times_raw_trip_update_raw_id_fkey; Type: FK CONSTRAINT; Schema: transit; Owner: postgres
--

ALTER TABLE ONLY transit.trip_update_stop_times_raw
    ADD CONSTRAINT trip_update_stop_times_raw_trip_update_raw_id_fkey FOREIGN KEY (trip_update_raw_id) REFERENCES transit.trip_updates_raw(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict CWCrH22cJFDgLOC1g9uYOmdE9BWdVu8ey0v6saBNu5SftX0yw7G7aCCRLmwiLzN

