CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE agents (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL DEFAULT 'admin',
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('active', 'draft', 'archived')),
  backend_agent TEXT NOT NULL DEFAULT 'runtime',
  config_path TEXT,
  voice_id TEXT NOT NULL DEFAULT 'af_heart',
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  system_prompt TEXT NOT NULL DEFAULT '',
  temperature DOUBLE PRECISION NOT NULL DEFAULT 0.3,
  max_tokens INT,
  history_limit INT NOT NULL DEFAULT 30,
  tools TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  tool_groups TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  ack JSONB NOT NULL DEFAULT '{}',
  mcp_servers JSONB NOT NULL DEFAULT '[]',
  timeouts JSONB NOT NULL DEFAULT '{}',
  tracing JSONB NOT NULL DEFAULT '{}',
  voice_config JSONB NOT NULL DEFAULT '{}',
  agent_config JSONB NOT NULL DEFAULT '{}',
  start_params JSONB NOT NULL DEFAULT '{}',
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX agents_status_updated_idx
  ON agents (status, updated_at DESC);

CREATE INDEX agents_user_updated_idx
  ON agents (user_id, updated_at DESC);

CREATE INDEX agents_backend_idx
  ON agents (backend_agent);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER agents_set_updated_at
BEFORE UPDATE ON agents
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TABLE conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id TEXT NOT NULL,
  user_id TEXT,
  system_prompt TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  parent_id UUID REFERENCES messages(id),
  role TEXT NOT NULL,
  kind TEXT NOT NULL,
  content TEXT,
  content_json JSONB,
  tool_name TEXT,
  tool_call_id TEXT,
  latency_ms INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX messages_conversation_created_idx
  ON messages (conversation_id, created_at);

CREATE TABLE traces (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  message_id UUID REFERENCES messages(id),
  event TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ended_at TIMESTAMPTZ,
  latency_ms INT,
  metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX traces_conversation_started_idx
  ON traces (conversation_id, started_at);
