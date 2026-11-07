CREATE SEQUENCE IF NOT EXISTS upbit_seq;
CREATE SEQUENCE IF NOT EXISTS upbit_history_label_seq;
CREATE SEQUENCE IF NOT EXISTS upbit_order_history_seq;
CREATE SEQUENCE IF NOT EXISTS trade_error_log_seq;
CREATE SEQUENCE IF NOT EXISTS tb_user_seq;
CREATE SEQUENCE IF NOT EXISTS tb_upbit_key_seq;

CREATE TABLE IF NOT EXISTS tb_user (
 id BIGINT PRIMARY KEY DEFAULT nextval('tb_user_seq'),user_login_id VARCHAR(50) UNIQUE NOT NULL,user_password TEXT NOT NULL,
 user_name VARCHAR(100) NOT NULL,user_role VARCHAR(20) NOT NULL DEFAULT 'USER',user_email VARCHAR(255),
 user_phone VARCHAR(50),created_at VARCHAR(255),updated_at VARCHAR(255),deleted_at VARCHAR(255)
);
CREATE TABLE IF NOT EXISTS tb_upbit_key (
 id BIGINT PRIMARY KEY DEFAULT nextval('tb_upbit_key_seq'),user_login_id VARCHAR(50) UNIQUE NOT NULL,access_key TEXT NOT NULL,
 secret_key TEXT NOT NULL,auto_on BOOLEAN NOT NULL DEFAULT FALSE,created_at VARCHAR(255),updated_at VARCHAR(255)
);
CREATE TABLE IF NOT EXISTS deal_settings (
 id BIGSERIAL PRIMARY KEY,name VARCHAR(20) UNIQUE NOT NULL,expected_high_percentage INTEGER NOT NULL DEFAULT 1,
 expected_low_percentage INTEGER NOT NULL DEFAULT -1,highest_price_reference_days INTEGER NOT NULL DEFAULT 41,
 is_volume_check BOOLEAN NOT NULL DEFAULT FALSE,created_at VARCHAR(255),updated_at VARCHAR(255),deleted_at VARCHAR(255)
);
INSERT INTO deal_settings(name,highest_price_reference_days) VALUES('upbit',41) ON CONFLICT(name) DO NOTHING;
CREATE TABLE IF NOT EXISTS upbit_history_label (
 id BIGINT PRIMARY KEY DEFAULT nextval('upbit_history_label_seq'),code VARCHAR(100) NOT NULL,name VARCHAR(255),
 created_at VARCHAR(255),updated_at VARCHAR(255),deleted_at VARCHAR(255)
);
CREATE TABLE IF NOT EXISTS upbit (
 id BIGINT PRIMARY KEY DEFAULT nextval('upbit_seq'),code VARCHAR(100) NOT NULL,name VARCHAR(255),
 origin_minimum_selling_price DOUBLE PRECISION,origin_expected_selling_price DOUBLE PRECISION,
 minimum_selling_price DOUBLE PRECISION,expected_selling_price DOUBLE PRECISION,temp_price DOUBLE PRECISION,
 setting_price DOUBLE PRECISION,pricing_reference_date VARCHAR(255),renewal_cnt INTEGER NOT NULL DEFAULT 0,
 created_at VARCHAR(255),updated_at VARCHAR(255),deleted_at VARCHAR(255)
);
-- Retained only so the historical uniqueness migration is safe on a fresh DB.
CREATE TABLE IF NOT EXISTS stock(id BIGSERIAL PRIMARY KEY,code VARCHAR(100),deleted_at VARCHAR(255));
CREATE TABLE IF NOT EXISTS upbit_order_history (
 id BIGINT PRIMARY KEY DEFAULT nextval('upbit_order_history_seq'),login_id VARCHAR(50),uuid VARCHAR(255),
 identifier VARCHAR(255),side VARCHAR(20),ord_type VARCHAR(30),price VARCHAR(100),state VARCHAR(30),market VARCHAR(100),
 created_at VARCHAR(255),updated_at VARCHAR(255),deleted_at VARCHAR(255),volume VARCHAR(100),remaining_volume VARCHAR(100),
 reserved_fee VARCHAR(100),remaining_fee VARCHAR(100),paid_fee VARCHAR(100),locked VARCHAR(100),executed_volume VARCHAR(100),
 trades_count INTEGER
);
CREATE TABLE IF NOT EXISTS trade_error_log (
 id BIGINT PRIMARY KEY DEFAULT nextval('trade_error_log_seq'),source VARCHAR(20),operation VARCHAR(100),
 error_type VARCHAR(255),message TEXT,created_at VARCHAR(255)
);
