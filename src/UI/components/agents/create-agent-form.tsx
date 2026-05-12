"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Save, Sparkles } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Agent, Voice } from "@/lib/types";
import { TOOL_LIBRARY } from "@/lib/mock-data";
import { ADMIN_USER } from "@/lib/auth";
import type { AgentStatus } from "@/lib/types";

const MODELS = [
  { id: "gemini-2.5-flash", label: "Gemini · 2.5 Flash" },
  { id: "gemini-2.0-flash", label: "Gemini · 2.0 Flash" },
  { id: "llama3.1", label: "Ollama · Llama 3.1" },
  { id: "qwen2.5", label: "Ollama · Qwen 2.5" },
];

function providerForModel(model: string, fallback = "gemini") {
  if (model.startsWith("llama") || model.startsWith("qwen")) return "ollama";
  if (model.startsWith("gemini") || model.startsWith("gemma")) return "gemini";
  return fallback;
}

interface Props {
  voices: Voice[];
  agent?: Agent;
}

export function CreateAgentForm({ voices, agent }: Props) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const isEditing = !!agent;
  const modelOptions = agent && !MODELS.some((m) => m.id === agent.model)
    ? [{ id: agent.model, label: `${agent.provider} · ${agent.model}` }, ...MODELS]
    : MODELS;
  const [tools, setTools] = useState<Record<string, boolean>>(
    () => Object.fromEntries((agent?.tools ?? []).map((tool) => [tool, true])),
  );
  const [temperature, setTemperature] = useState(agent?.temperature ?? 0.4);
  const [voiceId, setVoiceId] = useState(agent?.voiceId ?? voices[0]?.id ?? "");
  const [model, setModel] = useState(agent?.model ?? modelOptions[0].id);
  const [agentStatus, setAgentStatus] = useState<AgentStatus>(agent?.status ?? "active");

  async function handleSubmit(formData: FormData) {
    const submitStatus = String(formData.get("status") ?? "active") as AgentStatus;
    const status = isEditing ? agentStatus : submitStatus === "draft" ? "draft" : "active";
    const payload = {
      userId: ADMIN_USER.id,
      name: String(formData.get("name") ?? "").trim(),
      description: String(formData.get("description") ?? "").trim(),
      status,
      systemPrompt: String(formData.get("systemPrompt") ?? "").trim(),
      voiceId,
      provider: providerForModel(model, agent?.provider),
      model,
      temperature,
      tools: Object.entries(tools).filter(([, v]) => v).map(([k]) => k),
    };
    if (!payload.name) {
      toast.error("Name is required.");
      return;
    }

    const res = await fetch(isEditing ? `/api/agents/${encodeURIComponent(agent.id)}` : "/api/agents", {
      method: isEditing ? "PATCH" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      toast.error(isEditing ? "Could not update agent." : "Could not create agent.");
      return;
    }
    toast.success(isEditing ? "Agent updated." : payload.status === "draft" ? "Draft saved." : "Agent created.");
    router.push(isEditing ? `/agents/${agent.id}` : "/agents");
    router.refresh();
  }

  return (
    <form
      action={(fd) => startTransition(() => void handleSubmit(fd))}
      className="grid gap-6 lg:grid-cols-3"
    >
      <div className="space-y-6 lg:col-span-2">
        <Card>
          <CardHeader>
            <CardTitle>Basics</CardTitle>
            <CardDescription>Give your agent a clear name and a short description.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="name">Agent name</Label>
              <Input
                id="name"
                name="name"
                placeholder="e.g. Sales Concierge"
                defaultValue={agent?.name}
                required
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="description">Description</Label>
              <Input
                id="description"
                name="description"
                placeholder="Short summary shown in the dashboard"
                defaultValue={agent?.description}
              />
            </div>
            {isEditing ? (
              <div className="grid gap-2">
                <Label>Status</Label>
                <Select value={agentStatus} onValueChange={(v) => setAgentStatus(v as AgentStatus)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="draft">Draft</SelectItem>
                    <SelectItem value="archived">Archived</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Behavior</CardTitle>
            <CardDescription>System prompt, model, and creativity.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="systemPrompt">System prompt</Label>
              <Textarea
                id="systemPrompt"
                name="systemPrompt"
                rows={6}
                placeholder="You are a friendly support agent for…"
                defaultValue={agent?.systemPrompt}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label>Model</Label>
                <Select value={model} onValueChange={setModel}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {modelOptions.map((m) => (
                      <SelectItem key={m.id} value={m.id}>
                        {m.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <div className="flex items-center justify-between">
                  <Label>Temperature</Label>
                  <span className="font-mono text-xs text-[var(--muted-foreground)]">
                    {temperature.toFixed(2)}
                  </span>
                </div>
                <Slider
                  min={0}
                  max={1}
                  step={0.05}
                  value={[temperature]}
                  onValueChange={(v) => setTemperature(v[0] ?? 0)}
                  className="pt-2"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Tools</CardTitle>
            <CardDescription>Enable functions the agent can call during a conversation.</CardDescription>
          </CardHeader>
          <CardContent className="divide-y divide-[var(--border)]">
            {TOOL_LIBRARY.map((tool) => (
              <div key={tool.id} className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
                <div>
                  <div className="text-sm font-medium">{tool.label}</div>
                  <div className="text-xs text-[var(--muted-foreground)]">{tool.description}</div>
                </div>
                <Switch
                  checked={!!tools[tool.id]}
                  onCheckedChange={(v) => setTools((s) => ({ ...s, [tool.id]: v }))}
                />
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Voice</CardTitle>
            <CardDescription>Choose how your agent sounds.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            <Label>Voice</Label>
            <Select value={voiceId} onValueChange={setVoiceId}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectLabel>Available voices</SelectLabel>
                  {voices.map((v) => (
                    <SelectItem key={v.id} value={v.id}>
                      {v.name} · {v.provider}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
            <p className="text-xs text-[var(--muted-foreground)]">
              Manage the voice library from{" "}
              <a className="underline" href="/voice-settings">
                Voice Settings
              </a>
              .
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center gap-2">
            <Sparkles className="size-4 text-[var(--muted-foreground)]" />
            <CardTitle className="text-sm">Tip</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-[var(--muted-foreground)]">
              Keep system prompts under 1000 tokens for faster first-response latency.
            </p>
          </CardContent>
        </Card>

        <div className="flex items-center justify-end gap-2">
          {isEditing ? null : (
            <Button type="submit" name="status" value="draft" variant="outline" disabled={pending}>
              {pending ? "Saving…" : "Save draft"}
            </Button>
          )}
          <Button type="submit" name="status" value="active" disabled={pending}>
            <Save />
            {pending ? (isEditing ? "Saving…" : "Creating…") : isEditing ? "Save changes" : "Create agent"}
          </Button>
        </div>
      </div>
    </form>
  );
}
