"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { Bot, ChevronDown, ChevronRight, Send, User, Wrench } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Agent } from "@/lib/types";

type ChatBlock =
  | { id: string; type: "text"; text: string }
  | { id: string; type: "thinking"; text: string; open: boolean }
  | {
      id: string;
      type: "tool";
      callId: string;
      name: string;
      args: unknown;
      result: string;
      open: boolean;
      ok?: boolean;
      latencyMs?: number;
      status: "running" | "done";
    };

interface Msg {
  id: string;
  role: "user" | "agent";
  blocks: ChatBlock[];
}

type StreamEvent =
  | { type: "text_delta"; text: string }
  | { type: "thinking_delta"; text: string }
  | { type: "tool_start"; callId: string; name: string; args?: unknown }
  | { type: "tool_end"; callId: string; name: string; ok: boolean; latencyMs: number; summary?: string | null; error?: string | null }
  | { type: "error"; message: string }
  | { type: "done"; conversationId?: string | null };

export interface ChatPanelHandle {
  appendVoiceUserText: (text: string) => void;
  appendVoiceAgentText: (text: string) => void;
  finishVoiceAgentTurn: () => void;
}

interface ChatPanelProps {
  agent?: Agent;
  thinkingEnabled: boolean;
  conversationId: string | null;
  onConversationIdChange: (conversationId: string | null) => void;
}

