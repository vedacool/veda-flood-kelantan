-- VEDA operational store (veda-pg). Applied by scripts/setup_pg.py; safe to re-run (IF NOT EXISTS only).
-- Python writes here directly; agents read it back only through Zetaris (datasource veda_pg).
-- Times are UTC (timestamptz). Later backlog items fill these tables and may add columns.

-- Gauging stations. station_key is VEDA's own id: JPS ids can be blank and data.gov.my uses old ids (B-64 spike 5).
CREATE TABLE IF NOT EXISTS stations (
    station_key      text PRIMARY KEY,          -- e.g. 'kelantan_tambatan_diraja'
    name             text NOT NULL,             -- JPS display name
    name_norm        text NOT NULL,             -- lower-case, no brackets/punctuation (join key fallback)
    river            text,
    district         text,
    state            text NOT NULL DEFAULT 'KEL',
    jps_id           text,                      -- nullable: 8/36 Kelantan JPS rows have no id
    mygov_id         text,                      -- data.gov.my /flood-warning station_id
    mygov_code       text,                      -- data.gov.my station_code
    lat              double precision,
    lon              double precision,
    normal_m         double precision,
    alert_m          double precision,
    warning_m        double precision,
    danger_m         double precision,
    updated_at       timestamptz NOT NULL DEFAULT now()
);

-- River level readings scraped from JPS (B-06). One row per station per observation time.
CREATE TABLE IF NOT EXISTS river_levels (
    station_key      text NOT NULL,
    observed_at      timestamptz NOT NULL,      -- JPS "Last Update"
    level_m          double precision,
    source           text NOT NULL,             -- e.g. 'jps-live', 'jps-snapshot'
    scraped_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (station_key, observed_at)
);

-- Places a user can ask about (B-09 gazetteer).
CREATE TABLE IF NOT EXISTS places (
    place_id             text PRIMARY KEY,
    name                 text NOT NULL,
    name_norm            text NOT NULL,
    kind                 text NOT NULL CHECK (kind IN ('kampung', 'town', 'district', 'school')),
    district             text,
    lat                  double precision,
    lon                  double precision,
    nearest_station_key  text
);

-- Historic flood peaks for "bigger than 2014?" comparisons. Every row cites its source.
CREATE TABLE IF NOT EXISTS historic_peaks (
    station_key      text NOT NULL,
    event            text NOT NULL,             -- e.g. 'Dec 2014'
    peak_m           double precision NOT NULL,
    source_url       text NOT NULL,
    reconstructed    boolean NOT NULL DEFAULT false,  -- true when built from reported figures (safety rule 5)
    PRIMARY KEY (station_key, event)
);

-- Source registry: which sources VEDA knows, their trust status and health. Values seeded later (KIV, Dr Ariff).
CREATE TABLE IF NOT EXISTS source_registry (
    source_id          text PRIMARY KEY,
    name               text NOT NULL,
    kind               text NOT NULL,           -- e.g. 'rest_table', 'scrape', 'postgres'
    url                text,
    status             text NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate', 'trusted', 'disabled')),
    freshness_sla_min  integer,                 -- nullable until agreed
    last_ok_at         timestamptz,
    fail_count         integer NOT NULL DEFAULT 0,
    notes              text
);

-- Zetaris reads as a read-only role.
GRANT USAGE ON SCHEMA public TO veda_zetaris;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO veda_zetaris;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO veda_zetaris;

-- B-67: curated station mapping (from data/stations_mapping.csv via scripts/seed_stations.py).
-- The JPS collector never writes these columns, so curated values survive every scrape.
ALTER TABLE stations
    ADD COLUMN IF NOT EXISTS brief_name text,           -- name used in BUILD_BRIEF, e.g. 'Sg Kelantan @ Jambatan Guillemard'
    ADD COLUMN IF NOT EXISTS is_core boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS chain text,                -- 'kelantan-main', 'kelantan-galas', 'kelantan-lebir', 'golok'
    ADD COLUMN IF NOT EXISTS chain_order integer,       -- position along the chain, upstream = 1
    ADD COLUMN IF NOT EXISTS role text,
    ADD COLUMN IF NOT EXISTS controls_town text,
    ADD COLUMN IF NOT EXISTS backup_of text,            -- station_key this gauge stands in for when that one is stale
    ADD COLUMN IF NOT EXISTS mapping_status text,       -- 'verified - …' / 'tentative - needs Dr Ariff'
    ADD COLUMN IF NOT EXISTS mapping_note text,
    ADD COLUMN IF NOT EXISTS coords_source text;

