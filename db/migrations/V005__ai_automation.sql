BEGIN;

ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS automation_run BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS automation_note TEXT;

CREATE TABLE IF NOT EXISTS ai_automation_config (
    user_id BIGINT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    trigger_mode VARCHAR(30) NOT NULL DEFAULT 'interval'
        CHECK (trigger_mode IN ('interval', 'recommendation_change')),
    interval_minutes INTEGER NOT NULL DEFAULT 360 CHECK (interval_minutes BETWEEN 60 AND 1440),
    auto_apply_settings BOOLEAN NOT NULL DEFAULT FALSE,
    last_fingerprint VARCHAR(64),
    last_started_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,
    last_analysis_id BIGINT,
    last_error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;
