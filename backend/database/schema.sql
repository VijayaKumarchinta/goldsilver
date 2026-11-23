CREATE SCHEMA IF NOT EXISTS goldbot;
SET search_path TO goldbot;

CREATE TABLE IF NOT EXISTS price_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    event_type      VARCHAR(50) NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    base_currency   CHAR(3) NOT NULL DEFAULT 'USD',
    output_currency CHAR(3) NOT NULL DEFAULT 'INR',
    CONSTRAINT uq_snapshot_event_time UNIQUE (event_type, captured_at)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_captured ON price_snapshots (captured_at DESC);

CREATE TABLE IF NOT EXISTS metal_prices (
    id                  BIGSERIAL PRIMARY KEY,
    snapshot_id         BIGINT NOT NULL REFERENCES price_snapshots(id) ON DELETE CASCADE,
    symbol              VARCHAR(3) NOT NULL,
    usd_per_oz          NUMERIC(18,6) NOT NULL,
    inr_per_gram        NUMERIC(18,4) NOT NULL,
    provider            VARCHAR(50) NOT NULL,
    provider_updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_metal_snapshot UNIQUE (snapshot_id, symbol),
    CONSTRAINT chk_metal_symbol CHECK (symbol IN ('XAU','XAG'))
);

CREATE TABLE IF NOT EXISTS fx_rates (
    id          BIGSERIAL PRIMARY KEY,
    snapshot_id BIGINT NOT NULL REFERENCES price_snapshots(id) ON DELETE CASCADE,
    base        CHAR(3) NOT NULL,
    quote       CHAR(3) NOT NULL,
    rate        NUMERIC(18,8) NOT NULL,
    provider    VARCHAR(50) NOT NULL,
    CONSTRAINT uq_fx_snapshot UNIQUE (snapshot_id, base, quote)
);

CREATE TABLE IF NOT EXISTS destinations (
    id          BIGSERIAL PRIMARY KEY,
    channel     VARCHAR(20) NOT NULL,
    identifier  VARCHAR(255) NOT NULL,
    label       VARCHAR(100),
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_destination UNIQUE (channel, identifier),
    CONSTRAINT chk_channel CHECK (channel IN ('telegram'))
);

CREATE TABLE IF NOT EXISTS notification_jobs (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_id     BIGINT NOT NULL REFERENCES price_snapshots(id) ON DELETE CASCADE,
    destination_id  BIGINT NOT NULL REFERENCES destinations(id) ON DELETE CASCADE,
    event_type      VARCHAR(50) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts        INT NOT NULL DEFAULT 0,
    last_error      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scheduled_for   TIMESTAMPTZ,
    CONSTRAINT uq_job_dedupe UNIQUE (snapshot_id, event_type, destination_id),
    CONSTRAINT chk_job_status CHECK (status IN ('pending','sending','sent','failed'))
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON notification_jobs (status) WHERE status IN ('pending','sending');
CREATE UNIQUE INDEX IF NOT EXISTS idx_notification_schedule_slot
    ON notification_jobs (event_type, scheduled_for, destination_id)
    WHERE scheduled_for IS NOT NULL;