-- Add candle_interval column to upbit_strategy_settings for configurable candle timeframes (30m, 60m, 240m, days, weeks)
ALTER TABLE upbit_strategy_settings
    ADD COLUMN IF NOT EXISTS candle_interval VARCHAR(16) NOT NULL DEFAULT 'days';
