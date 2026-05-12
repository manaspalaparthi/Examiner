import { RoomAgentDispatch, RoomConfiguration } from "@livekit/protocol";
import { AccessToken } from "livekit-server-sdk";
import { NextResponse } from "next/server";
import { voiceApiUrl } from "@/lib/voice-api";
import type { Agent } from "@/lib/types";

export async function POST(req: Request) {
  const body = await req.json().catch(() => null);
  const agentId = cleanString(body?.agentId);
  if (!agentId) {
    return NextResponse.json({ error: "agentId is required" }, { status: 400 });
  }

  const apiKey = process.env.LIVEKIT_API_KEY;
  const apiSecret = process.env.LIVEKIT_API_SECRET;
  const serverUrl = process.env.LIVEKIT_URL || process.env.NEXT_PUBLIC_LIVEKIT_URL;
  if (!apiKey || !apiSecret || !serverUrl) {
    return NextResponse.json(
      { error: "LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET are required" },
      { status: 500 },
    );
  }

  const agent = await loadAgent(agentId).catch(() => null);
  if (!agent) {
    return NextResponse.json({ error: "Agent not found" }, { status: 404 });
  }

  const roomName = cleanString(body?.roomName) || makeRoomName(agent.id);
  const participantName = cleanString(body?.participantName) || makeParticipantName(agent.userId);
  const livekitConfig = agent.voiceConfig?.livekit as { agent_name?: string; agentName?: string } | undefined;
  const agentName =
    cleanString(body?.livekitAgentName) ||
    cleanString(livekitConfig?.agent_name) ||
    cleanString(livekitConfig?.agentName) ||
    process.env.LIVEKIT_AGENT_NAME ||
    "examiner-agent";

  const metadata = {
    agent_id: agent.id,
    user_id: agent.userId,
    conversation_id: cleanString(body?.conversationId),
    thinking_enabled: typeof body?.thinkingEnabled === "boolean" ? body.thinkingEnabled : undefined,
    config_path: agent.configPath,
    voice: agent.voiceConfig ?? {},
  };

  const token = new AccessToken(apiKey, apiSecret, {
    identity: participantName,
    name: participantName,
    ttl: "10m",
  });
  token.addGrant({
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canSubscribe: true,
    canPublishData: true,
  });
  token.roomConfig = new RoomConfiguration({
    agents: [
      new RoomAgentDispatch({
        agentName,
        metadata: JSON.stringify(metadata),
      }),
    ],
  });

  return NextResponse.json({
    token: await token.toJwt(),
    serverUrl,
    roomName,
    participantName,
    agentName,
  });
}

async function loadAgent(agentId: string): Promise<Agent | null> {
  const res = await fetch(voiceApiUrl(`/api/agents/${encodeURIComponent(agentId)}`), {
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Could not load agent: ${res.status}`);
  return res.json();
}

function cleanString(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function makeRoomName(agentId: string) {
  return `examiner-${slug(agentId)}-${crypto.randomUUID().slice(0, 8)}`;
}

function makeParticipantName(userId: string) {
  return `user-${slug(userId)}-${crypto.randomUUID().slice(0, 8)}`;
}

function slug(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "") || "agent";
}
