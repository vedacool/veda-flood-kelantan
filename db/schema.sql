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
