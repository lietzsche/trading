BEGIN;

CREATE TABLE IF NOT EXISTS ai_credentials (
    user_id BIGINT PRIMARY KEY,
    encrypted_key TEXT NOT NULL,
    key_hint VARCHAR(12) NOT NULL,
    model VARCHAR(80) NOT NULL DEFAULT 'deepseek-flash',
    daily_request_limit INTEGER NOT NULL DEFAULT 5 CHECK (daily_request_limit BETWEEN 1 AND 20),
    daily_token_limit INTEGER NOT NULL DEFAULT 50000 CHECK (daily_token_limit BETWEEN 5000 AND 200000),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_daily_usage (
    user_id BIGINT NOT NULL,
    usage_date DATE NOT NULL,
    runs INTEGER NOT NULL DEFAULT 0 CHECK (runs >= 0),
    tokens INTEGER NOT NULL DEFAULT 0 CHECK (tokens >= 0),
    reserved_tokens INTEGER NOT NULL DEFAULT 0 CHECK (reserved_tokens >= 0),
    PRIMARY KEY (user_id, usage_date)
);

CREATE TABLE IF NOT EXISTS ai_analyses (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    market VARCHAR(10) NOT NULL CHECK (market IN ('stock', 'upbit')),
    status VARCHAR(12) NOT NULL CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')),
    prompt TEXT NOT NULL,
    include_account BOOLEAN NOT NULL DEFAULT false,
    request_payload JSONB NOT NULL,
    settings_snapshot JSONB NOT NULL,
    model VARCHAR(80) NOT NULL,
    result JSONB,
    error_message TEXT,
    usage_tokens INTEGER NOT NULL DEFAULT 0,
    reserved_tokens INTEGER NOT NULL DEFAULT 0,
    usage_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    applied_candidate_id VARCHAR(40),
    applied_at TIMESTAMPTZ,
    applied_by BIGINT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_analysis_active_user
    ON ai_analyses(user_id) WHERE status IN ('PENDING', 'RUNNING');
CREATE INDEX IF NOT EXISTS idx_ai_analysis_owner_history ON ai_analyses(user_id, id DESC);

COMMIT;
