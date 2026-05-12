"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { MoreHorizontal, Copy, Pencil, Archive, ArchiveRestore, Trash2, Bot } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { AgentStatusBadge } from "@/components/shared/status-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { formatRelativeTime } from "@/lib/utils";
import { createClient } from "@/lib/supabase/client";
import type { Agent, AgentStatus } from "@/lib/types";

interface AgentsTableProps {
  agents: Agent[];
}

export function AgentsTable({ agents }: AgentsTableProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<"all" | AgentStatus>("all");

  useEffect(() => {
    const supabase = createClient();
    const channel = supabase
      .channel("agents-table")
      .on("postgres_changes", { event: "*", schema: "public", table: "agents" }, () => {
        router.refresh();
      })
      .subscribe();

    return () => {
      void supabase.removeChannel(channel);
    };
  }, [router]);

  const filtered = useMemo(() => {
    return agents.filter((a) => {
      if (status !== "all" && a.status !== status) return false;
      if (query && !`${a.name} ${a.description}`.toLowerCase().includes(query.toLowerCase())) return false;
      return true;
    });
  }, [agents, query, status]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <Input
          placeholder="Search agents…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="sm:max-w-xs"
        />
        <Select value={status} onValueChange={(v) => setStatus(v as typeof status)}>
          <SelectTrigger className="sm:w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="draft">Draft</SelectItem>
            <SelectItem value="archived">Archived</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon={Bot}
          title="No agents match your filters"
          description="Try clearing the search or changing the status filter."
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--card)]">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Agent</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Updated</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((agent) => (
                <TableRow key={agent.id}>
                  <TableCell>
                    <Link href={`/agents/${agent.id}`} className="block">
                      <div className="flex items-center gap-3">
                        <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-[var(--muted)]">
                          <Bot className="size-4 text-[var(--muted-foreground)]" strokeWidth={1.75} />
                        </div>
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium hover:underline">{agent.name}</div>
                          <div className="truncate text-xs text-[var(--muted-foreground)]">{agent.description}</div>
                        </div>
                      </div>
                    </Link>
                  </TableCell>
                  <TableCell>
                    <AgentStatusBadge status={agent.status} />
                  </TableCell>
                  <TableCell>
                    <span className="font-mono text-xs text-[var(--muted-foreground)]">{agent.model}</span>
                  </TableCell>
                  <TableCell>
                    <span className="text-sm text-[var(--muted-foreground)]">
                      {formatRelativeTime(agent.updatedAt)}
                    </span>
                  </TableCell>
                  <TableCell>
                    <AgentRowActions agent={agent} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}

function AgentRowActions({ agent }: { agent: Agent }) {
  const router = useRouter();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [busyAction, setBusyAction] = useState<"archive" | "duplicate" | "delete" | null>(null);
  const isArchived = agent.status === "archived";
  const disabled = busyAction !== null;

  async function updateStatus(status: AgentStatus) {
    setBusyAction("archive");
    try {
      const res = await fetch(`/api/agents/${encodeURIComponent(agent.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      if (!res.ok) throw new Error();
      toast.success(status === "archived" ? "Agent archived." : "Agent restored.");
      router.refresh();
    } catch {
      toast.error(status === "archived" ? "Could not archive agent." : "Could not restore agent.");
    } finally {
      setBusyAction(null);
    }
  }

  async function duplicateAgent() {
    setBusyAction("duplicate");
    try {
      const res = await fetch("/api/agents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: `${agent.id}-copy-${Date.now().toString(36)}`,
          userId: agent.userId,
          name: `Copy of ${agent.name}`,
          description: agent.description,
          status: "draft",
          backendAgent: agent.backendAgent,
          configPath: agent.configPath,
          voiceId: agent.voiceId,
          provider: agent.provider,
          model: agent.model,
          systemPrompt: agent.systemPrompt,
          temperature: agent.temperature,
          maxTokens: agent.maxTokens,
          historyLimit: agent.historyLimit,
          tools: agent.tools,
          toolGroups: agent.toolGroups,
          ack: agent.ack,
          mcpServers: agent.mcpServers,
          timeouts: agent.timeouts,
          tracing: agent.tracing,
          voiceConfig: agent.voiceConfig,
          startParams: agent.startParams,
        }),
      });
      if (!res.ok) throw new Error();
      toast.success("Agent duplicated as a draft.");
      router.refresh();
    } catch {
      toast.error("Could not duplicate agent.");
    } finally {
      setBusyAction(null);
    }
  }

  async function deleteAgent() {
    setBusyAction("delete");
    try {
      const res = await fetch(`/api/agents/${encodeURIComponent(agent.id)}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      toast.success("Agent deleted.");
      setDeleteOpen(false);
      router.refresh();
    } catch {
      toast.error("Could not delete agent.");
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" className="h-8 w-8" disabled={disabled}>
            <MoreHorizontal />
            <span className="sr-only">Open menu</span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem asChild>
            <Link href={`/agents/${agent.id}/edit`}>
              <Pencil /> Edit
            </Link>
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => void duplicateAgent()} disabled={disabled}>
            <Copy /> Duplicate
          </DropdownMenuItem>
          <DropdownMenuItem
            onSelect={() => void updateStatus(isArchived ? "active" : "archived")}
            disabled={disabled}
          >
            {isArchived ? <ArchiveRestore /> : <Archive />}
            {isArchived ? "Restore" : "Archive"}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={(event) => {
              event.preventDefault();
              setDeleteOpen(true);
            }}
            disabled={disabled}
            className="text-[var(--destructive)] focus:text-[var(--destructive)]"
          >
            <Trash2 /> Delete
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {agent.name}?</DialogTitle>
            <DialogDescription>
              This permanently removes the agent from the dashboard.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)} disabled={busyAction === "delete"}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => void deleteAgent()} disabled={busyAction === "delete"}>
              <Trash2 />
              {busyAction === "delete" ? "Deleting…" : "Delete agent"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