export const ChatPanel = forwardRef<ChatPanelHandle, ChatPanelProps>(function ChatPanel(
  { agent, thinkingEnabled, conversationId, onConversationIdChange },
  ref,
) {
  const [messages, setMessages] = useState<Msg[]>(() => initialMessages(agent));
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const activeVoiceAgentMessageRef = useRef<string | null>(null);
  const agentName = agent?.name ?? "Agent";

  function appendTextBlock(messageId: string, text: string) {
    setMessages((current) => updateMessage(current, messageId, (blocks) => [
      ...blocks,
      { id: newId("text"), type: "text", text },
    ]));
  }

  useImperativeHandle(ref, () => ({
    appendVoiceUserText(text: string) {
      const cleanText = text.trim();
      if (!cleanText) return;
      activeVoiceAgentMessageRef.current = null;
      const id = newId("voice-user");
      setMessages((current) => [
        ...current,
        { id, role: "user", blocks: [{ id: `${id}-text`, type: "text", text: cleanText }] },
      ]);
    },
    appendVoiceAgentText(text: string) {
      const cleanText = text.trim();
      if (!cleanText) return;
      const currentId = activeVoiceAgentMessageRef.current;
      if (currentId) {
        appendTextBlock(currentId, cleanText);
        return;
      }

      const id = newId("voice-agent");
      activeVoiceAgentMessageRef.current = id;
      setMessages((current) => [
        ...current,
        { id, role: "agent", blocks: [{ id: `${id}-text`, type: "text", text: cleanText }] },
      ]);
    },
    finishVoiceAgentTurn() {
      activeVoiceAgentMessageRef.current = null;
    },
  }), []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, running]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || !agent || running) return;

    activeVoiceAgentMessageRef.current = null;
    const userId = newId("user");
    const replyId = newId("agent");
    setMessages((current) => [
      ...current,
      { id: userId, role: "user", blocks: [{ id: `${userId}-text`, type: "text", text }] },
      { id: replyId, role: "agent", blocks: [] },
    ]);
    setInput("");
    setRunning(true);

    try {
      const res = await fetch(`/api/agents/${encodeURIComponent(agent.id)}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
        body: JSON.stringify({
          message: text,
          conversationId,
          userId: agent.userId,
          thinkingEnabled,
        }),
      });

      if (!res.ok) {
        throw new Error(await readError(res));
      }
      if (!res.body) {
        throw new Error("Runtime chat stream was empty");
      }

      await readStream(res.body, (event) => handleStreamEvent(replyId, event));
      ensureReplyHasContent(replyId);
    } catch (error) {
      appendText(replyId, error instanceof Error ? error.message : "Runtime chat failed");
    } finally {
      setRunning(false);
    }
  }

  function handleStreamEvent(messageId: string, event: StreamEvent) {
    if (event.type === "text_delta") {
      appendText(messageId, event.text);
    } else if (event.type === "thinking_delta") {
      appendThinking(messageId, event.text);
    } else if (event.type === "tool_start") {
      appendTool(messageId, event);
    } else if (event.type === "tool_end") {
      completeTool(messageId, event);
    } else if (event.type === "error") {
      appendText(messageId, `I hit an error: ${event.message}`);
    } else if (event.type === "done") {
      onConversationIdChange(event.conversationId ?? null);
    }
  }

  function appendText(messageId: string, text: string) {
    setMessages((current) => updateMessage(current, messageId, (blocks) => {
      const last = blocks.at(-1);
      if (last?.type === "text") {
        return [...blocks.slice(0, -1), { ...last, text: last.text + text }];
      }
      return [...blocks, { id: newId("text"), type: "text", text }];
    }));
  }

  function appendThinking(messageId: string, text: string) {
    setMessages((current) => updateMessage(current, messageId, (blocks) => {
      const last = blocks.at(-1);
      if (last?.type === "thinking") {
        return [...blocks.slice(0, -1), { ...last, text: last.text + text }];
      }
      return [...blocks, { id: newId("thinking"), type: "thinking", text, open: false }];
    }));
  }

  function appendTool(messageId: string, event: Extract<StreamEvent, { type: "tool_start" }>) {
    setMessages((current) => updateMessage(current, messageId, (blocks) => [
      ...blocks,
      {
        id: newId("tool"),
        type: "tool",
        callId: event.callId,
        name: event.name,
        args: event.args ?? {},
        result: "",
        open: false,
        status: "running",
      },
    ]));
  }

  function completeTool(messageId: string, event: Extract<StreamEvent, { type: "tool_end" }>) {
    setMessages((current) => updateMessage(current, messageId, (blocks) =>
      blocks.map((block) =>
        block.type === "tool" && block.callId === event.callId
          ? {
              ...block,
              status: "done",
              ok: event.ok,
              latencyMs: event.latencyMs,
              result: event.error || event.summary || "",
            }
          : block,
      ),
    ));
  }

  function toggleBlock(messageId: string, blockId: string) {
    setMessages((current) => updateMessage(current, messageId, (blocks) =>
      blocks.map((block) =>
        block.id === blockId && (block.type === "thinking" || block.type === "tool")
          ? { ...block, open: !block.open }
          : block,
      ),
    ));
  }

  function ensureReplyHasContent(messageId: string) {
    setMessages((current) => updateMessage(current, messageId, (blocks) =>
      blocks.length ? blocks : [{ id: newId("text"), type: "text", text: "The runtime returned an empty response." }],
    ));
  }

  return (
    <Card className="flex h-[640px] min-h-[420px] flex-col overflow-hidden">
      <CardHeader className="border-b border-[var(--border)] py-3">
        <CardTitle className="text-sm">Conversation with {agentName}</CardTitle>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col gap-0 p-0">
        <div ref={scrollRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
          {messages.map((m) => (
            <div key={m.id} className={cn("flex items-start gap-3", m.role === "user" && "flex-row-reverse")}>
              <div
                className={cn(
                  "flex size-7 shrink-0 items-center justify-center rounded-full",
                  m.role === "agent"
                    ? "bg-[var(--muted)] text-[var(--muted-foreground)]"
                    : "bg-[var(--primary)] text-[var(--primary-foreground)]",
                )}
              >
                {m.role === "agent" ? <Bot className="size-4" /> : <User className="size-4" />}
              </div>
              <div
                className={cn(
                  "max-w-[80%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed",
                  m.role === "agent"
                    ? "bg-[var(--muted)] text-[var(--foreground)]"
                    : "bg-[var(--primary)] text-[var(--primary-foreground)]",
                )}
              >
                {m.blocks.length ? (
                  <div className="space-y-2">
                    {m.blocks.map((block) => (
                      <MessageBlock
                        key={block.id}
                        block={block}
                        onToggle={() => toggleBlock(m.id, block.id)}
                      />
                    ))}
                  </div>
                ) : (
                  <TypingDots />
                )}
              </div>
            </div>
          ))}
        </div>

        <form onSubmit={send} className="flex items-center gap-2 border-t border-[var(--border)] p-3">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={agent ? "Type a message..." : "Select an agent first"}
            className="h-10"
            disabled={!agent || running}
          />
          <Button type="submit" size="icon" disabled={!agent || !input.trim() || running} className="h-10 w-10">
            <Send />
          </Button>
        </form>
      </CardContent>
    </Card>
  );
});

function MessageBlock({ block, onToggle }: { block: ChatBlock; onToggle: () => void }) {
  if (block.type === "text") {
    return <div className="whitespace-pre-wrap break-words">{block.text}</div>;
  }

  const isTool = block.type === "tool";
  const label = isTool ? `Tool call: ${block.name}` : "Proposed plan";
  const detail = isTool ? formatToolDetail(block) : block.text;

  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        className="inline-flex max-w-full items-center gap-1 text-left text-xs font-medium text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
      >
        {block.open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        {isTool && <Wrench className="size-3.5" />}
        <span className="truncate">{label}</span>
        {isTool && block.status === "running" && <span className="shrink-0">running</span>}
        {isTool && block.status === "done" && typeof block.latencyMs === "number" && (
          <span className="shrink-0">{block.latencyMs}ms</span>
        )}
      </button>
      {block.open && (
        <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-md border border-[var(--border)] bg-[var(--background)]/70 p-3 font-mono text-xs leading-relaxed text-[var(--foreground)]">
          {detail || "No details returned."}
        </pre>
      )}
    </div>
  );
}

function TypingDots() {
  return (
    <span className="inline-flex gap-1 py-1">
      <span className="size-1.5 animate-bounce rounded-full bg-[var(--muted-foreground)]" />
      <span className="size-1.5 animate-bounce rounded-full bg-[var(--muted-foreground)] [animation-delay:120ms]" />
      <span className="size-1.5 animate-bounce rounded-full bg-[var(--muted-foreground)] [animation-delay:240ms]" />
    </span>
  );
}

function updateMessage(messages: Msg[], messageId: string, update: (blocks: ChatBlock[]) => ChatBlock[]) {
  return messages.map((message) =>
    message.id === messageId ? { ...message, blocks: update(message.blocks) } : message,
  );
}

function initialMessages(agent?: Agent): Msg[] {
  if (!agent) return [];
  return [
    {
      id: "ready",
      role: "agent",
      blocks: [
        {
          id: "ready-text",
          type: "text",
          text: `${agent.name} is connected to the runtime. Send a message to start testing.`,
        },
      ],
    },
  ];
}

async function readStream(body: ReadableStream<Uint8Array>, onEvent: (event: StreamEvent) => void) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.trim()) continue;
      onEvent(JSON.parse(line) as StreamEvent);
    }
  }

  buffer += decoder.decode();
  if (buffer.trim()) {
    onEvent(JSON.parse(buffer) as StreamEvent);
  }
}

async function readError(res: Response) {
  const body = await res.text();
  try {
    const parsed = JSON.parse(body) as { detail?: string; error?: string };
    return parsed.detail ?? parsed.error ?? "Runtime chat failed";
  } catch {
    return body || "Runtime chat failed";
  }
}

function formatToolDetail(block: Extract<ChatBlock, { type: "tool" }>) {
  const args = `Arguments\n${formatValue(block.args)}`;
  const result = block.result ? `\n\nResult\n${block.result}` : "";
  return `${args}${result}`;
}

function formatValue(value: unknown) {
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function newId(prefix: string) {
  return `${prefix}-${globalThis.crypto?.randomUUID?.() ?? Date.now().toString(36)}`;
}
