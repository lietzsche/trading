BEGIN;

ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS hidden_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_ai_analysis_visible_history
    ON ai_analyses(user_id, id DESC) WHERE hidden_at IS NULL;

COMMIT;
