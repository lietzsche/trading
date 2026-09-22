BEGIN;

CREATE TABLE IF NOT EXISTS portfolio_daily_snapshot (
    user_id BIGINT NOT NULL,
    snapshot_date DATE NOT NULL,
    total_valuation DOUBLE PRECISION NOT NULL,
    purchase_amount DOUBLE PRECISION,
    unrealized_profit DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_snapshot_user_date
    ON portfolio_daily_snapshot(user_id, snapshot_date DESC);

COMMIT;
