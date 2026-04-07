-- LR-AutoTag: Initial schema

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Batch-Jobs
CREATE TABLE IF NOT EXISTS batch_jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending, running, paused, done, cancelled
    total_images  INTEGER NOT NULL,
    processed     INTEGER NOT NULL DEFAULT 0,
    failed        INTEGER NOT NULL DEFAULT 0,
    skipped       INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Chunks innerhalb eines Batch-Jobs
CREATE TABLE IF NOT EXISTS chunks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id      UUID NOT NULL REFERENCES batch_jobs(id) ON DELETE CASCADE,
    status        TEXT NOT NULL DEFAULT 'pending',  -- pending, processing, done, failed
    image_ids     TEXT[] NOT NULL,
    attempt       INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at    TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_chunks_batch_status ON chunks(batch_id, status);

-- Ergebnisse pro Bild
CREATE TABLE IF NOT EXISTS image_keywords (
    image_id        TEXT PRIMARY KEY,
    keywords        TEXT[] NOT NULL,
    geo_keywords    TEXT[],
    vision_keywords TEXT[],
    gps_lat         DOUBLE PRECISION,
    gps_lon         DOUBLE PRECISION,
    location_name   TEXT,
    model_used      TEXT NOT NULL,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Batch image metadata (GPS etc., submitted by plugin at batch start)
CREATE TABLE IF NOT EXISTS batch_images (
    batch_id    UUID NOT NULL REFERENCES batch_jobs(id) ON DELETE CASCADE,
    image_id    TEXT NOT NULL,
    gps_lat     DOUBLE PRECISION,
    gps_lon     DOUBLE PRECISION,
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending, done, failed
    PRIMARY KEY (batch_id, image_id)
);

CREATE INDEX IF NOT EXISTS idx_batch_images_pending ON batch_images(batch_id, status);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version  INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO schema_version (version) VALUES (1) ON CONFLICT DO NOTHING;
