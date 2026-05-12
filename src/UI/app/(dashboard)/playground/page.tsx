"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ChatPanel, type ChatPanelHandle } from "@/components/playground/chat-panel";
import { LiveKitVoiceControls } from "@/components/playground/livekit-voice-controls";
import { VoiceControls } from "@/components/playground/voice-controls";
import type { Agent } from "@/lib/types";

export default function PlaygroundPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agentId, setAgentId] = useState("");
  const [thinkingEnabled, setThinkingEnabled] = useState(true);
  const [loadingAgents, setLoadingAgents] = useState(true);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const chatRef = useRef<ChatPanelHandle>(null);

  const testable = useMemo(() => agents.filter((a) => a.status !== "archived"), [agents]);
  const agent = testable.find((a) => a.id === agentId) ?? testable[0];

  useEffect(() => {
    let alive = true;

    async function loadAgents() {
      try {
        setLoadingAgents(true);
        setAgentError(null);
        const res = await fetch("/api/agents", { cache: "no-store" });
        if (!res.ok) {
          throw new Error(`Could not load agents (${res.status})`);
        }
        const rows = (await res.json()) as Agent[];
        if (!alive) return;
        const visible = rows.filter((a) => a.status !== "archived");
        setAgents(rows);
        setAgentId((current) => current || visible[0]?.id || "");
        setThinkingEnabled((current) =>
          typeof visible[0]?.thinkingEnabled === "boolean"
            ? visible[0].thinkingEnabled
            : typeof visible[0]?.agentConfig?.thinking_enabled === "boolean"
              ? visible[0].agentConfig.thinking_enabled
              : current,
        );
      } catch (error) {
        if (!alive) return;
        setAgentError(error instanceof Error ? error.message : "Could not load agents");
      } finally {
        if (alive) setLoadingAgents(false);
      }
    }

    loadAgents();
    return () => {
      alive = false;
    };
  }, []);

  return (
    <>
      <PageHeader
        title="Playground"
        description="Try out your agents in chat or simulated voice mode before going live."
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_2fr]">
        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Agent</CardTitle>
            </CardHeader>
            <CardContent>
              <Select
                value={agentId}
                onValueChange={(nextAgentId) => {
                  setAgentId(nextAgentId);
                  setConversationId(null);
                  const nextAgent = testable.find((a) => a.id === nextAgentId);
                  setThinkingEnabled(agentThinkingEnabled(nextAgent));
                }}
                disabled={loadingAgents || testable.length === 0}
              >
                <SelectTrigger>
                  <SelectValue placeholder={loadingAgents ? "Loading agents..." : "Select an agent"} />
                </SelectTrigger>
                <SelectContent>
                  {testable.map((a) => (
                    <SelectItem key={a.id} value={a.id}>
                      {a.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {agentError && <p className="mt-3 text-xs text-[var(--destructive)]">{agentError}</p>}
              {!agentError && !loadingAgents && testable.length === 0 && (
                <p className="mt-3 text-xs text-[var(--muted-foreground)]">Create an active agent to test it here.</p>
              )}
              {agent && <p className="mt-3 text-xs text-[var(--muted-foreground)]">{agent.description}</p>}
              {agent && (
                <div className="mt-4 flex items-center justify-between gap-4 rounded-lg border border-[var(--border)] px-3 py-2.5">
                  <Label htmlFor="thinking-toggle" className="text-sm">
                    Thinking
                  </Label>
                  <Switch
                    id="thinking-toggle"
                    checked={thinkingEnabled}
                    onCheckedChange={setThinkingEnabled}
                  />
                </div>
              )}
            </CardContent>
          </Card>
          {voiceTransport(agent) === "livekit" ? (
            <LiveKitVoiceControls
              agent={agent}
              thinkingEnabled={thinkingEnabled}
              conversationId={conversationId}
              onConversationIdChange={(nextConversationId) => {
                setConversationId(nextConversationId);
                chatRef.current?.finishVoiceAgentTurn();
              }}
              onUserTranscript={(text) => chatRef.current?.appendVoiceUserText(text)}
              onAgentText={(text) => chatRef.current?.appendVoiceAgentText(text)}
            />
          ) : (
            <VoiceControls
              agent={agent}
              thinkingEnabled={thinkingEnabled}
              conversationId={conversationId}
              onConversationIdChange={(nextConversationId) => {
                setConversationId(nextConversationId);
                chatRef.current?.finishVoiceAgentTurn();
              }}
              onUserTranscript={(text) => chatRef.current?.appendVoiceUserText(text)}
              onAgentText={(text) => chatRef.current?.appendVoiceAgentText(text)}
            />
          )}
        </div>
        <ChatPanel
          key={agent?.id ?? "no-agent"}
          ref={chatRef}
          agent={agent}
          thinkingEnabled={thinkingEnabled}
          conversationId={conversationId}
          onConversationIdChange={setConversationId}
        />
      </div>
    </>
  );
}

function agentThinkingEnabled(agent?: Agent) {
  if (typeof agent?.thinkingEnabled === "boolean") return agent.thinkingEnabled;
  if (typeof agent?.agentConfig?.thinking_enabled === "boolean") return agent.agentConfig.thinking_enabled as boolean;
  return true;
}

function voiceTransport(agent?: Agent) {
  const transport = agent?.voiceConfig?.transport;
  return transport === "livekit" ? "livekit" : "legacy_ws";
}
