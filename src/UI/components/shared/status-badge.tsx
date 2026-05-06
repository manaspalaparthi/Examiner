import { Badge } from "@/components/ui/badge";
import type { AgentStatus, Conversation } from "@/lib/types";
import { cn } from "@/lib/utils";

const agentMap: Record<AgentStatus, { label: string; variant: "success" | "muted" | "warning" }> = {
  active: { label: "Active", variant: "success" },
  draft: { label: "Draft", variant: "warning" },
  archived: { label: "Archived", variant: "muted" },
};

export function AgentStatusBadge({ status, className }: { status: AgentStatus; className?: string }) {
  const cfg = agentMap[status];
  return (
    <Badge variant={cfg.variant} className={cn("gap-1.5", className)}>
      <span
        className={cn(
          "size-1.5 rounded-full",
          status === "active" && "bg-[var(--success)]",
          status === "draft" && "bg-[var(--warning)]",
          status === "archived" && "bg-[var(--muted-foreground)]",
        )}
      />
      {cfg.label}
    </Badge>
  );
}

const convMap: Record<Conversation["status"], { label: string; variant: "success" | "destructive" | "default" }> = {
  completed: { label: "Completed", variant: "success" },
  failed: { label: "Failed", variant: "destructive" },
  "in-progress": { label: "Live", variant: "default" },
};

export function ConversationStatusBadge({ status }: { status: Conversation["status"] }) {
  const cfg = convMap[status];
  return (
    <Badge variant={cfg.variant} className="gap-1.5">
      {status === "in-progress" && <span className="size-1.5 animate-pulse rounded-full bg-current" />}
      {cfg.label}
    </Badge>
  );
}
