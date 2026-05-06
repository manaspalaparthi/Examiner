"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { MessagesSquare } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ConversationStatusBadge } from "@/components/shared/status-badge";
import { EmptyState } from "@/components/shared/empty-state";
import { conversations } from "@/lib/mock-data";
import { formatDuration, formatRelativeTime } from "@/lib/utils";

export default function ConversationsPage() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<string>("all");

  const rows = useMemo(() => {
    return conversations.filter((c) => {
      if (status !== "all" && c.status !== status) return false;
      if (
        query &&
        !`${c.agentName} ${c.callerNumber ?? ""}`.toLowerCase().includes(query.toLowerCase())
      ) {
        return false;
      }
      return true;
    });
  }, [query, status]);

  return (
    <>
      <PageHeader
        title="Conversations"
        description="Browse, filter, and review every call your agents have handled."
      />

      <Card>
        <CardContent className="space-y-4 p-5">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Input
              placeholder="Search by agent or caller…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="sm:max-w-xs"
            />
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger className="sm:w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="completed">Completed</SelectItem>
                <SelectItem value="failed">Failed</SelectItem>
                <SelectItem value="in-progress">In progress</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {rows.length === 0 ? (
            <EmptyState icon={MessagesSquare} title="No matching conversations" />
          ) : (
            <div className="-mx-5 overflow-hidden border-y border-[var(--border)]">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="pl-5">Agent</TableHead>
                    <TableHead>Caller</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Duration</TableHead>
                    <TableHead className="pr-5">Started</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((c) => (
                    <TableRow key={c.id}>
                      <TableCell className="pl-5">
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
                      <TableCell className="pr-5 text-sm text-[var(--muted-foreground)]">
                        {formatRelativeTime(c.startedAt)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </>
  );
}
