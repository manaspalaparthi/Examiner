import Link from "next/link";
import { Bot, Phone, Timer, CheckCircle2, ArrowRight, PlusCircle } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { StatCard } from "@/components/shared/stat-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ConversationStatusBadge } from "@/components/shared/status-badge";
import { AgentCard } from "@/components/agents/agent-card";
import { agents, conversations, analyticsSummary } from "@/lib/mock-data";
import { formatDuration, formatRelativeTime } from "@/lib/utils";

export default function OverviewPage() {
  const recent = [...conversations]
    .sort((a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime())
    .slice(0, 5);
  const activeAgents = agents.filter((a) => a.status === "active").slice(0, 3);

  return (
    <>
      <PageHeader
        title="Overview"
        description="A snapshot of your voice agents and recent activity."
        actions={
          <Button asChild>
            <Link href="/create-agent">
              <PlusCircle /> New agent
            </Link>
          </Button>
        }
      />

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Active agents"
          value={analyticsSummary.activeAgents.toString()}
          icon={Bot}
          delta={{ value: "+1 this week", trend: "up" }}
        />
        <StatCard
          label="Calls today"
          value={analyticsSummary.callsToday.toLocaleString()}
          icon={Phone}
          delta={{ value: "12.4%", trend: "up" }}
        />
        <StatCard
          label="Avg duration"
          value={formatDuration(analyticsSummary.avgDurationSec)}
          icon={Timer}
          delta={{ value: "8s", trend: "down" }}
          hint="Lower is better for transactional flows."
        />
        <StatCard
          label="Success rate"
          value={`${(analyticsSummary.successRate * 100).toFixed(1)}%`}
          icon={CheckCircle2}
          delta={{ value: "0.6%", trend: "up" }}
        />
      </section>

      <section className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Recent conversations</CardTitle>
            <Button asChild variant="ghost" size="sm" className="text-xs">
              <Link href="/conversations">
                View all <ArrowRight />
              </Link>
            </Button>
          </CardHeader>
          <CardContent className="px-0 pb-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Agent</TableHead>
                  <TableHead>Caller</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead className="pr-6">Started</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recent.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="pl-6">
                      <Link href={`/conversations/${c.id}`} className="text-sm font-medium hover:underline">
                        {c.agentName}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <span className="font-mono text-xs text-[var(--muted-foreground)]">{c.callerNumber}</span>
                    </TableCell>
                    <TableCell>
                      <ConversationStatusBadge status={c.status} />
                    </TableCell>
                    <TableCell className="text-sm tabular-nums">
                      {c.durationSec ? formatDuration(c.durationSec) : "—"}
                    </TableCell>
                    <TableCell className="pr-6 text-sm text-[var(--muted-foreground)]">
                      {formatRelativeTime(c.startedAt)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Top agents</CardTitle>
            <Button asChild variant="ghost" size="sm" className="text-xs">
              <Link href="/analytics">
                Analytics <ArrowRight />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {analyticsSummary.topAgents.map((a, i) => (
                <li key={a.agentId} className="flex items-center gap-3">
                  <span className="flex size-7 items-center justify-center rounded-md bg-[var(--muted)] font-mono text-xs text-[var(--muted-foreground)]">
                    {i + 1}
                  </span>
                  <span className="flex-1 text-sm font-medium">{a.name}</span>
                  <span className="font-mono text-xs text-[var(--muted-foreground)]">{a.calls} calls</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </section>

      <section className="mt-6">
        <div className="mb-3 flex items-end justify-between">
          <h2 className="text-base font-semibold">Active agents</h2>
          <Button asChild variant="ghost" size="sm" className="text-xs">
            <Link href="/agents">
              See all agents <ArrowRight />
            </Link>
          </Button>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {activeAgents.map((a) => (
            <AgentCard key={a.id} agent={a} />
          ))}
        </div>
      </section>
    </>
  );
}
