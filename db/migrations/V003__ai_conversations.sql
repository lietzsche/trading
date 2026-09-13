BEGIN;

CREATE TABLE IF NOT EXISTS ai_conversation_messages (
    id BIGSERIAL PRIMARY KEY,
    analysis_id BIGINT NOT NULL REFERENCES ai_analyses(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    status VARCHAR(12) NOT NULL CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')),
    question TEXT NOT NULL,
    answer TEXT,
    research JSONB,
    error_message TEXT,
    usage_tokens INTEGER NOT NULL DEFAULT 0,
    reserved_tokens INTEGER NOT NULL DEFAULT 0,
    usage_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_conversation_active_user
    ON ai_conversation_messages(user_id) WHERE status IN ('PENDING', 'RUNNING');
CREATE INDEX IF NOT EXISTS idx_ai_conversation_thread
    ON ai_conversation_messages(analysis_id, id);

COMMIT;
