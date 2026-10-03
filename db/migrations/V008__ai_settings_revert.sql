BEGIN;
ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS reverted_at TIMESTAMPTZ;
ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS reverted_by BIGINT;
CREATE INDEX IF NOT EXISTS ai_auto_applied_market_idx ON ai_analyses(market, applied_at DESC)
    WHERE automation_run=true AND applied_at IS NOT NULL;
COMMIT;
