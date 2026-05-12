export type AgentStatus = "active" | "draft" | "archived";

export interface Agent {
  id: string;
  userId: string;
  name: string;
  description: string;
  status: AgentStatus;
  backendAgent: string;
  configPath?: string | null;
  voiceId: string;
  provider: string;
  model: string;
  systemPrompt: string;
  temperature: number;
  maxTokens?: number | null;
  thinkingEnabled?: boolean;
  historyLimit?: number;
  tools: string[];
  toolGroups?: string[];
  ack?: Record<string, unknown>;
  mcpServers?: Record<string, unknown>[];
  timeouts?: Record<string, unknown>;
  tracing?: Record<string, unknown>;
  voiceConfig?: {
    transport?: "legacy_ws" | "livekit";
    livekit?: {
      agent_name?: string;
      agentName?: string;
      url?: string;
      [key: string]: unknown;
    };
    stt?: {
      provider?: string;
      model?: string;
      model_id?: string;
      modelId?: string;
      language?: string;
      [key: string]: unknown;
    };
    llm?: {
      provider?: string;
      model?: string;
      [key: string]: unknown;
    };
    tts?: {
      provider?: string;
      model?: string;
      voice?: string;
      speed?: number;
      lang?: string;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
  agentConfig?: Record<string, unknown>;
  startParams?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface Voice {
  id: string;
  name: string;
  provider: "elevenlabs" | "openai" | "deepgram" | "playht" | "kokoro";
  gender: "male" | "female" | "neutral";
  accent?: string;
  sampleUrl?: string;
}

export interface Message {
  id: string;
  role: "user" | "agent" | "system";
  content: string;
  timestamp: string;
}

export interface Conversation {
  id: string;
  agentId: string;
  agentName: string;
  callerNumber?: string;
  startedAt: string;
  durationSec: number;
  status: "completed" | "failed" | "in-progress";
  messages: Message[];
}

export interface Integration {
  id: string;
  name: string;
  description: string;
  category: "telephony" | "crm" | "messaging" | "automation" | "analytics";
  connected: boolean;
  iconKey: string;
}

export interface AnalyticsSummary {
  activeAgents: number;
  callsToday: number;
  avgDurationSec: number;
  successRate: number;
  callsLast7Days: { date: string; count: number }[];
  topAgents: { agentId: string; name: string; calls: number }[];
}

export interface CreateAgentInput {
  name: string;
  userId?: string;
  description: string;
  status?: AgentStatus;
  voiceId: string;
  provider?: string;
  model: string;
  systemPrompt: string;
  temperature: number;
  tools?: string[];
}