-- Relations between gauges: upstream_of (adjacent along a chain), backup_for, travel_time (lag range, any pair).
CREATE TABLE IF NOT EXISTS station_links (
    from_key    text NOT NULL REFERENCES stations (station_key),
    to_key      text NOT NULL REFERENCES stations (station_key),
    link_type   text NOT NULL CHECK (link_type IN ('upstream_of', 'backup_for', 'travel_time')),
    lag_min_h   double precision,
    lag_max_h   double precision,
    lag_source  text,
    status      text NOT NULL,
    notes       text,
    PRIMARY KEY (from_key, to_key, link_type),
    CHECK (from_key <> to_key),
    CHECK (lag_min_h IS NULL OR lag_max_h IS NULL OR lag_min_h <= lag_max_h)
);

-- B-55: historic peaks with provenance. Official JPS figures and news-reported figures are kept apart
-- (source_type); news values for the same event may disagree - each row cites its own source.
ALTER TABLE historic_peaks
    ADD COLUMN IF NOT EXISTS observed_when text,        -- as given by the source, e.g. '24 Dec 2014 16:00'
    ADD COLUMN IF NOT EXISTS source_type text,          -- 'official' (JPS) | 'news' (reported)
    ADD COLUMN IF NOT EXISTS source_name text,
    ADD COLUMN IF NOT EXISTS normal_m double precision, -- thresholds in force at the time (2014 JPS table)
    ADD COLUMN IF NOT EXISTS alert_m double precision,
    ADD COLUMN IF NOT EXISTS warning_m double precision,
    ADD COLUMN IF NOT EXISTS danger_m double precision,
    ADD COLUMN IF NOT EXISTS notes text;

-- B-08: rain points (from data/rain_points.csv via scripts/setup_wx.py) so Zetaris views can name each
-- Open-Meteo row: om_rain row COALESCE(location_id, 0) = rain_points.location_id.
CREATE TABLE IF NOT EXISTS rain_points (
    location_id    integer PRIMARY KEY,
    point_key      text NOT NULL UNIQUE,
    station_key    text REFERENCES stations (station_key),
    name           text,
    lat            double precision NOT NULL,
    lon            double precision NOT NULL,
    role           text,
    coords_source  text,
    status         text NOT NULL
);

-- B-09: gazetteer. places (existing table) gets provenance + links to its rain point and forecast;
-- place_aliases holds normalised spellings; place_gauges says which gauges represent a place.
ALTER TABLE places
    ADD COLUMN IF NOT EXISTS coords_source text,
    ADD COLUMN IF NOT EXISTS rain_location_id integer,      -- nearest rain point (rain_points.location_id)
    ADD COLUMN IF NOT EXISTS forecast_location_id text,     -- data.gov.my forecast location, e.g. 'Tn032'
    ADD COLUMN IF NOT EXISTS mapping_status text,
    ADD COLUMN IF NOT EXISTS notes text;

CREATE TABLE IF NOT EXISTS place_aliases (
    alias_norm  text PRIMARY KEY,                           -- normalised by app.gazetteer.normalize()
    place_id    text NOT NULL REFERENCES places (place_id),
    alias       text NOT NULL                               -- as written in data/places.csv
);

CREATE TABLE IF NOT EXISTS place_gauges (
    place_id     text NOT NULL REFERENCES places (place_id),
    station_key  text NOT NULL REFERENCES stations (station_key),
    role         text NOT NULL CHECK (role IN ('controlling', 'controlling_secondary', 'sentinel')),
    sort_order   integer NOT NULL DEFAULT 1,
    PRIMARY KEY (place_id, station_key)
);
