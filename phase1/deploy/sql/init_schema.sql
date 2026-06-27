CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS acled_events (
    event_id_cnty       TEXT PRIMARY KEY,
    event_date          DATE NOT NULL,
    year                INTEGER NOT NULL,
    time_precision      SMALLINT,
    disorder_type       TEXT NOT NULL,
    event_type          TEXT NOT NULL,
    sub_event_type      TEXT,
    actor1              TEXT,
    assoc_actor_1       TEXT,
    inter1              TEXT,
    actor2              TEXT,
    assoc_actor_2       TEXT,
    inter2              TEXT,
    interaction         TEXT,
    civilian_targeting  TEXT,
    iso                 INTEGER,
    region              TEXT,
    country             TEXT,
    admin1              TEXT,
    admin2              TEXT,
    admin3              TEXT,
    location            TEXT,
    latitude            DOUBLE PRECISION,
    longitude           DOUBLE PRECISION,
    geo_precision       SMALLINT,
    source              TEXT,
    source_scale        TEXT,
    notes               TEXT,
    fatalities          INTEGER DEFAULT 0,
    tags                TEXT,
    timestamp           BIGINT,
    population_best     INTEGER,
    population_1km      INTEGER,
    population_2km      INTEGER,
    population_5km      INTEGER,
    geom                GEOMETRY(Point, 4326),
    ingested_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_acled_geom ON acled_events USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_acled_event_date ON acled_events (event_date);
CREATE INDEX IF NOT EXISTS idx_acled_event_type ON acled_events (event_type);
CREATE INDEX IF NOT EXISTS idx_acled_date_type ON acled_events (event_date, event_type);
CREATE INDEX IF NOT EXISTS idx_acled_country ON acled_events (country);
CREATE INDEX IF NOT EXISTS idx_acled_timestamp ON acled_events (timestamp);

CREATE TABLE IF NOT EXISTS ingestion_log (
    id              SERIAL PRIMARY KEY,
    phase           TEXT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL,
    completed_at    TIMESTAMPTZ,
    status          TEXT NOT NULL,
    events_upserted INTEGER DEFAULT 0,
    date_from       DATE,
    date_to         DATE,
    last_timestamp  BIGINT,
    error_message   TEXT,
    metadata        JSONB
);

CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    display_name    TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    is_active       BOOLEAN DEFAULT TRUE
);

