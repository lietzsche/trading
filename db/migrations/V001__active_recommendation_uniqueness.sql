BEGIN;

WITH duplicates AS (
    SELECT id,
           row_number() OVER (PARTITION BY code ORDER BY id) AS duplicate_number
    FROM upbit
    WHERE deleted_at IS NULL
)
UPDATE upbit
SET deleted_at = CURRENT_TIMESTAMP
WHERE id IN (SELECT id FROM duplicates WHERE duplicate_number > 1);

WITH duplicates AS (
    SELECT id,
           row_number() OVER (PARTITION BY code ORDER BY id) AS duplicate_number
    FROM stock
    WHERE deleted_at IS NULL
)
UPDATE stock
SET deleted_at = CURRENT_TIMESTAMP
WHERE id IN (SELECT id FROM duplicates WHERE duplicate_number > 1);

CREATE UNIQUE INDEX IF NOT EXISTS uq_upbit_active_code
    ON upbit (code)
    WHERE deleted_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_stock_active_code
    ON stock (code)
    WHERE deleted_at IS NULL;

COMMIT;
