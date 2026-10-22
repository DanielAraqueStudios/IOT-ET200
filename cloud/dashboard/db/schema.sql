-- Minimal schema: current + historical state for PLC tags.
-- Every MQTT message received is inserted as a new row (history);
-- "current" value per tag is just the latest row for that tag_name.
CREATE TABLE IF NOT EXISTS plc_state (
    id         BIGSERIAL PRIMARY KEY,
    tag_name   TEXT NOT NULL,
    value      TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_plc_state_tag_name_updated_at
    ON plc_state (tag_name, updated_at DESC);
