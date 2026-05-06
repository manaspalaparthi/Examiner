import { Phone, Timer, CheckCircle2, TrendingUp } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { StatCard } from "@/components/shared/stat-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { analyticsSummary } from "@/lib/mock-data";
import { formatDuration } from "@/lib/utils";

export default function AnalyticsPage() {
  const max = Math.max(...analyticsSummary.callsLast7Days.map((d) => d.count));

  return (
    <>
      <PageHeader
        title="Analytics"
        description="Aggregate metrics across all your agents over the last 7 days."
      />

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total calls"
          value={analyticsSummary.callsLast7Days.reduce((s, d) => s + d.count, 0).toLocaleString()}
          icon={Phone}
          delta={{ value: "9.1%", trend: "up" }}
        />
        <StatCard
          label="Avg duration"
          value={formatDuration(analyticsSummary.avgDurationSec)}
          icon={Timer}
          delta={{ value: "4s", trend: "down" }}
        />
        <StatCard
          label="Success rate"
          value={`${(analyticsSummary.successRate * 100).toFixed(1)}%`}
          icon={CheckCircle2}
          delta={{ value: "0.6%", trend: "up" }}
        />
        <StatCard
          label="Avg first response"
          value="0.84s"
          icon={TrendingUp}
          delta={{ value: "12ms", trend: "down" }}
        />
      </section>

      <section className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Calls — last 7 days</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex h-56 items-end gap-3">
              {analyticsSummary.callsLast7Days.map((d) => (
                <div key={d.date} className="flex flex-1 flex-col items-center gap-2">
                  <span className="text-xs font-mono tabular-nums text-[var(--muted-foreground)]">
                    {d.count}
                  </span>
                  <div
                    className="w-full rounded-t-md bg-[var(--primary)]/85 transition-colors hover:bg-[var(--primary)]"
                    style={{ height: `${(d.count / max) * 90}%` }}
                  />
                  <span className="text-xs text-[var(--muted-foreground)]">{d.date}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Top agents</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-4">
              {analyticsSummary.topAgents.map((a) => {
                const pct = (a.calls / analyticsSummary.topAgents[0].calls) * 100;
                return (
                  <li key={a.agentId} className="space-y-1.5">
                    <div className="flex items-center justify-between text-sm">
                      <span className="font-medium">{a.name}</span>
                      <span className="font-mono text-xs text-[var(--muted-foreground)]">{a.calls}</span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--muted)]">
                      <div className="h-full bg-[var(--primary)]" style={{ width: `${pct}%` }} />
                    </div>
                  </li>
                );
              })}
            </ul>
          </CardContent>
        </Card>
      </section>

      <section className="mt-6">
        <Card>
          <CardHeader>
            <CardTitle>Outcomes</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-6 sm:grid-cols-3">
              {[
                { label: "Resolved", value: 78, color: "var(--success)" },
                { label: "Transferred to human", value: 14, color: "var(--warning)" },
                { label: "Dropped", value: 8, color: "var(--destructive)" },
              ].map((o) => (
                <div key={o.label} className="space-y-1.5">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium">{o.label}</span>
                    <span className="font-mono text-xs text-[var(--muted-foreground)]">{o.value}%</span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--muted)]">
                    <div className="h-full" style={{ width: `${o.value}%`, background: o.color }} />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </section>
    </>
  );
}
