-- Fernet tokens are longer than the original API keys; preserve all existing values.
ALTER TABLE tb_upbit_key ALTER COLUMN access_key TYPE TEXT;
ALTER TABLE tb_upbit_key ALTER COLUMN secret_key TYPE TEXT;
