import Link from "next/link";
import { Bot, ArrowUpRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { AgentStatusBadge } from "@/components/shared/status-badge";
import type { Agent } from "@/lib/types";

export function AgentCard({ agent }: { agent: Agent }) {
  return (
    <Card className="group flex flex-col gap-4 p-5 transition-colors hover:border-[var(--ring)]">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex size-10 items-center justify-center rounded-lg bg-[var(--muted)]">
            <Bot className="size-5 text-[var(--muted-foreground)]" strokeWidth={1.75} />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">{agent.name}</div>
            <div className="font-mono text-xs text-[var(--muted-foreground)]">{agent.model}</div>
          </div>
        </div>
        <AgentStatusBadge status={agent.status} />
      </div>
      <p className="line-clamp-2 text-sm text-[var(--muted-foreground)]">{agent.description}</p>
      <Link
        href={`/agents/${agent.id}`}
        className="inline-flex items-center gap-1 text-xs font-medium text-[var(--foreground)] hover:underline"
      >
        Open agent <ArrowUpRight className="size-3.5" />
      </Link>
    </Card>
  );
}
