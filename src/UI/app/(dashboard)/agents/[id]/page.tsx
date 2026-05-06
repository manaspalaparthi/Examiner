import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Sparkles, Mic2, Wrench, FileText, BarChart3 } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { AgentStatusBadge } from "@/components/shared/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { voices } from "@/lib/mock-data";
import { formatRelativeTime } from "@/lib/utils";
import { getAgent } from "@/lib/voice-api";

interface Props {
  params: Promise<{ id: string }>;
}

export default async function AgentDetailPage({ params }: Props) {
  const { id } = await params;
  const agent = await getAgent(id).catch(() => null);
  if (!agent) notFound();
  const voice = voices.find((v) => v.id === agent.voiceId);

  return (
    <>
      <Button asChild variant="ghost" size="sm" className="mb-4 -ml-2 text-[var(--muted-foreground)]">
        <Link href="/agents">
          <ArrowLeft /> Back to agents
        </Link>
      </Button>

      <PageHeader
        title={agent.name}
        description={agent.description}
        actions={
          <>
            <AgentStatusBadge status={agent.status} />
            <Button variant="outline" asChild>
              <Link href="/playground">Test in playground</Link>
            </Button>
            <Button asChild>
              <Link href={`/agents/${agent.id}/edit`}>Edit agent</Link>
            </Button>
          </>
        }
      />

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">
            <Sparkles className="mr-1.5 size-3.5" /> Overview
          </TabsTrigger>
          <TabsTrigger value="prompt">
            <FileText className="mr-1.5 size-3.5" /> Prompt
          </TabsTrigger>
          <TabsTrigger value="voice">
            <Mic2 className="mr-1.5 size-3.5" /> Voice
          </TabsTrigger>
          <TabsTrigger value="tools">
            <Wrench className="mr-1.5 size-3.5" /> Tools
          </TabsTrigger>
          <TabsTrigger value="logs">
            <BarChart3 className="mr-1.5 size-3.5" /> Logs
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="grid gap-4 sm:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Configuration</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2 text-sm">
              <Row k="Agent ID" v={<span className="font-mono text-xs">{agent.id}</span>} />
              <Row k="User ID" v={<span className="font-mono text-xs">{agent.userId}</span>} />
              <Row k="Backend" v={<span className="font-mono text-xs">{agent.backendAgent}</span>} />
              <Row k="Provider" v={<span className="font-mono text-xs">{agent.provider}</span>} />
              <Row k="Model" v={<span className="font-mono text-xs">{agent.model}</span>} />
              <Row k="Temperature" v={<span className="font-mono text-xs">{agent.temperature.toFixed(2)}</span>} />
              <Row k="Config path" v={<span className="font-mono text-xs">{agent.configPath ?? "database"}</span>} />
              <Row k="Voice" v={voice ? `${voice.name} · ${voice.provider}` : agent.voiceId} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Activity</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2 text-sm">
              <Row k="Created" v={formatRelativeTime(agent.createdAt)} />
              <Row k="Updated" v={formatRelativeTime(agent.updatedAt)} />
              <Row k="Tools" v={agent.tools.length ? `${agent.tools.length} enabled` : "None"} />
              <Row k="Tool groups" v={agent.toolGroups?.length ? agent.toolGroups.join(", ") : "None"} />
              <Row k="Status" v={<AgentStatusBadge status={agent.status} />} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="prompt">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">System prompt</CardTitle>
            </CardHeader>
            <CardContent>
              <pre className="whitespace-pre-wrap rounded-lg bg-[var(--muted)] p-4 font-mono text-xs leading-relaxed text-[var(--foreground)]">
                {agent.systemPrompt}
              </pre>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="voice">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Voice configuration</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2 text-sm">
              <Row k="Name" v={voice?.name ?? "—"} />
              <Row k="Provider" v={voice?.provider ?? (agent.voiceConfig?.tts?.voice ? "kokoro" : "—")} />
              <Row k="Voice ID" v={<span className="font-mono text-xs">{agent.voiceId}</span>} />
              <Row k="Gender" v={voice?.gender ?? "—"} />
              <Row k="Accent" v={voice?.accent ?? "—"} />
              <Row k="Speed" v={<span className="font-mono text-xs">{agent.voiceConfig?.tts?.speed ?? "—"}</span>} />
              <Row k="Language" v={<span className="font-mono text-xs">{agent.voiceConfig?.tts?.lang ?? "—"}</span>} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="tools">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Enabled tools</CardTitle>
            </CardHeader>
            <CardContent>
              {agent.tools.length === 0 ? (
                <p className="text-sm text-[var(--muted-foreground)]">No tools enabled.</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {agent.tools.map((t) => (
                    <Badge key={t} variant="outline" className="font-mono text-xs">
                      {t}
                    </Badge>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="logs">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Recent runs</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-[var(--muted-foreground)]">
                Logs will appear here once this agent starts handling calls.
              </p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-[var(--border)] py-1.5 last:border-0">
      <span className="text-[var(--muted-foreground)]">{k}</span>
      <span>{v}</span>
    </div>
  );
}
