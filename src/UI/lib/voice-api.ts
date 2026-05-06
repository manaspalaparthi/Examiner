import type { Agent } from "@/lib/types";

const DEFAULT_VOICE_API_BASE_URL = "http://127.0.0.1:8000";

export function voiceApiUrl(path: string) {
  const base =
    process.env.VOICE_API_BASE_URL ||
    process.env.NEXT_PUBLIC_VOICE_API_BASE_URL ||
    DEFAULT_VOICE_API_BASE_URL;
  return `${base.replace(/\/$/, "")}${path.startsWith("/") ? path : `/${path}`}`;
}

export function voiceWsUrl(path: string) {
  const base =
    process.env.NEXT_PUBLIC_VOICE_API_WS_URL ||
    process.env.NEXT_PUBLIC_VOICE_API_BASE_URL ||
    DEFAULT_VOICE_API_BASE_URL;
  const withProtocol = base.replace(/^http:/, "ws:").replace(/^https:/, "wss:");
  return `${withProtocol.replace(/\/$/, "")}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function listAgents(): Promise<Agent[]> {
  const res = await fetch(voiceApiUrl("/api/agents"), { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Could not load agents: ${res.status}`);
  }
  return res.json();
}

export async function getAgent(id: string): Promise<Agent | null> {
  const res = await fetch(voiceApiUrl(`/api/agents/${encodeURIComponent(id)}`), {
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`Could not load agent ${id}: ${res.status}`);
  }
  return res.json();
}
