ALTER TABLE trade_error_log ADD COLUMN IF NOT EXISTS repeat_count INTEGER NOT NULL DEFAULT 1;
ALTER TABLE trade_error_log ADD COLUMN IF NOT EXISTS last_seen_at VARCHAR(255);
CREATE INDEX IF NOT EXISTS idx_trade_error_last_seen
 ON trade_error_log ((COALESCE(last_seen_at, created_at)));
CREATE INDEX IF NOT EXISTS idx_trade_error_group_recent
 ON trade_error_log (source,operation,error_type,(COALESCE(last_seen_at,created_at)) DESC);
