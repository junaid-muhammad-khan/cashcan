-- Scores for the kids' sorting game (website /play). The API creates this table on first use; this file is the same statement
-- for anyone who prefers to run it by hand. Delta does not enforce keys: score_id (the browser's game id) is made unique by a MERGE.
CREATE TABLE IF NOT EXISTS workspace.cashcan_app.game_scores (
  score_id    STRING NOT NULL,
  user_id     STRING NOT NULL,
  score       INT NOT NULL,        -- worked out by the server: correct x 10 + best_streak x 5
  correct     INT NOT NULL,
  wrong       INT NOT NULL,
  spilled     INT NOT NULL,
  best_streak INT NOT NULL,
  level       INT NOT NULL,
  duration_ms BIGINT NOT NULL,
  created_at  TIMESTAMP NOT NULL
);
