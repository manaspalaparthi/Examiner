CREATE EXTENSION IF NOT EXISTS pgcrypto;

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
