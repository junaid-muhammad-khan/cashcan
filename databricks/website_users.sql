-- Website accounts. Run once in a SQL warehouse (or: databricks experimental aitools tools query "<each statement>").
CREATE SCHEMA IF NOT EXISTS workspace.cashcan_web;
CREATE TABLE IF NOT EXISTS workspace.cashcan_web.users (
  id               STRING NOT NULL,
  name             STRING NOT NULL,
  email            STRING NOT NULL,   -- stored lower-case; uniqueness is enforced in the insert statement
  password_hash    STRING NOT NULL,   -- scrypt hash, never the password
  wallet_address   STRING,
  face_opt_in      BOOLEAN NOT NULL,
  created_at       TIMESTAMP NOT NULL,
  reset_token_hash STRING,            -- SHA-256 of the reset token only
  reset_expires    BIGINT             -- epoch milliseconds
);
