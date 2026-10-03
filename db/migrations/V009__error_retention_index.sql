-- Retention only affects trade_error_log at runtime; this migration deletes no records.
CREATE INDEX IF NOT EXISTS idx_trade_error_created_at ON trade_error_log(created_at);
