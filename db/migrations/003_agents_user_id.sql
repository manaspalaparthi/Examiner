ALTER TABLE agents
  ADD COLUMN IF NOT EXISTS user_id TEXT NOT NULL DEFAULT 'admin';

CREATE INDEX IF NOT EXISTS agents_user_updated_idx
  ON agents (user_id, updated_at DESC);
